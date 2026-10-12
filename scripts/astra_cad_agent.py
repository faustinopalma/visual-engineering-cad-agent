import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageOps

from astra_client import AstraClient


ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ("qcad", "freecad-direct", "freecad-mcp")
POINT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
SHAPE = {"type": "object", "properties": {
    "type": {"type": "string", "enum": ["line", "polyline", "circle", "spline"]},
    "points": {"type": "array", "items": POINT}, "radius": {"type": "number"}, "closed": {"type": "boolean"}},
    "required": ["type", "points", "radius", "closed"], "additionalProperties": False}
COMPONENT = {"type": "object", "properties": {"id": {"type": "string"}, "meaning": {"type": "string"},
             "shapes": {"type": "array", "items": SHAPE}}, "required": ["id", "meaning", "shapes"], "additionalProperties": False}
MODEL_SCHEMA = {"type": "object", "properties": {"notes": {"type": "string"},
                "components": {"type": "array", "items": COMPONENT}}, "required": ["notes", "components"], "additionalProperties": False}
PLAN_SCHEMA = {"type": "object", "properties": {"interpretation": {"type": "string"},
               "uncertainties": {"type": "array", "items": {"type": "string"}},
               "components": {"type": "array", "items": {"type": "string"}}},
               "required": ["interpretation", "uncertainties", "components"], "additionalProperties": False}
REVIEW_SCHEMA = {"type": "object", "properties": {"assessment": {"type": "string"}, "revise": {"type": "boolean"},
                 "model": MODEL_SCHEMA}, "required": ["assessment", "revise", "model"], "additionalProperties": False}


def save(path, value):
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def validate_model(model, width, height):
    if not isinstance(model, dict) or set(model) != {"notes", "components"} or not isinstance(model["notes"], str):
        raise ValueError("Invalid model envelope.")
    components = model["components"]
    if not isinstance(components, list) or not 1 <= len(components) <= 30:
        raise ValueError("Component count out of bounds.")
    identifiers = set()
    shapes_count = 0
    segments_count = 0
    for component in components:
        if not isinstance(component, dict) or set(component) != {"id", "meaning", "shapes"}:
            raise ValueError("Invalid component fields.")
        name = component["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", name) or name in identifiers:
            raise ValueError("Invalid or duplicate component ID.")
        identifiers.add(name)
        if not isinstance(component["meaning"], str) or len(component["meaning"]) > 1000 or not isinstance(component["shapes"], list) or not component["shapes"]:
            raise ValueError("Invalid component meaning/shapes.")
        for shape in component["shapes"]:
            if not isinstance(shape, dict) or set(shape) != {"type", "points", "radius", "closed"}:
                raise ValueError("Invalid shape fields.")
            kind = shape["type"]
            points = shape["points"]
            if kind not in {"line", "circle", "polyline", "spline"} or not isinstance(points, list) or not isinstance(shape["closed"], bool):
                raise ValueError("Unsupported shape.")
            if not 1 <= len(points) <= 80 or (kind == "line" and len(points) != 2) or (kind == "circle" and len(points) != 1) or (kind in {"polyline", "spline"} and len(points) < 2):
                raise ValueError("Invalid point count.")
            for point in points:
                if not isinstance(point, list) or len(point) != 2 or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in point):
                    raise ValueError("Invalid coordinate.")
                if not -5 <= point[0] <= width + 5 or not -5 <= point[1] <= height + 5:
                    raise ValueError("Coordinate outside input crop.")
            radius = shape["radius"]
            if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not math.isfinite(radius):
                raise ValueError("Invalid radius.")
            if kind == "circle" and not 0.1 <= radius <= min(width, height) / 2:
                raise ValueError("Circle radius outside budget.")
            if kind != "circle" and radius != 0:
                raise ValueError("Only circles use radius.")
            if kind not in {"polyline", "circle"} and shape["closed"]:
                raise ValueError("Only polylines and circles may be closed.")
            if kind != "circle" and any(math.dist(first, second) < 0.01 for first, second in zip(points, points[1:])):
                raise ValueError("Degenerate adjacent points.")
            shapes_count += 1
            segments_count += len(points) if kind == "polyline" else 1
    if shapes_count > 180 or segments_count > 450:
        raise ValueError("Geometry budget exceeded.")


def compile_model(model, width, height):
    validate_model(model, width, height)
    entities = []
    meanings = {}
    def convert(point):
        return [point[0] * 0.25, (height - point[1]) * 0.25]
    for component in model["components"]:
        name = component["id"]
        meanings[name] = component["meaning"]
        index = 0
        for shape in component["shapes"]:
            kind = shape["type"]
            points = [convert(point) for point in shape["points"]]
            generated = []
            if kind == "circle":
                generated.append({"type": "circle", "center": points[0], "radius": shape["radius"] * 0.25})
            elif kind == "spline":
                generated.append({"type": "spline", "fit_points": points})
            else:
                pairs = list(zip(points, points[1:]))
                if shape["closed"] and math.dist(points[-1], points[0]) >= 0.0025:
                    pairs.append((points[-1], points[0]))
                for first, second in pairs:
                    generated.append({"type": "line", "start": first, "end": second})
            for entity in generated:
                entity.update(id="E" + str(len(entities) + 1).zfill(4), component=name, geometry_index=index)
                entities.append(entity)
                index += 1
    return {"entities": entities, "component_meanings": meanings, "units": "mm",
            "unit_status": "Display coordinates only: 0.25 drawing units per raster pixel; physical dimensions not established.",
            "human_confirmation": False, "status": "needs_review"}


def process(command, output, environment, timeout):
    started = time.perf_counter()
    with (output / "stdout.log").open("w", encoding="utf-8") as stdout, (output / "stderr.log").open("w", encoding="utf-8") as stderr:
        child = subprocess.Popen(command, env=environment, cwd=ROOT, stdout=stdout, stderr=stderr)
        print(json.dumps({"event": "process_started", "pid": child.pid, "timeout_seconds": timeout, "output": str(output)}), flush=True)
        try:
            while True:
                remaining = timeout - (time.perf_counter() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    code = child.wait(timeout=min(120, remaining))
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.perf_counter() - started
                    state = {"event": "process_check", "pid": child.pid, "elapsed_seconds": elapsed,
                             "timeout_seconds": timeout, "output": str(output)}
                    worker_progress = output / "worker-progress.json"
                    if worker_progress.exists():
                        try:
                            state["worker"] = json.loads(worker_progress.read_text())
                            state["worker_progress_age_seconds"] = time.time() - worker_progress.stat().st_mtime
                        except (OSError, ValueError):
                            state["worker"] = "progress receipt temporarily unavailable"
                    save(output / "progress.json", state)
                    print(json.dumps(state), flush=True)
                    if elapsed >= timeout:
                        raise
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True, timeout=15)
            child.wait(timeout=10)
            save(output / "process.json", {"status": "timeout", "pid": child.pid, "seconds": time.perf_counter() - started})
            raise RuntimeError("Owned CAD process timed out.")
    metrics = {"pid": child.pid, "exit_code": code, "seconds": time.perf_counter() - started}
    save(output / "process.json", metrics)
    if code:
        raise RuntimeError("CAD command failed; inspect local stderr.log.")
    return metrics


def build(model_path, output, backend):
    output.mkdir()
    profile = output / "profile"
    profile.mkdir()
    environment = dict(os.environ, CAD_AGENT_MODEL=str(model_path), CAD_AGENT_OUTPUT=str(output),
                       FREECAD_USER_HOME=str(profile), APPDATA=str(profile), LOCALAPPDATA=str(profile),
                       PYTHONDONTWRITEBYTECODE="1")
    started = time.perf_counter()
    if backend == "freecad-direct":
        environment["CAD_AGENT_DIRECT"] = "1"
        command = ["C:/Program Files/FreeCAD 1.1/bin/FreeCAD.exe", "--user-cfg", str(profile / "user.cfg"),
                   "--system-cfg", str(profile / "system.cfg"), str(ROOT / "scripts/freecad/agent_build.FCMacro")]
        process(command, output, environment, 100)
    elif backend == "freecad-mcp":
        candidate = environment.get("CAD_AGENT_MCP_CANDIDATE", "neka")
        command = [str(Path("C:/code/FreecadMCP/.lab/envs") / candidate / "Scripts/python.exe"), "-B", str(ROOT / "scripts/agent_mcp_worker.py"), str(output)]
        process(command, output, environment, 140)
    else:
        command = ["C:/Program Files/QCAD/qcadcmd.com", "-no-gui", "-allow-multiple-instances", "-config", str(profile),
                   "-autostart", str(ROOT / "scripts/qcad/restart_view.js"), "-model=" + str(model_path),
                   "-output=" + str(output / "draft.dxf")]
        process(command, output, environment, 90)
        lines = (output / "stdout.log").read_text(encoding="utf-8").splitlines()
        result = json.loads(next(line.split("=", 1)[1] for line in lines if line.startswith("CAD_AGENT_REPORT=")))
        save(output / "geometry.json", result)
        if result["status"] != "passed":
            raise RuntimeError("Native QCAD geometry validation failed: " + result.get("error", "unknown"))
        render = output / "render"
        render.mkdir()
        command = ["C:/Program Files/QCAD/qcadcmd.com", "-no-gui", "-allow-multiple-instances", "-config", str(profile),
                   "-autostart", "scripts/Pro/Tools/Dwg2Pdf/Dwg2Pdf.js", "dwg2pdf.bat", "-a", "-auto-orientation", "-n",
                   "-outfile=" + str(render / "preview.pdf"), str(output / "draft.dxf")]
        process(command, render, environment, 60)
        with pymupdf.open(render / "preview.pdf") as document:
            if len(document) != 1:
                raise RuntimeError("Expected one PDF render page.")
            pixmap = document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples).save(output / "preview.png")
    report = json.loads((output / "geometry.json").read_text(encoding="utf-8"))
    if report["status"] != "passed" or not report.get("reopened"):
        raise RuntimeError("CAD did not pass saved-file inspection: " + report.get("error", "unknown"))
    if len(report["entities"]) != len(json.loads(model_path.read_text())["entities"]):
        raise RuntimeError("Native entity count differs from compiled model.")
    with Image.open(output / "preview.png") as image:
        if ImageOps.grayscale(image).getextrema()[0] > 150:
            raise RuntimeError("Native preview is blank.")
    metrics = {"seconds": time.perf_counter() - started, "entities": len(report["entities"]),
               "geometry_status": report["status"], "backend": backend}
    save(output / "build.json", metrics)
    return metrics


def source_images(source, output):
    started = time.perf_counter()
    if source.suffix.lower() == ".pdf":
        with pymupdf.open(source) as document:
            if len(document) != 1:
                raise ValueError("Pilot supports one-page drawings only.")
            page = document[0]
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    else:
        image = Image.open(source).convert("RGB")
    image.save(output / "source-page.png")
    if source.stem != "disegno_05":
        raise ValueError("This measured pilot currently targets drawing 05 lower view only.")
    crop_box = [100, 445, 690, 662]
    view = image.crop(crop_box).resize((1180, 434))
    view.save(output / "source-view.png")
    save(output / "source.json", {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                  "crop_pixels_144dpi": crop_box, "view_pixels": list(view.size),
                                  "preprocessing_seconds": time.perf_counter() - started,
                                  "no_invented_physical_units": True})
    return view.size


def run_route(campaign, backend, config, size, seed=None):
    directory = campaign / backend
    directory.mkdir()
    started = time.perf_counter()
    client = AstraClient(config, directory / "inference")
    prior_seconds = 0
    if seed:
        prior = json.loads((seed / "result.json").read_text())
        prior_seconds = prior["total_seconds"]
        client.metrics = json.loads((seed / "inference/usage.json").read_text())
        client.total_tokens = sum((item.get("usage") or {}).get("total_tokens", 0) for item in client.metrics)
        for path in (seed / "inference").glob("*.json"):
            shutil.copy2(path, client.output / path.name)
        save(directory / "recovery.json", {"prior_route": str(seed), "prior_result": prior,
                                          "policy": "Reuse completed responses; retain original failed artifacts and call accounting."})
    builds = []
    result = {"backend": backend, "status": "failed", "review_status": "needs_review"}
    width, height = size
    skill = (ROOT / ".github/skills/technical-drawing-reconstruction/SKILL.md").read_text(encoding="utf-8")
    instructions = "Reconstruct only the lower orthographic view of this mechanical drawing in 2D. Do not create 3D. Preserve technical meaning, not scan stains or handwriting. No physical dimensions or human approval are established. "
    methods = {"qcad": "Native QCAD component blocks, line/circle/spline shapes; closed polyline intent becomes edges in a block. No persistent solver.",
               "freecad-direct": "Native FreeCAD component sketches with horizontal/vertical and radius constraints; native interpolating B-splines. No blanket fixed coordinates.",
               "freecad-mcp": "Same FreeCAD component sketches, executed through a guarded local MCP call. The model cannot execute Python or shell. No extra automatic image feedback beyond the common review."}
    try:
        print("Starting " + backend + " analysis", flush=True)
        if seed:
            analysis = json.loads((seed / "analysis.json").read_text())
        else:
            analysis = client.call("01-analysis", instructions + "Identify components, drafting conventions, uncertain readings and a construction plan. Cropped lower view is " + str(width) + "x" + str(height) + " pixels.\n" + skill,
                                   [campaign / "source-page.png", campaign / "source-view.png"], PLAN_SCHEMA, config["analysis_max_output_tokens"])
        save(directory / "analysis.json", analysis)
        prompt = instructions + "\nBackend method: " + methods[backend] + "\nPlan: " + json.dumps(analysis)
        prompt += "\nReturn a component model using crop pixel coordinates: origin top-left, x right, y down, width=" + str(width) + ", height=" + str(height) + "."
        prompt += " Use at most 130 shapes, 350 polyline edges, and 25 components. IDs ASCII letters/numbers/underscore. For line use exactly 2 points; circle exactly 1 center and positive radius; polyline 2-60 vertices, closed optionally true; spline 3-12 distinct fit points, closed false. All non-circle radii=0. Don't duplicate closing point. Prefer compact connected polylines for body/fittings, splines for genuinely curved chamfer profiles, circles only with supported meaning. Axes must be distinct components with long/short dash segments. Copy both lateral fittings and the central body, avoiding arbitrary standard-size replacement. Do not include dimension labels or explanatory text entities."
        if seed:
            response = json.loads((seed / "inference/02-generation-response.json").read_text())
            if response.get("status") != "completed":
                raise RuntimeError("Cannot recover an incomplete generation.")
            model = json.loads("".join(item["text"] for message in response["output"] if message.get("type") == "message"
                                       for item in message.get("content", []) if item.get("type") == "output_text"))
        else:
            model = client.call("02-generation", prompt, [campaign / "source-view.png"], MODEL_SCHEMA)
        validate_model(model, width, height)
        save(directory / "model-initial.json", model)
        compiled = compile_model(model, width, height)
        save(directory / "compiled-initial.json", compiled)
        print("Building " + backend + " initial: " + str(len(compiled["entities"])) + " entities", flush=True)
        try:
            builds.append(build(directory / "compiled-initial.json", directory / "cad-initial", backend))
            preview = directory / "cad-initial/preview.png"
            feedback = "Native construction passed and saved files reopened. This proves geometry execution only, not mechanical meaning."
        except Exception as error:
            preview = None
            feedback = str(error)
            result["initial_build_error"] = feedback
        if time.perf_counter() - started > config["route_timeout_seconds"] - config["request_timeout_seconds"]:
            raise RuntimeError("Route time budget exhausted before review.")
        print("Reviewing " + backend + " with Astra", flush=True)
        review_prompt = instructions + " Compare the original crop with the native CAD render if supplied. Check nut faceting/chamfer interpretation, body corner shape, missing/open contours, concentric details, axes and component connectivity.\nBackend: " + methods[backend]
        review_prompt += "\nExecution feedback: " + feedback + "\nCurrent model: " + json.dumps(model)
        review_prompt += "\nReturn assessment, revise true/false and the full corrected model (or unchanged model if revise=false). Keep all coordinate and geometry budgets and shape conventions from generation. No human approval. This is the only correction allowed."
        images = [campaign / "source-view.png"] + ([preview] if preview else [])
        review = client.call("03-review", review_prompt, images, REVIEW_SCHEMA)
        validate_model(review["model"], width, height)
        save(directory / "review.json", review)
        final_model = review["model"] if review["revise"] or preview is None else model
        save(directory / "model-final.json", final_model)
        final_directory = directory / "cad-initial"
        if review["revise"] or preview is None:
            save(directory / "compiled-final.json", compile_model(final_model, width, height))
            print("Building " + backend + " corrected model", flush=True)
            builds.append(build(directory / "compiled-final.json", directory / "cad-final", backend))
            final_directory = directory / "cad-final"
        result.update(status="executed", final_cad_directory=str(final_directory), assessment=review["assessment"],
                      corrected=bool(review["revise"]), model_source="Independent live Astra interpretation, not a prewritten drawing template.")
    except Exception as error:
        result.update(status="failed", error=str(error))
    finally:
        result.update(total_seconds=prior_seconds + time.perf_counter() - started, recovery_prior_seconds=prior_seconds, model_calls=len(client.metrics),
                      inference_seconds=sum(item["seconds"] for item in client.metrics), builds=builds,
                      input_tokens=sum((item.get("usage") or {}).get("input_tokens", 0) for item in client.metrics),
                      cached_input_tokens=sum((item.get("usage") or {}).get("input_tokens_details", {}).get("cached_tokens", 0) for item in client.metrics),
                      output_tokens=sum((item.get("usage") or {}).get("output_tokens", 0) for item in client.metrics),
                      reasoning_tokens=sum((item.get("usage") or {}).get("output_tokens_details", {}).get("reasoning_tokens", 0) for item in client.metrics),
                      usage_complete=all(item.get("usage") is not None for item in client.metrics),
                      cad_seconds=sum(item["seconds"] for item in builds), monetary_cost_usd=None)
        save(directory / "result.json", result)
        print(json.dumps(result, indent=2), flush=True)
    return result


def comparison(campaign, results):
    gallery = ROOT / "comparisons" / ("astra-agents-" + uuid4().hex[:8])
    gallery.mkdir(parents=True)
    source = Image.open(campaign / "source-view.png").convert("RGB")
    sheet = Image.new("RGB", (1800, 1100), "#eceff1")
    draw = ImageDraw.Draw(sheet)
    panels = [("Original lower view", source)]
    for result in results:
        image = None
        label = result["backend"] + " / " + result["status"]
        if result["status"] == "executed":
            image = Image.open(Path(result["final_cad_directory"]) / "preview.png").convert("RGB")
        elif result.get("builds"):
            fallback = campaign / result["backend"] / "cad-initial"
            report = json.loads((fallback / "geometry.json").read_text())
            if report.get("status") == "passed" and report.get("reopened"):
                image = Image.open(fallback / "preview.png").convert("RGB")
                label += " / INITIAL ONLY, review incomplete"
        if image is not None:
            mask = ImageChops.difference(image, Image.new("RGB", image.size, "white")).convert("L").point(lambda value: 255 if value > 50 else 0)
            box = mask.getbbox()
            if box:
                image = image.crop(box)
        panels.append((label, image))
    for index, (label, image) in enumerate(panels):
        left = (index % 2) * 900
        top = (index // 2) * 500
        draw.text((left + 20, top + 25), label, fill="black")
        if image:
            tile = ImageOps.contain(image, (850, 380))
            sheet.paste(tile, (left + (900 - tile.width) // 2, top + 90 + (380 - tile.height) // 2))
        else:
            draw.text((left + 20, top + 160), "FAILED: see local result.json; no invented output", fill="#a51b36")
    budget_label = "Direct route includes one authorized extra request; call budgets differ." if any(item.get("additional_authorized_requests") for item in results) else "Same source, effort and call budget."
    draw.text((20, 1030), "Independent Astra runs. " + budget_label + " No human-approved dimensions or semantic scores.", fill="#a51b36")
    draw.text((20, 1060), "Native geometry persisted; visual fit-to-panel is not metric accuracy. Failed routes remain visible.", fill="#a51b36")
    sheet.save(gallery / "01-source-and-three-agents.png")
    board = Image.new("RGB", (1600, 580), "white")
    painter = ImageDraw.Draw(board)
    painter.text((25, 25), "ACTUAL ASTRA USAGE AND LOCAL EXECUTION: one independent pilot per route", fill="black")
    headers = ["Route", "Status", "Total s", "Inference s", "CAD s", "Input", "Cached", "Output", "Reasoning"]
    positions = [20, 250, 430, 580, 750, 900, 1060, 1210, 1390]
    for position, header in zip(positions, headers):
        painter.text((position, 100), header, fill="black")
    for index, result in enumerate(results):
        values = [result["backend"], result["status"], f"{result['total_seconds']:.2f}", f"{result['inference_seconds']:.2f}",
                  f"{result['cad_seconds']:.2f}", str(result["input_tokens"]) + ("+?" if not result["usage_complete"] else ""), str(result["cached_input_tokens"]),
                  str(result["output_tokens"]) + ("+?" if not result["usage_complete"] else ""), str(result["reasoning_tokens"])]
        for position, value in zip(positions, values):
            painter.text((position, 170 + index * 75), value, fill="black")
    painter.text((20, 440), "Cached input is included in input; reasoning is included in output. Usage from provider, not estimates or billing.", fill="black")
    painter.text((20, 475), "Total includes authentication and inference + build/review. CAD total is successful builds only; inspect failures separately.", fill="black")
    painter.text((20, 510), "+? = timed-out call usage unknown. Dollar cost unknown. Independent generations prevent backend-only causal ranking.", fill="#a51b36")
    board.save(gallery / "02-measured-time-and-token-comparison.png")
    return gallery


def report_campaign(directory):
    summary = json.loads((directory / "summary.json").read_text())
    source = json.loads((directory / "source.json").read_text())
    lines = ["# Local Astra Three-Route Pilot", "", "All outputs require human technical review. Physical dimensions are unconfirmed.", "",
             "| Route | Status | Calls | Total s | Inference s | Successful CAD s | Input | Cached | Output | Reasoning |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for result in summary["results"]:
        lines.append("| " + " | ".join([result["backend"], result["status"], str(result["model_calls"]),
                     f"{result['total_seconds']:.2f}", f"{result['inference_seconds']:.2f}", f"{result['cad_seconds']:.2f}",
                     str(result["input_tokens"]), str(result["cached_input_tokens"]), str(result["output_tokens"]),
                     str(result["reasoning_tokens"])]) + " |")
    lines.extend(["", "Cached input is included in input; reasoning is included in output. Provider usage is not a bill. Dollar cost is unknown.",
                  "Protocol: " + summary["protocol"],
                  "Recovery elapsed time includes the prior failed attempt, but not idle time between attempts. Initial exhausted-budget campaign and preflight are separate evidence.",
                  "One independent model run per route, fixed order QCAD/direct/MCP: model variance, cache and inference latency confound backend-only rankings.", "",
                  "Source preprocessing: " + str(source["preprocessing_seconds"]) + " seconds (shared, outside route timing).", "",
                  "Source SHA256: " + source["sha256"], "",
                  "[Image-only comparison](" + Path(os.path.relpath(summary["gallery"], directory)).as_posix() + ")", ""])
    for result in summary["results"]:
        lines.extend(["## " + result["backend"], "", result.get("assessment", result.get("error", "No semantic assessment.")), ""])
        if not result["usage_complete"]:
            lines.extend(["Token counts above cover received responses only. Timed-out request usage is UNKNOWN, not zero.", ""])
        if result["status"] == "executed" or result.get("builds"):
            cad = Path(result["final_cad_directory"]) if result["status"] == "executed" else directory / result["backend"] / "cad-initial"
            if result["status"] != "executed":
                lines.extend(["INITIAL DRAFT ONLY: native construction passed, but model review did not complete. Not a successful full agent route.", ""])
            geometry = json.loads((cad / "geometry.json").read_text())
            native = cad / ("draft.dxf" if result["backend"] == "qcad" else "draft.FCStd")
            lines.extend(["[Native CAD](" + Path(os.path.relpath(native, directory)).as_posix() + ")",
                          "[Reopened geometry checks](" + Path(os.path.relpath(cad / "geometry.json", directory)).as_posix() + ")", "",
                          "Entities: " + str(len(geometry["entities"])) + "; reopened: " + str(geometry["reopened"]) + ".",
                          "Constraints: " + str(geometry.get("constraints", "not applicable")) + "; fully constrained components: " + str(geometry.get("fully_constrained_components", "not applicable")) + ".", ""])
            if (cad / "mcp-metrics.json").exists():
                metrics = json.loads((cad / "mcp-metrics.json").read_text())
                lines.extend(["MCP final-build initialization: " + str(metrics["initialize_seconds"]) + " s; guarded CAD tool call: " + str(metrics["cad_call_seconds"]) + " s.", ""])
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(str(directory / "report.md"))


def complete_direct_review(previous):
    old_summary = json.loads((previous / "summary.json").read_text())
    old_result = next(item for item in old_summary["results"] if item["backend"] == "freecad-direct")
    if old_result["status"] != "failed" or not old_result.get("builds") or old_result["model_calls"] != 3:
        raise ValueError("Expected a failed three-call route with a validated initial draft.")
    initial = previous / "freecad-direct/cad-initial"
    geometry = json.loads((initial / "geometry.json").read_text())
    if geometry["status"] != "passed" or not geometry["reopened"]:
        raise ValueError("Initial draft has not passed native reopening checks.")
    output = ROOT / "work" / ("astra-campaign-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    output.mkdir()
    for name in ("source-page.png", "source-view.png", "source.json"):
        shutil.copy2(previous / name, output / name)
    config = json.loads((previous / "config.json").read_text())
    config.update(max_calls_per_route=4, request_timeout_seconds=900)
    save(output / "config.json", config)
    directory = output / "freecad-direct"
    directory.mkdir()
    save(directory / "authorization.json", {"additional_requests": 1, "reason": "User authorized completion after review timeout.",
                                           "prior_campaign": str(previous), "prior_result": old_result})
    model = json.loads((previous / "freecad-direct/model-initial.json").read_text())
    size = json.loads((output / "source.json").read_text())["view_pixels"]
    client = AstraClient(config, directory / "inference")
    client.metrics = json.loads((previous / "freecad-direct/inference/usage.json").read_text())
    client.total_tokens = sum((item.get("usage") or {}).get("total_tokens", 0) for item in client.metrics)
    result = dict(old_result)
    result["builds"] = list(old_result["builds"])
    started = time.perf_counter()
    lock = ROOT / "work/.astra-campaign.lock"
    with lock.open("x") as handle:
        handle.write(str(os.getpid()))
    try:
        prompt = "Review this lower orthographic mechanical view in 2D only. Compare the source crop and native FreeCAD initial render. Check continuous nut envelopes, projected facets/chamfers, body corners, circles, connectivity and separate axes. Physical dimensions and human approval are unconfirmed. Return assessment, revise and the full corrected model, or unchanged model if no revision. Coordinates are crop pixels, origin top-left, size " + str(size) + ". Use only line, polyline, circle and spline; non-circle radius zero; closed only circles/polylines. Keep at most 180 shapes and 450 edges. Do not execute code. Current model: " + json.dumps(model)
        print("Starting authorized fourth request: direct FreeCAD review", flush=True)
        review = client.call("04-authorized-review", prompt, [output / "source-view.png", initial / "preview.png"], REVIEW_SCHEMA)
        validate_model(review["model"], *size)
        save(directory / "review.json", review)
        final_model = review["model"] if review["revise"] else model
        save(directory / "model-final.json", final_model)
        final = initial
        if review["revise"]:
            save(directory / "compiled-final.json", compile_model(final_model, *size))
            print("Building authorized corrected FreeCAD model", flush=True)
            result["builds"].append(build(directory / "compiled-final.json", directory / "cad-final", "freecad-direct"))
            final = directory / "cad-final"
        result.pop("error", None)
        result.update(status="executed", final_cad_directory=str(final), assessment=review["assessment"], corrected=review["revise"],
                      additional_authorized_requests=1)
    except Exception as error:
        result.update(status="failed", error=str(error))
    finally:
        lock.unlink()
        result.update(total_seconds=old_result["total_seconds"] + time.perf_counter() - started, model_calls=len(client.metrics),
                      inference_seconds=sum(item["seconds"] for item in client.metrics), usage_complete=False,
                      cad_seconds=sum(item["seconds"] for item in result["builds"]))
        for field, detail in (("input_tokens", None), ("output_tokens", None), ("cached_input_tokens", "input_tokens_details"), ("reasoning_tokens", "output_tokens_details")):
            key = "cached_tokens" if field == "cached_input_tokens" else "reasoning_tokens" if detail else field
            result[field] = sum(((item.get("usage") or {}).get(detail, {}) if detail else (item.get("usage") or {})).get(key, 0) for item in client.metrics)
        save(directory / "result.json", result)
    results = [result if item["backend"] == "freecad-direct" else item for item in old_summary["results"]]
    save(output / "results.json", results)
    gallery = comparison(output, results)
    save(output / "summary.json", dict(old_summary, results=results, gallery=str(gallery),
                                      protocol="Original three-call protocol plus one user-authorized direct review; timeout usage remains unknown."))
    report_campaign(output)
    print(json.dumps({"campaign": str(output), "gallery": str(gallery), "all_executed": all(item["status"] == "executed" for item in results), "direct": result}, indent=2))


def campaign(config_path, source, resume=None):
    config = json.loads(config_path.read_text())
    output = ROOT / "work" / ("astra-campaign-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    output.mkdir(parents=True)
    save(output / "config.json", config)
    if resume:
        config = json.loads((resume / "config.json").read_text())
        save(output / "config.json", config)
        for name in ("source-page.png", "source-view.png", "source.json"):
            shutil.copy2(resume / name, output / name)
        size = tuple(json.loads((output / "source.json").read_text())["view_pixels"])
        previous = {item["backend"]: item for item in json.loads((resume / "results.json").read_text())}
    else:
        size = source_images(source, output)
    results = []
    lock = ROOT / "work/.astra-campaign.lock"
    with lock.open("x") as handle:
        handle.write(str(os.getpid()))
    try:
        for backend in BACKENDS:
            if resume and previous[backend]["status"] == "executed":
                results.append(previous[backend])
            else:
                seed = resume / backend if resume else None
                if seed and not (seed / "inference/02-generation-response.json").exists():
                    results.append(previous[backend])
                else:
                    results.append(run_route(output, backend, config, size, seed))
            save(output / "results.json", results)
    finally:
        lock.unlink()
    gallery = comparison(output, results)
    save(output / "summary.json", {"results": results, "gallery": str(gallery), "source": str(source),
                                  "protocol": "Independent analysis/generation/review per route, high effort, max 3 calls and one correction; no arbitrary code execution.",
                                  "sample_count_per_route": 1, "human_approval": False})
    print(json.dumps({"campaign": str(output), "gallery": str(gallery), "all_executed": all(result["status"] == "executed" for result in results)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local Astra-driven 2D CAD pilot with three deterministic backend routes.")
    parser.add_argument("--config", type=Path, default=ROOT / "config/astra-local.json")
    parser.add_argument("--source", type=Path, default=ROOT / "disegni/disegno_05.pdf")
    parser.add_argument("--resume-campaign", type=Path)
    parser.add_argument("--report-campaign", type=Path)
    parser.add_argument("--complete-direct-review", type=Path)
    args = parser.parse_args()
    if args.complete_direct_review:
        complete_direct_review(args.complete_direct_review.resolve())
    elif args.report_campaign:
        report_campaign(args.report_campaign.resolve())
    else:
        campaign(args.config.resolve(), args.source.resolve(), args.resume_campaign.resolve() if args.resume_campaign else None)