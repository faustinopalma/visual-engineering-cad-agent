"""Paired comparison of drafter_choice (edit or regenerate) versus full_regeneration.

Both arms start from identical copies of the same unaccepted route, use the same configuration and attempt limit,
and run sequentially. Every validated output is then overlaid on the source view with the pipeline's own tracing
transform, measured with deterministic ink metrics and judged by a stateless model that is not told which arm
produced it. Overlay results are relative evidence, not metrology or human approval.
"""
import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from astra_client import AstraClient
from astra_cad_agent import ROOT, process, save
from quality_campaign import seeded_history


MODES = ("drafter_choice", "full_regeneration")
SCALE = 0.25
INK_CONTRAST = 70
INK_RULE = ("ink = pixel darker than the local paper level by more than " + str(INK_CONTRAST) + " grey levels "
            "(median 5 px; paper = 31 px local maximum, 10 px box blur; 3 px opening) so broad scan stains are not ink")
TOLERANCE_PX = 3
CURVE_SAMPLES = 96
JUDGE_SCHEMA = {"type": "object", "properties": {
    "adherence_score": {"type": "integer"}, "coverage_score": {"type": "integer"}, "assessment": {"type": "string"},
    "offset_or_misshapen": {"type": "array", "items": {"type": "string"}},
    "missing_geometry": {"type": "array", "items": {"type": "string"}},
    "extra_geometry": {"type": "array", "items": {"type": "string"}}},
    "required": ["adherence_score", "coverage_score", "assessment", "offset_or_misshapen", "missing_geometry", "extra_geometry"],
    "additionalProperties": False}
JUDGE_PROMPT = (
    "Act as a strict, independent overlay adherence judge for a 2D CAD reconstruction. Image 1 is the original scanned "
    "drawing view. Image 2 is the same view with the original ink lightened to gray and the reconstructed CAD geometry "
    "drawn on top in red (translucent red areas are CAD hatch regions), placed with the reconstruction pipeline's own "
    "pixel transform; no alignment was fitted afterwards. Judge only geometric adherence: do red contours, circles, "
    "curves, centerlines, hidden lines and hatch regions lie on the corresponding original lines, with the same shape, "
    "proportions and relative view positions? Text, dimensions, leaders, arrows, title block, handwritten notes, frame "
    "borders and scan stains are intentionally omitted and are NOT defects. adherence_score 0-100: how precisely the red "
    "geometry that exists sits on real original geometry (100 = everything drawn coincides; penalize offsets, wrong "
    "shapes, invented lines). coverage_score 0-100: how much of the reproducible original geometry (excluding the omitted "
    "categories) is covered by red. List concrete regions by view and component. This is a visual judgment at the "
    "tracing transform, not dimensional metrology, and never human approval.")


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def to_pixel(point, height):
    return (point[0] / SCALE, height - point[1] / SCALE)


def circle_points(center, radius, samples=CURVE_SAMPLES):
    return [(center[0] + radius * math.cos(2 * math.pi * index / samples), center[1] + radius * math.sin(2 * math.pi * index / samples))
            for index in range(samples + 1)]


def bspline_points(poles, weights, knots, degree, samples=CURVE_SAMPLES):
    """Evaluate a clamped, possibly rational, non-periodic B-spline with de Boor's algorithm."""
    count = len(poles)
    if len(knots) != count + degree + 1:
        raise ValueError("B-spline knot vector length does not match poles and degree.")
    start, end = knots[degree], knots[count]
    points = []
    for index in range(samples + 1):
        parameter = start + (end - start) * index / samples
        span = degree
        while span < count - 1 and knots[span + 1] <= parameter:
            span += 1
        values = [[poles[j][0] * weights[j], poles[j][1] * weights[j], weights[j]] for j in range(span - degree, span + 1)]
        for level in range(1, degree + 1):
            for j in range(degree, level - 1, -1):
                left = knots[j + span - degree]
                denominator = knots[j + 1 + span - level] - left
                alpha = 0.0 if denominator == 0 else (parameter - left) / denominator
                values[j] = [(1 - alpha) * values[j - 1][axis] + alpha * values[j][axis] for axis in range(3)]
        points.append((values[degree][0] / values[degree][2], values[degree][1] / values[degree][2]))
    return points


def catmull_rom(points, samples_per_segment=16):
    """Centripetal Catmull-Rom curve through fit points: an approximation of a fit-point spline between its fit points."""
    points = [tuple(point) for point in points]
    if len(points) < 3:
        return points
    padded = [tuple(2 * a - b for a, b in zip(points[0], points[1]))] + points + [tuple(2 * a - b for a, b in zip(points[-1], points[-2]))]
    result = [points[0]]
    for index in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[index - 1:index + 3]
        def knot(previous, a, b):
            return previous + max(math.dist(a, b), 1e-9) ** 0.5
        t0 = 0.0
        t1 = knot(t0, p0, p1)
        t2 = knot(t1, p1, p2)
        t3 = knot(t2, p2, p3)
        for step in range(1, samples_per_segment + 1):
            t = t1 + (t2 - t1) * step / samples_per_segment
            def lerp(a, b, ta, tb):
                return tuple(((tb - t) * u + (t - ta) * v) / (tb - ta) for u, v in zip(a, b))
            a1, a2, a3 = lerp(p0, p1, t0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
            b1, b2 = lerp(a1, a2, t0, t2), lerp(a2, a3, t1, t3)
            result.append(lerp(b1, b2, t1, t2))
    return result


def freecad_geometry(path):
    """Read the saved native sketch geometry from a FreeCAD document without launching FreeCAD."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("Document.xml"))
    polylines, counts = [], {}
    for item in root.iter("Object"):
        properties = {node.get("name"): node for node in item.findall("./Properties/Property")}
        if "Geometry" not in properties or "Constraints" not in properties:
            continue
        placement = properties.get("Placement")
        if placement is not None:
            values = placement.find("PropertyPlacement").attrib
            if any(abs(float(values.get(key, 0))) > 1e-9 for key in ("Px", "Py", "Pz", "Q0", "Q1", "Q2")):
                raise ValueError("Sketch placement is not identity; overlay transform would be wrong: " + item.get("name", "?"))
        for geometry in properties["Geometry"].iter("Geometry"):
            construction = geometry.find("Construction")
            if construction is not None and construction.get("value") == "1":
                continue
            kind = geometry.get("type")
            if kind == "Part::GeomLineSegment":
                line = geometry.find("LineSegment").attrib
                polylines.append([(float(line["StartX"]), float(line["StartY"])), (float(line["EndX"]), float(line["EndY"]))])
            elif kind == "Part::GeomCircle":
                circle = geometry.find("Circle").attrib
                polylines.append(circle_points((float(circle["CenterX"]), float(circle["CenterY"])), float(circle["Radius"])))
            elif kind == "Part::GeomBSplineCurve":
                curve = geometry.find("BSplineCurve")
                if curve.get("IsPeriodic") not in (None, "0"):
                    raise ValueError("Periodic B-splines are not supported by the overlay reader.")
                poles = [(float(node.get("X")), float(node.get("Y"))) for node in curve.findall("Pole")]
                weights = [float(node.get("Weight", 1)) for node in curve.findall("Pole")]
                knots = [float(node.get("Value")) for node in curve.findall("Knot") for _ in range(int(node.get("Mult")))]
                polylines.append(bspline_points(poles, weights, knots, int(curve.get("Degree"))))
            else:
                raise ValueError("Unsupported native geometry for overlay: " + str(kind))
            counts[kind] = counts.get(kind, 0) + 1
    return {"polylines": polylines, "fills": [], "counts": counts,
            "source": "Saved FreeCAD Document.xml sketch geometry (lines, circles, B-spline poles and knots evaluated exactly)."}


def qcad_geometry(geometry_path, compiled_path):
    """Use QCAD's readback of the reopened DXF; hatch loops come from the compiled model QCAD verified by area and loop count."""
    report = json.loads(Path(geometry_path).read_text())
    if report.get("status") != "passed" or not report.get("reopened"):
        raise ValueError("QCAD geometry receipt did not pass after reopening.")
    compiled = json.loads(Path(compiled_path).read_text())
    hatches = [entity for entity in compiled["entities"] if entity["type"] == "hatch"]
    polylines, fills, counts = [], [], {}
    for entity in report["entities"]:
        kind = entity["type"]
        if kind == "line":
            polylines.append([tuple(entity["start"]), tuple(entity["end"])])
        elif kind == "polyline":
            points = [tuple(point) for point in entity["points"]]
            polylines.append(points + ([points[0]] if entity.get("closed") else []))
        elif kind == "circle":
            polylines.append(circle_points(entity["center"], entity["radius"]))
        elif kind == "spline":
            polylines.append(catmull_rom(entity["fit_points"]))
        elif kind != "hatch":
            raise ValueError("Unsupported QCAD readback entity for overlay: " + str(kind))
        counts[kind] = counts.get(kind, 0) + 1
    if counts.get("hatch", 0) != len(hatches):
        raise ValueError("QCAD hatch readback count differs from compiled hatch loops.")
    for hatch in hatches:
        fills.append([[tuple(point) for point in loop] for loop in hatch["loops"]])
    return {"polylines": polylines, "fills": fills, "counts": counts,
            "source": "QCAD readback of the reopened DXF; fit-point splines drawn with a centripetal Catmull-Rom approximation between fit points; hatch loops from the executor-verified compiled model."}


def native_geometry(cad, compiled_path):
    cad = Path(cad)
    if (cad / "draft.FCStd").exists():
        return freecad_geometry(cad / "draft.FCStd")
    if (cad / "draft.dxf").exists() and (cad / "geometry.json").exists():
        return qcad_geometry(cad / "geometry.json", compiled_path)
    raise ValueError("No native CAD document for overlay in " + str(cad))


def ink_mask(source):
    smooth = source.filter(ImageFilter.MedianFilter(5))
    paper = smooth.filter(ImageFilter.MaxFilter(31)).filter(ImageFilter.BoxBlur(10))
    contrast = np.array(paper, dtype=np.int16) - np.array(smooth, dtype=np.int16)
    mask = Image.fromarray(np.uint8(contrast > INK_CONTRAST) * 255)
    return mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))


def overlay(view_path, geometry, output):
    """Render the CAD on the source with the tracing transform and compute deterministic ink agreement metrics."""
    output.mkdir(parents=True, exist_ok=True)
    source = Image.open(view_path).convert("L")
    width, height = source.size
    pixel_lines = [[to_pixel(point, height) for point in line] for line in geometry["polylines"]]
    pixel_fills = [[[to_pixel(point, height) for point in loop] for loop in fill] for fill in geometry["fills"]]
    centerline = Image.new("L", source.size, 0)
    drawing = ImageDraw.Draw(centerline)
    for line in pixel_lines:
        drawing.line(line, fill=255, width=1)
    ink = ink_mask(source)
    size = 2 * TOLERANCE_PX + 1
    ink_near = np.array(ink.filter(ImageFilter.MaxFilter(size))) > 0
    cad_near = np.array(centerline.filter(ImageFilter.MaxFilter(size))) > 0
    cad_pixels = np.array(centerline) > 0
    ink_pixels = np.array(ink) > 0
    precision = float((cad_pixels & ink_near).sum() / cad_pixels.sum()) if cad_pixels.any() else None
    recall = float((ink_pixels & cad_near).sum() / ink_pixels.sum()) if ink_pixels.any() else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    lightened = source.point(lambda value: round(255 - (255 - value) * 0.5)).convert("RGBA")
    layer = Image.new("RGBA", source.size, (0, 0, 0, 0))
    painter = ImageDraw.Draw(layer)
    for fill in pixel_fills:
        painter.polygon(fill[0], fill=(220, 0, 0, 55))
        for hole in fill[1:]:
            painter.polygon(hole, fill=(0, 0, 0, 0))
    for line in pixel_lines:
        painter.line(line, fill=(220, 0, 0, 255), width=2)
    Image.alpha_composite(lightened, layer).convert("RGB").save(output / "overlay.png")
    agreement = np.full((height, width, 3), 255, dtype=np.uint8)
    agreement[ink_pixels & ~cad_near] = (200, 200, 200)
    strokes = np.array(Image.fromarray(np.uint8(cad_pixels) * 255).filter(ImageFilter.MaxFilter(3))) > 0
    agreement[strokes & ink_near] = (0, 150, 60)
    agreement[strokes & ~ink_near] = (220, 0, 120)
    Image.fromarray(agreement).save(output / "agreement.png")
    metrics = {"view_size": [width, height], "ink_rule": INK_RULE, "tolerance_px": TOLERANCE_PX,
               "cad_pixels": int(cad_pixels.sum()), "ink_pixels": int(ink_pixels.sum()),
               "ink_precision": precision, "ink_recall": recall, "ink_f1": f1,
               "geometry_counts": geometry["counts"], "geometry_source": geometry["source"],
               "definition": "precision = share of CAD centerline pixels within the tolerance (square neighbourhood) of source ink; recall = share of source ink pixels within the tolerance of CAD. Source ink includes text, dimensions and title block that the reconstruction must omit, so recall is only comparable between outputs of the same drawing.",
               "status": "relative evidence at the tracing transform; not metrology"}
    save(output / "overlay-metrics.json", metrics)
    return metrics


def git_state():
    def git(*arguments):
        return subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.strip()
    return {"commit": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def plan_comparison(output, seeds, max_attempts):
    output.mkdir(parents=True)
    arms = []
    for index, seed in enumerate(seeds):
        seed = seed.resolve()
        result = json.loads((seed / "result.json").read_text())
        config = json.loads((seed / "config.json").read_text())
        native = result["method"] == "qcad" and config.get("native_qcad", False)
        label = seed.parent.name + "-" + result["method"] + ("-native" if native else "")
        source = output / label / "source"
        source.mkdir(parents=True)
        for path in sorted((seed.parent / "source").iterdir()):
            if path.is_file():
                (source / path.name).write_bytes(path.read_bytes())
        for mode in (MODES if index % 2 == 0 else MODES[::-1]):
            arm_config = output / label / (mode + ".config.json")
            save(arm_config, dict(config, revision_mode=mode, max_attempts=max_attempts))
            arms.append({"label": label, "seed": str(seed), "method": result["method"], "native_qcad": native, "mode": mode,
                         "route": str(output / label / mode), "config": str(arm_config)})
    first = json.loads((Path(arms[0]["seed"]) / "config.json").read_text())
    save(output / "judge.config.json", dict(first, deployment=first.get("evaluator_deployment", first["deployment"]),
                                            max_calls_per_route=2, max_total_tokens_per_route=None))
    plan = {"created_unix_seconds": time.time(), "code": git_state(), "modes": list(MODES), "max_attempts": max_attempts, "arms": arms,
            "protocol": "Each arm copies the same seed route (identical hashes), uses the seed's own configuration with only revision_mode and max_attempts set, and runs sequentially with a 3,600 s supervisor deadline. Arm order alternates between seeds. Overlay judgment is stateless and blind to the arm.",
            "human_approval": False}
    save(output / "plan.json", plan)
    return plan


def arm_name(arm):
    return arm.get("name", arm["mode"])


def ordered_arms(plan, label):
    arms = [arm for arm in plan["arms"] if arm["label"] == label]
    return sorted(arms, key=lambda arm: (MODES.index(arm["mode"]), arm_name(arm) != arm["mode"], arm_name(arm)))


def add_arm(output, label, mode, name, note):
    """Append an extra arm (for example a rerun after a validator fix) without touching existing arms."""
    plan = json.loads((output / "plan.json").read_text())
    if any(arm["label"] == label and arm_name(arm) == name for arm in plan["arms"]) or name in MODES:
        raise ValueError("Arm name already used: " + name)
    template = next(arm for arm in plan["arms"] if arm["label"] == label and arm["mode"] == mode and arm_name(arm) == mode)
    config = output / label / (name + ".config.json")
    save(config, json.loads(Path(template["config"]).read_text()))
    plan["arms"].append(dict(template, name=name, route=str(output / label / name), config=str(config), code=git_state(), note=note,
                             added_unix_seconds=time.time()))
    save(output / "plan.json", plan)


def run(output, seeds, max_attempts):
    plan = json.loads((output / "plan.json").read_text()) if (output / "plan.json").exists() else plan_comparison(output, seeds, max_attempts)
    lock = ROOT / "work/.astra-campaign.lock"
    with lock.open("x") as handle:
        handle.write(str(os.getpid()))
    try:
        for arm in plan["arms"]:
            route = Path(arm["route"])
            if (route / "result.json").exists():
                continue
            if route.exists():
                raise RuntimeError("Interrupted arm needs manual review before rerun (seeded route is not empty): " + str(route))
            supervisor = route.parent / (arm_name(arm) + "-supervisor")
            supervisor.mkdir(exist_ok=True)
            print(json.dumps({"event": "arm_started", "label": arm["label"], "arm": arm_name(arm)}), flush=True)
            command = [sys.executable, str(ROOT / "scripts/quality_campaign.py"), "worker", str(route), "--method", arm["method"],
                       "--config", arm["config"], "--seed-route", arm["seed"]]
            try:
                process(command, supervisor, dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), 3600)
            except Exception as error:
                if not (route / "result.json").exists():
                    route.mkdir(parents=True, exist_ok=True)
                    save(route / "result.json", {"method": arm["method"], "status": "supervisor_failed", "error": str(error),
                                                 "revision_mode": arm["mode"], "candidates": [], "usage_complete": False})
            print(json.dumps({"event": "arm_finished", "label": arm["label"], "arm": arm_name(arm)}), flush=True)
    finally:
        lock.unlink()


def collect(output):
    """List every output to measure: the seed's best candidate per drawing and every new candidate of every arm."""
    plan = json.loads((output / "plan.json").read_text())
    rows = []
    for label in dict.fromkeys(arm["label"] for arm in plan["arms"]):
        arms = ordered_arms(plan, label)
        seed = Path(arms[0]["seed"])
        seeded, _ = seeded_history(seed)
        scored = [item for item in seeded if item.get("score") is not None]
        if scored:
            start = max(scored, key=lambda item: (item["score"], item["attempt"]))
            rows.append({"id": label + "/start", "label": label, "arm": "start", "attempt": start["attempt"], "mode": "seed",
                         "cad": start["cad"], "compiled": str(seed / (str(start["attempt"]) + "-compiled.json")),
                         "internal_score": start["score"], "internal_accepted": start["accepted"]})
        for arm in arms:
            route = Path(arm["route"])
            result = json.loads((route / "result.json").read_text()) if (route / "result.json").exists() else {"status": "not_run", "candidates": []}
            for candidate in result.get("candidates", []):
                if candidate.get("seeded"):
                    continue
                row = {"id": label + "/" + arm_name(arm) + "/" + str(candidate["attempt"]), "label": label, "arm": arm_name(arm),
                       "attempt": candidate["attempt"], "mode": candidate.get("mode"), "base_attempt": candidate.get("base_attempt"),
                       "operations": candidate.get("operations"), "error": candidate.get("error")}
                if candidate.get("cad"):
                    row.update(cad=candidate["cad"], compiled=str(route / (str(candidate["attempt"]) + "-compiled.json")),
                               internal_score=candidate["score"], internal_accepted=candidate["accepted"])
                rows.append(row)
    return plan, rows


def measure(output):
    _, rows = collect(output)
    for row in rows:
        if not row.get("cad"):
            continue
        target = output / "overlays" / row["id"].replace("/", "__")
        if (target / "overlay-metrics.json").exists():
            continue
        view = output / row["label"] / "source" / "view.png"
        overlay(view, native_geometry(row["cad"], row["compiled"]), target)
        print(json.dumps({"overlay": row["id"]}), flush=True)


def judge_once(config, view, target, filename, inference):
    client = AstraClient(config, target / inference)
    for retry in range(2):
        try:
            judgment = client.call("overlay-judge" + ("-retry" if retry else ""), JUDGE_PROMPT, [view, target / "overlay.png"], JUDGE_SCHEMA, 16000)
            break
        except Exception as error:
            save(target / (filename.replace(".json", "") + "-error-" + str(retry) + ".json"), {"error": str(error), "usage_may_be_unknown": True})
            if retry:
                raise
    for key in ("adherence_score", "coverage_score"):
        if not isinstance(judgment[key], int) or not 0 <= judgment[key] <= 100:
            raise ValueError("Invalid overlay judge score.")
    usage = [item.get("usage") or {} for item in client.metrics]
    result = dict(judgment, deployment=config["deployment"], calls=len(client.metrics),
                  input_tokens=sum(item.get("input_tokens", 0) for item in usage), output_tokens=sum(item.get("output_tokens", 0) for item in usage),
                  blind="Judge saw only the source view and the overlay; arm, mode, scores and history were withheld.")
    save(target / filename, result)
    return result


def judge(output):
    plan, rows = collect(output)
    config = json.loads((output / "judge.config.json").read_text())
    measured = [row for row in rows if row.get("cad")]
    for row in sorted(measured, key=lambda item: sha256_text(str(plan["created_unix_seconds"]) + item["id"])):
        target = output / "overlays" / row["id"].replace("/", "__")
        if (target / "overlay-judgment.json").exists():
            continue
        judgment = judge_once(config, output / row["label"] / "source" / "view.png", target, "overlay-judgment.json", "judge-inference")
        print(json.dumps({"judged": row["id"], "adherence": judgment["adherence_score"], "coverage": judgment["coverage_score"]}), flush=True)


def judge_repeat(output, ids, count):
    """Re-judge identical images to measure how much the judge's own scores vary."""
    config = json.loads((output / "judge.config.json").read_text())
    _, rows = collect(output)
    known = {row["id"]: row for row in rows if row.get("cad")}
    for row_id in ids:
        row = known[row_id]
        target = output / "overlays" / row_id.replace("/", "__")
        for index in range(1, count + 1):
            name = "overlay-judgment-repeat-" + str(index) + ".json"
            if (target / name).exists():
                continue
            judgment = judge_once(config, output / row["label"] / "source" / "view.png", target, name, "judge-inference-repeat-" + str(index))
            print(json.dumps({"repeat": row_id, "index": index, "adherence": judgment["adherence_score"], "coverage": judgment["coverage_score"]}), flush=True)


def decisions(result):
    steps = []
    for candidate in result.get("candidates", []):
        if candidate.get("seeded"):
            continue
        step = candidate.get("mode") or "unknown"
        if step == "edit_existing":
            counts = candidate.get("operations") or {}
            step += " (base " + str(candidate.get("base_attempt")) + "; " + ", ".join(key + " " + str(value) for key, value in counts.items() if value) + ")"
        if candidate.get("error"):
            step += " -> failed validation"
        steps.append(step)
    return steps


def fmt(value, digits=None, percent=False):
    if value is None:
        return "-"
    if percent:
        return str(round(value * 100, 1)) + "%"
    return str(round(value, digits)) if digits is not None else str(value)


def report(output):
    plan, rows = collect(output)
    for row in rows:
        target = output / "overlays" / row["id"].replace("/", "__")
        row["metrics"] = json.loads((target / "overlay-metrics.json").read_text()) if (target / "overlay-metrics.json").exists() else {}
        row["judgment"] = json.loads((target / "overlay-judgment.json").read_text()) if (target / "overlay-judgment.json").exists() else {}
        row["repeats"] = [json.loads(path.read_text()) for path in sorted(target.glob("overlay-judgment-repeat-*.json"))
                          if "-error-" not in path.name] if target.exists() else []
        row["judge_failures"] = len(list(target.glob("*error-*.json"))) if target.exists() else 0
        row["images"] = target if (target / "overlay.png").exists() else None
    results = {}
    for arm in plan["arms"]:
        route = Path(arm["route"])
        results[(arm["label"], arm_name(arm))] = json.loads((route / "result.json").read_text()) if (route / "result.json").exists() else {"status": "not_run"}
    summary = []
    for label in dict.fromkeys(arm["label"] for arm in plan["arms"]):
        start = next((row for row in rows if row["label"] == label and row["arm"] == "start"), None)
        if start:
            summary.append(dict(start, row_kind="start", decisions=["seed best (" + str(start["attempt"]) + ")"], result={}))
        for arm in ordered_arms(plan, label):
            name = arm_name(arm)
            result = results.get((label, name), {"status": "not_run"})
            new = [row for row in rows if row["label"] == label and row["arm"] == name]
            valid = [row for row in new if row.get("cad")]
            best = max(valid, key=lambda row: (row["internal_score"], row["attempt"])) if valid else None
            entry = dict(best or {"label": label, "arm": name, "metrics": {}, "judgment": {}, "images": None})
            entry.update(row_kind="arm", decisions=decisions(result), result=result, new_attempts=len(new), new_valid=len(valid))
            summary.append(entry)
    save(output / "comparison.json", {"plan": plan, "rows": [{key: (str(value) if isinstance(value, Path) else value) for key, value in row.items()} for row in rows]})
    header = ["Drawing / backend", "Arm", "Output", "Drafter decisions", "Valid new / attempts", "Internal evaluator", "Overlay judge adherence",
              "Overlay judge coverage", "Ink precision", "Ink recall", "Calls", "Input / output tokens", "Seconds", "Route status"]
    def cells(entry):
        result = entry.get("result", {})
        start = entry["row_kind"] == "start"
        output_name = ("attempt " + str(entry["attempt"])) if entry.get("attempt") else "no valid new output"
        return [entry["label"], "start (seed)" if start else entry["arm"], output_name, "; ".join(entry["decisions"]) or "-",
                "-" if start else str(entry["new_valid"]) + " / " + str(entry["new_attempts"]),
                fmt(entry.get("internal_score")), fmt(entry["judgment"].get("adherence_score")), fmt(entry["judgment"].get("coverage_score")),
                fmt(entry["metrics"].get("ink_precision"), percent=True), fmt(entry["metrics"].get("ink_recall"), percent=True),
                "-" if start else fmt(result.get("calls")),
                "-" if start else fmt(result.get("input_tokens")) + " / " + fmt(result.get("output_tokens")),
                "-" if start else fmt(None if result.get("elapsed_seconds") is None else round(result["elapsed_seconds"])), "seed: not accepted" if start else result.get("status", "-")]
    notes = ["Same seed copy, configuration, model deployment and attempt limit (" + str(plan["max_attempts"]) + ") for both arms; arms ran sequentially with alternating order.",
             "Output = best new candidate of the arm by internal evaluator score; the seed row is the common starting point.",
             "Ink precision = share of CAD line pixels within " + str(TOLERANCE_PX) + " px of source ink (adherence of what was drawn). Ink recall = share of source ink near CAD; source ink includes text, dimensions and title block that must be omitted, so recall compares outputs of the same drawing only.",
             "Overlay judge: stateless model call (" + json.loads((output / "judge.config.json").read_text())["deployment"] + ") seeing only the source view and the overlay, blind to arm and scores. Same provider as drafter/evaluator: errors may be correlated.",
             "Overlay uses the pipeline's own pixel transform (no fitted alignment). Relative evidence only: not metrology, not human approval. One route per arm and drawing is too few for statistical conclusions."]
    for arm in plan["arms"]:
        if arm.get("note"):
            notes.append("Extra arm " + arm["label"] + " / " + arm_name(arm) + " (code " + arm["code"]["commit"][:7] + ("+dirty" if arm["code"]["dirty"] else "")
                         + ", same seed and configuration as " + arm["mode"] + "): " + arm["note"])
    judged = [item for row in rows for item in ([row["judgment"]] if row["judgment"] else []) + row["repeats"]]
    failures = sum(row["judge_failures"] for row in rows)
    if judged:
        notes.append("Overlay judge usage: " + str(sum(item.get("calls", 0) for item in judged)) + " successful calls, "
                     + str(sum(item.get("input_tokens", 0) for item in judged)) + " input / " + str(sum(item.get("output_tokens", 0) for item in judged))
                     + " output tokens" + (" plus " + str(failures) + " failed call(s) with unknown usage" if failures else "")
                     + ". Not included in the per-arm token columns, which cover only the drafter and internal evaluator.")
    repeated = [row for row in rows if row["repeats"]]
    repeat_lines, repeat_html = [], []
    if repeated:
        repeat_header = ["Output", "Adherence (first, repeats)", "Coverage (first, repeats)", "Adherence spread", "Coverage spread"]
        repeat_lines = ["", "## Overlay judge repeatability", "", "Identical source and overlay judged again in fresh stateless calls.", "",
                        "| " + " | ".join(repeat_header) + " |", "|---|---|---|---:|---:|"]
        repeat_html = ["<tr>" + "".join("<th>" + html.escape(name) + "</th>" for name in repeat_header) + "</tr>"]
        for row in repeated:
            adherence = [row["judgment"]["adherence_score"]] + [item["adherence_score"] for item in row["repeats"]]
            coverage = [row["judgment"]["coverage_score"]] + [item["coverage_score"] for item in row["repeats"]]
            values = [row["id"], ", ".join(map(str, adherence)), ", ".join(map(str, coverage)),
                      str(max(adherence) - min(adherence)), str(max(coverage) - min(coverage))]
            repeat_lines.append("| " + " | ".join(values) + " |")
            repeat_html.append("<tr>" + "".join("<td>" + html.escape(value) + "</td>" for value in values) + "</tr>")
    lines = ["# Edit-capable vs full-regeneration comparison", "", "Code: " + plan["code"]["branch"] + " @ " + plan["code"]["commit"][:7] + (" (uncommitted changes)" if plan["code"]["dirty"] else ""), "",
             "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines.extend("| " + " | ".join(cell.replace("|", "/") for cell in cells(entry)) + " |" for entry in summary)
    lines.extend(["", "## All new candidates", "", "| Drawing / backend | Arm | Attempt | Action | Internal | Judge adherence | Judge coverage | Ink precision | Ink recall | Error |", "|---|---|---:|---|---:|---:|---:|---:|---:|---|"])
    for row in rows:
        if row["arm"] == "start":
            continue
        lines.append("| " + " | ".join(str(value).replace("|", "/") for value in (row["label"], row["arm"], row["attempt"], row.get("mode"), fmt(row.get("internal_score")),
                     fmt(row["judgment"].get("adherence_score")), fmt(row["judgment"].get("coverage_score")), fmt(row["metrics"].get("ink_precision"), percent=True),
                     fmt(row["metrics"].get("ink_recall"), percent=True), (row.get("error") or "")[:160])) + " |")
    lines.extend(["", "## Notes", ""] + ["- " + note for note in notes] + repeat_lines + ["", "## Overlay judge assessments", ""])
    for entry in summary:
        if entry["judgment"]:
            lines.extend(["### " + entry["label"] + " / " + ("start" if entry["row_kind"] == "start" else entry["arm"]), "", entry["judgment"]["assessment"], ""])
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    def image(entry, name):
        if not entry.get("images"):
            return "<span class=muted>no image</span>"
        relative = Path(os.path.relpath(Path(entry["images"]) / name, output)).as_posix()
        return "<a href='" + html.escape(relative) + "'><img src='" + html.escape(relative) + "' alt='" + name + "'></a>"
    table = ["<table><tr>" + "".join("<th>" + html.escape(name) + "</th>" for name in header + ["Overlay (red = CAD)", "Agreement (green on ink, magenta off ink)"]) + "</tr>"]
    for entry in summary:
        css = " class=start" if entry["row_kind"] == "start" else ""
        table.append("<tr" + css + ">" + "".join("<td>" + html.escape(cell) + "</td>" for cell in cells(entry)) + "<td>" + image(entry, "overlay.png") + "</td><td>" + image(entry, "agreement.png") + "</td></tr>")
    table.append("</table>")
    sources = "".join("<figure><img src='" + html.escape(label + "/source/view.png") + "'><figcaption>" + html.escape(label) + " original view</figcaption></figure>"
                      for label in dict.fromkeys(arm["label"] for arm in plan["arms"]))
    page = ("<!doctype html><meta charset=utf-8><title>Edit vs regeneration comparison</title><style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1b1f24}"
            "table{border-collapse:collapse;font-size:13px}td,th{border:1px solid #c9d1d9;padding:6px;vertical-align:top}th{background:#eef2f6}tr.start td{background:#f7f7f2}"
            "img{max-width:260px;max-height:320px;display:block}figure{display:inline-block;margin:8px}figure img{max-width:300px}.muted{color:#888}</style>"
            "<h1>Edit-capable (drafter_choice) vs full regeneration</h1><p>Code " + html.escape(plan["code"]["branch"] + " @ " + plan["code"]["commit"][:7]) + "</p>"
            + "".join(table) + "<h2>Notes</h2><ul>" + "".join("<li>" + html.escape(note) + "</li>" for note in notes) + "</ul>"
            + ("<h2>Overlay judge repeatability</h2><table>" + "".join(repeat_html) + "</table>" if repeat_html else "")
            + "<h2>Original views</h2>" + sources)
    (output / "report.html").write_text(page, encoding="utf-8")
    print(json.dumps({"report": str(output / "report.md"), "html": str(output / "report.html"), "rows": len(summary)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("run", "overlay", "judge", "report", "all", "add-arm", "judge-repeat"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--seed-route", type=Path, action="append", default=[])
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--label", help="add-arm: drawing/backend label from plan.json")
    parser.add_argument("--mode", choices=MODES, help="add-arm: revision mode of the extra arm")
    parser.add_argument("--name", help="add-arm: unique arm name, for example drafter_choice-rerun")
    parser.add_argument("--note", help="add-arm: why the extra arm exists")
    parser.add_argument("--row", action="append", default=[], help="judge-repeat: output id to judge again")
    parser.add_argument("--count", type=int, default=2, help="judge-repeat: repeats per output")
    arguments = parser.parse_args()
    directory = arguments.directory.resolve()
    if arguments.action == "add-arm":
        if not (arguments.label and arguments.mode and arguments.name and arguments.note):
            parser.error("add-arm needs --label, --mode, --name and --note")
        add_arm(directory, arguments.label, arguments.mode, arguments.name, arguments.note)
        raise SystemExit(0)
    if arguments.action == "judge-repeat":
        if not arguments.row:
            parser.error("judge-repeat needs at least one --row, for example 06-freecad-neka/start")
        judge_repeat(directory, arguments.row, arguments.count)
        raise SystemExit(0)
    if arguments.action in ("run", "all"):
        if not (directory / "plan.json").exists() and not arguments.seed_route:
            parser.error("run needs at least one --seed-route for a new comparison")
        run(directory, arguments.seed_route, arguments.max_attempts)
    if arguments.action in ("overlay", "all"):
        measure(directory)
    if arguments.action in ("judge", "all"):
        judge(directory)
    if arguments.action in ("report", "all"):
        report(directory)
