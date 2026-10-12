import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from uuid import uuid4

import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageOps

from astra_client import AstraClient
from astra_cad_agent import ROOT, MODEL_SCHEMA, PLAN_SCHEMA, build, compile_model, process, save, validate_model


METHODS = ("qcad", "freecad-direct", "freecad-neka", "freecad-robust")
EVALUATION = {"type": "object", "properties": {
    "accepted": {"type": "boolean"}, "score": {"type": "integer"},
    "assessment": {"type": "string"}, "defects": {"type": "array", "items": {"type": "string"}},
    "correction_instructions": {"type": "string"}},
    "required": ["accepted", "score", "assessment", "defects", "correction_instructions"], "additionalProperties": False}


def prepare(output):
    output.mkdir(parents=True)
    for drawing in ("01", "05", "07"):
        source = ROOT / "drawings" / ("disegno_" + drawing + ".pdf")
        directory = output / drawing
        directory.mkdir()
        with pymupdf.open(source) as document:
            pixels = document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pixels.width, pixels.height), pixels.samples)
        image.save(directory / "page.png")
        save(directory / "source.json", {"source": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "page": 1, "raster_size": list(image.size)})
    print(str(output), flush=True)


def initialize(inputs, output):
    crops = {"01": [210, 470, 650, 755], "05": [100, 445, 690, 662], "07": [280, 225, 560, 690]}
    output.mkdir()
    for drawing, crop in crops.items():
        source = output / drawing / "source"
        source.mkdir(parents=True)
        shutil.copy2(inputs / drawing / "page.png", source / "page.png")
        metadata = json.loads((inputs / drawing / "source.json").read_text())
        image = Image.open(source / "page.png").convert("RGB").crop(crop)
        image = ImageOps.contain(image, (1200, 1200)) if max(image.size) > 1200 else image.resize((round(image.width * 1200 / max(image.size)), round(image.height * 1200 / max(image.size))))
        image.save(source / "view.png")
        save(source / "source.json", dict(metadata, crop_pixels_144dpi=crop, view_size=list(image.size)))
    save(output / "protocol.json", {"drawings": list(crops), "methods": list(METHODS), "independence": "Only original rasters shared; fresh stateless model calls and isolated native profiles per route.", "maximum_models_per_route": 4, "acceptance_score": 85, "human_approval": False})
    print(str(output))


def heartbeat(directory, state, stop):
    if stop.is_set():
        return
    receipt = dict(state, elapsed_seconds=time.perf_counter() - state["started"])
    receipt.pop("started", None)
    save(directory / "worker-progress.json", receipt)
    print(json.dumps(receipt), flush=True)
    timer = threading.Timer(120, heartbeat, args=(directory, state, stop))
    timer.daemon = True
    timer.start()


def worker(directory, method, config_path=None):
    state = {"phase": "starting", "method": method, "started": time.perf_counter()}
    stop = threading.Event()
    heartbeat(directory, state, stop)
    config = json.loads((config_path or ROOT / "config/astra-local.json").read_text())
    config.update(max_calls_per_route=12, max_total_tokens_per_route=250000, max_output_tokens=24000,
                  request_timeout_seconds=600)
    if config_path:
        config.update(json.loads(config_path.read_text()))
    save(directory / "config.json", config)
    client = AstraClient(config, directory / "inference")
    evaluator_config = dict(config, deployment=config.get("evaluator_deployment", config["deployment"]))
    evaluator = AstraClient(evaluator_config, directory / "evaluation-inference") if config_path else client
    native_qcad = method == "qcad" and config.get("native_qcad", False)
    generation_schema = MODEL_SCHEMA
    qcad_guidance = ""
    if native_qcad:
        from qcad_model import QCAD_SCHEMA, GUIDANCE, compile_qcad
        generation_schema = QCAD_SCHEMA
        qcad_guidance = GUIDANCE
    def request(phase, *args, client_target=None):
        target = client_target or client
        for retry in range(2):
            try:
                return target.call(phase + ("-retry" if retry else ""), *args)
            except Exception as error:
                save(directory / (phase + "-request-error-" + str(retry) + ".json"), {"error": str(error), "usage_may_be_unknown": True})
                if retry or len(target.metrics) >= config["max_calls_per_route"]:
                    raise
                state["phase"] = "bounded_request_recovery"
    view = directory.parent / "source/view.png"
    page = directory.parent / "source/page.png"
    with Image.open(view) as image:
        width, height = image.size
    skill = (ROOT / ".github/skills/technical-drawing-reconstruction/SKILL.md").read_text()
    model = None
    feedback = ""
    evaluations = []
    builds = []
    result = {"method": method, "status": "failed", "human_approval": False, "review_status": "needs_review"}
    def checkpoint(phase):
        state["phase"] = phase
        save(directory / "checkpoint.json", dict(result, status="running", phase=phase,
             elapsed_seconds=time.perf_counter() - state["started"], evaluations=evaluations, builds=builds,
             generator_calls=len(client.metrics), evaluator_calls=len(evaluator.metrics)))
    conventions = "2D only, crop pixel coordinates, origin top-left, size " + str([width, height]) + ". IDs ASCII letters/digits/underscore. Lines exactly 2 points, circles one center and radius, polylines 2-80 points, splines 3-12 distinct fit points. Noncircle radius zero, closed only polyline/circle. At most 180 shapes, 450 edges, 30 components. Separate conventional axes/hidden lines with explicit segments. No dimension text, title blocks, handwriting or scan stains. No physical units or human approval established."
    coverage = config.get("coverage_instruction", "Interpret only the selected view, use page for context.")
    conventions += " " + coverage + " Model whole components before edges. Never use projected chamfer curves as a scalloped nut silhouette; separate continuous outer envelopes from internal facet/chamfer intersections when supported by the original."
    conventions += "\n" + qcad_guidance
    try:
        state["phase"] = "independent_analysis"
        plan = request("01-analysis", coverage + " Explain components, contours, faceting/chamfers, every visible view and uncertain readings.\n" + skill,
                           [page, view], PLAN_SCHEMA, config.get("analysis_max_output_tokens", 10000))
        save(directory / "analysis.json", plan)
        checkpoint("analysis_saved")
        for attempt in range(1, 5):
            state.update(phase="generation_or_correction", attempt=attempt)
            prompt = "Generate an editable mechanical 2D component model for " + method + ". " + conventions + "\nPlan: " + json.dumps(plan)
            if model is not None:
                prompt += "\nCorrect your own previous model only: " + json.dumps(model) + "\nEvaluator/execution feedback: " + feedback
            raw = request(str(attempt) + "-generate", prompt, [view], generation_schema)
            model = raw
            save(directory / (str(attempt) + "-model.json"), model)
            checkpoint("model_saved")
            try:
                compiled = directory / (str(attempt) + "-compiled.json")
                compiled_model = compile_qcad(model, width, height) if native_qcad else compile_model(model, width, height)
                save(compiled, compiled_model)
                state["phase"] = "native_build"
                if method.startswith("freecad-") and method != "freecad-direct":
                    os.environ["CAD_AGENT_MCP_CANDIDATE"] = method.split("-")[1]
                    backend = "freecad-mcp"
                else:
                    backend = method
                cad = directory / ("cad-" + str(attempt))
                metrics = build(compiled, cad, backend)
                builds.append(dict(metrics, attempt=attempt, directory=str(cad)))
                result["last_valid_cad"] = str(cad)
                checkpoint("native_cad_saved_and_reopened")
            except Exception as error:
                feedback = "Native execution/model validator failure: " + str(error) + ". Repair the structured model; do not claim acceptance."
                save(directory / (str(attempt) + "-failure.json"), {"error": feedback})
                checkpoint("native_build_failed")
                continue
            state["phase"] = "independent_evaluation"
            hatch_review = ""
            if native_qcad:
                native_report = json.loads((cad / "geometry.json").read_text())
                hatch_count = sum(entity["type"] == "hatch" for entity in native_report["entities"])
                hatch_review = " Native checks passed. Native HATCH count=" + str(hatch_count) + ". Reject section views with missing material hatch or voids incorrectly hatched, wrong density/angle, or hatch strokes disguised as line entities. Dedicated layers and closed hatch-loop topology are checked by executor, but correct material interpretation must be checked visually. No hatch is required if the sheet genuinely contains no sectioned material."
            judgment = request(str(attempt) + "-evaluate",
                "Act as a strict independent drawing-quality evaluator. Images: original sheet/view, native reconstructed render. Do not generate geometry. Judge ALL views, mechanical meaning, proportions, continuous envelopes, chamfer/facet transitions, component connectivity, circular details and line conventions. Critically inspect union nuts: repeated scalloped silhouette where a continuous envelope and INTERNAL chamfer curves are required is a MAJOR defect; reject even when overall image looks similar. Missing legible views or components is a MAJOR defect. Ignore omitted labels/stains and unconfirmed absolute dimensions. Score 0-100. Accept only if score>=85 AND no major missing/incorrect mechanical features. Explicitly list actionable defects and evidence by view/component; reject visually plausible but mechanically wrong contours. Acceptance is internal only, never human approval. Fit-to-panel scale differences alone are not defects. Treat source ambiguities honestly. " + coverage + hatch_review,
                [view, cad / "preview.png"], EVALUATION, 10000, client_target=evaluator)
            if not isinstance(judgment["score"], int) or not 0 <= judgment["score"] <= 100:
                raise ValueError("Invalid evaluator score.")
            judgment["accepted"] = judgment["accepted"] and judgment["score"] >= 85
            evaluations.append(dict(judgment, attempt=attempt))
            save(directory / (str(attempt) + "-evaluation.json"), judgment)
            result.update(final_score=judgment["score"], assessment=judgment["assessment"])
            checkpoint("evaluation_saved")
            if judgment["accepted"]:
                result["status"] = "internally_accepted"
                break
            feedback = json.dumps(judgment)
        else:
            result["status"] = "not_accepted"
    except Exception as error:
        result["error"] = str(error)
    finally:
        stop.set()
        all_metrics = client.metrics + (evaluator.metrics if evaluator is not client else [])
        result.update(elapsed_seconds=time.perf_counter() - state["started"], evaluations=evaluations, builds=builds,
                  generator_deployment=config["deployment"], evaluator_deployment=evaluator_config["deployment"],
                  generator_calls=len(client.metrics), evaluator_calls=len(evaluator.metrics) if evaluator is not client else None,
                  calls=len(all_metrics), usage_complete=all(item.get("usage") is not None for item in all_metrics),
                  input_tokens=sum((item.get("usage") or {}).get("input_tokens", 0) for item in all_metrics),
                  output_tokens=sum((item.get("usage") or {}).get("output_tokens", 0) for item in all_metrics),
                  cached_tokens=sum((item.get("usage") or {}).get("input_tokens_details", {}).get("cached_tokens", 0) for item in all_metrics),
                  reasoning_tokens=sum((item.get("usage") or {}).get("output_tokens_details", {}).get("reasoning_tokens", 0) for item in all_metrics),
                      cost_usd=None, cost_status="Verified price schedule unavailable; provider usage retained.")
        save(directory / "result.json", result)
        print(json.dumps(result), flush=True)


def gallery(campaign):
    output = ROOT / "comparisons" / ("quality-twelve-" + uuid4().hex[:8])
    output.mkdir()
    rows = []
    for drawing in ("01", "05", "07"):
        sheet = Image.new("RGB", (2000, 1600), "#eceff1")
        painter = ImageDraw.Draw(sheet)
        source = Image.open(campaign / drawing / "source/view.png").convert("RGB")
        tile = ImageOps.contain(source, (1500, 400))
        sheet.paste(tile, ((2000 - tile.width) // 2, 35))
        painter.text((20, 10), "Drawing " + drawing + " / original selected view", fill="black")
        for index, method in enumerate(METHODS):
            directory = campaign / drawing / method
            result = json.loads((directory / "result.json").read_text())
            rows.append(dict(result, drawing=drawing, directory=str(directory)))
            left, top = index % 2 * 1000, 460 + index // 2 * 520
            painter.text((left + 20, top), method + " / " + result["status"] + " / score " + str(result.get("final_score", "unknown")), fill="black")
            if result.get("last_valid_cad"):
                image = Image.open(Path(result["last_valid_cad"]) / "preview.png").convert("RGB")
                mask = ImageChops.difference(image, Image.new("RGB", image.size, "white")).convert("L").point(lambda value: 255 if value > 50 else 0)
                box = mask.getbbox()
                if box:
                    image = image.crop(box)
                tile = ImageOps.contain(image, (950, 430))
                sheet.paste(tile, (left + (1000 - tile.width) // 2, top + 50 + (430 - tile.height) // 2))
            else:
                painter.text((left + 20, top + 150), "No validated CAD output; see failure receipts", fill="#a51b36")
        painter.text((20, 1540), "Independent runs: no models, intermediate CAD or evaluations shared between methods. Scores are model judgments, not metrology.", fill="#a51b36")
        painter.text((20, 1570), "Physical dimensions unconfirmed; human review required. Last validated output shown even when evaluator rejected it.", fill="#a51b36")
        sheet.save(output / (drawing + "-four-methods.png"))
    save(campaign / "results.json", rows)
    save(campaign / "summary.json", {"gallery": str(output), "results": rows, "completed_routes": len(rows), "internally_accepted": sum(item["status"] == "internally_accepted" for item in rows)})
    lines = ["# Independent Twelve-Route Quality Campaign", "", "Internal evaluator acceptance is not human approval. All drafts require review.", "",
             "| Drawing | Method | Outcome | Score | Calls | Seconds | Input | Cached | Output | Reasoning |", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for item in rows:
        lines.append("| " + " | ".join(str(value) for value in (item["drawing"], item["method"], item["status"], item.get("final_score", "unknown"), item.get("calls", 0), round(item.get("elapsed_seconds", 0), 2), item.get("input_tokens", "unknown"), item.get("cached_tokens", "unknown"), item.get("output_tokens", "unknown"), item.get("reasoning_tokens", "unknown"))) + " |")
    lines.extend(["", "Each route independently analyzes, generates, builds and evaluates. At most four candidate models; every corrected model is rerendered and reevaluated. Stateless evaluator requests do not receive generator reasoning or other methods' results. Same model provider may have correlated judgment errors.", "", "Hard per-route deadline: 3,600 seconds; request read timeout: 600 seconds; owned CAD deadlines unchanged. Progress logged every 120 seconds; timeout does not establish provider cancellation or zero cost. Missing usage is unknown. Dollar costs require verified pricing; user-reported $5 historical spend is not measured by this runner.", "", "[Comparison gallery](" + Path(os.path.relpath(output, campaign)).as_posix() + ")", ""])
    for item in rows:
        lines.extend(["## Drawing " + item["drawing"] + " / " + item["method"], "", item.get("assessment", item.get("error", "No evaluation completed.")), ""])
        if item.get("last_valid_cad"):
            cad = Path(item["last_valid_cad"])
            native = cad / ("draft.dxf" if item["method"] == "qcad" else "draft.FCStd")
            lines.extend(["[Native CAD](" + Path(os.path.relpath(native, campaign)).as_posix() + ")", ""])
    (campaign / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"campaign": str(campaign), "gallery": str(output), "routes": len(rows)}), flush=True)


def details(campaign):
    summary = json.loads((campaign / "summary.json").read_text())
    output = Path(summary["gallery"])
    for drawing, region in (("05", (0.07, 0.08, 0.28, 0.94)), ("07", (0.0, 0.27, 1.0, 0.64))):
        sheet = Image.new("RGB", (1800, 1100), "#eceff1")
        painter = ImageDraw.Draw(sheet)
        for index, method in enumerate(METHODS):
            result = json.loads((campaign / drawing / method / "result.json").read_text())
            image = Image.open(Path(result["last_valid_cad"]) / "preview.png").convert("RGB")
            mask = ImageChops.difference(image, Image.new("RGB", image.size, "white")).convert("L").point(lambda value: 255 if value > 50 else 0)
            box = mask.getbbox()
            if box:
                image = image.crop(box)
            crop = tuple(round(value * (image.width if position % 2 == 0 else image.height)) for position, value in enumerate(region))
            tile = ImageOps.contain(image.crop(crop), (850, 430))
            left, top = index % 2 * 900, index // 2 * 510
            sheet.paste(tile, (left + (900 - tile.width) // 2, top + 60 + (430 - tile.height) // 2))
            painter.text((left + 20, top + 20), "Drawing " + drawing + " / " + method, fill="black")
        painter.text((20, 1040), "Relative native-render detail crops, not calibrated metrology. Compare with original in overview sheet.", fill="#a51b36")
        painter.text((20, 1070), "Internal acceptance is fallible: inspect nut envelope/chamfer meaning and knurl conventions independently.", fill="#a51b36")
        sheet.save(output / (drawing + "-details.png"))
    print(str(output))


def run(campaign):
    lock = ROOT / "work/.astra-campaign.lock"
    with lock.open("x") as handle:
        handle.write(str(os.getpid()))
    try:
        for drawing in ("01", "05", "07"):
            for method in METHODS:
                directory = campaign / drawing / method
                if (directory / "result.json").exists():
                    continue
                directory.mkdir(exist_ok=True)
                print("Starting drawing " + drawing + " / " + method, flush=True)
                try:
                    process([sys.executable, str(Path(__file__).resolve()), "worker", str(directory), "--method", method], directory, dict(os.environ), 3600)
                except Exception as error:
                    if not (directory / "result.json").exists():
                        valid = sorted(directory.glob("cad-*/build.json"), key=lambda path: path.stat().st_mtime)
                        save(directory / "result.json", {"method": method, "status": "supervisor_failed", "error": str(error),
                                                         "last_valid_cad": str(valid[-1].parent) if valid else None, "usage_complete": False})
                save(campaign / "progress.json", {"drawing": drawing, "method": method, "completed": len(list(campaign.glob("*/*/result.json"))), "time": time.time()})
    finally:
        lock.unlink()
    gallery(campaign)


async def observe(campaign):
    loop = asyncio.get_running_loop()
    finished = loop.create_future()
    def check():
        try:
            results = []
            for path in campaign.glob("*/*/result.json"):
                result = json.loads(path.read_text())
                results.append({"drawing": path.parents[1].name, "method": result["method"], "status": result["status"], "score": result.get("final_score")})
            active = []
            for path in campaign.glob("*/*/worker-progress.json"):
                if not (path.parent / "result.json").exists():
                    active.append(dict(json.loads(path.read_text()), receipt_age_seconds=time.time() - path.stat().st_mtime))
            state = {"time": time.time(), "completed": len(results), "results": results, "active": active}
            with (campaign / "monitor.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(state) + "\n")
            print(json.dumps(state), flush=True)
            if (campaign / "summary.json").exists():
                print((campaign / "summary.json").read_text(), flush=True)
                finished.set_result(None)
            else:
                loop.call_later(120, check)
        except Exception as error:
            finished.set_exception(error)
    check()
    await finished


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "initialize", "run", "worker", "gallery", "details", "observe"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--method", choices=METHODS)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--config", type=Path)
    arguments = parser.parse_args()
    directory = arguments.directory.resolve()
    if arguments.action == "prepare":
        prepare(directory)
    elif arguments.action == "initialize":
        initialize(arguments.inputs.resolve(), directory)
    elif arguments.action == "worker":
        worker(directory, arguments.method, arguments.config.resolve() if arguments.config else None)
    elif arguments.action == "gallery":
        gallery(directory)
    elif arguments.action == "observe":
        asyncio.run(observe(directory))
    elif arguments.action == "details":
        details(directory)
    else:
        run(directory)