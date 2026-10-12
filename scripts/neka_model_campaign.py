import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageOps

from astra_cad_agent import ROOT, process, save


MODELS = {"astra": ("lab-gpt-6-astra-20260919", "2026-09-03"),
          "sol": ("cad-gpt-6-1-sol-20261010", "2026-09-29")}


def prepare(campaign, backend="freecad-neka"):
    campaign.mkdir()
    files = sorted((ROOT / "disegni").glob("disegno_*"))
    if len(files) != 10:
        raise ValueError("Expected all ten original drawings.")
    inventory = []
    for path in files:
        drawing = path.stem.split("_")[-1]
        source = campaign / drawing / "source"
        source.mkdir(parents=True)
        pages = []
        if path.suffix.lower() == ".pdf":
            with pymupdf.open(path) as document:
                for page in document:
                    pixels = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                    pages.append(Image.frombytes("RGB", (pixels.width, pixels.height), pixels.samples))
        else:
            with Image.open(path) as document:
                for frame in range(document.n_frames):
                    document.seek(frame)
                    pages.append(document.convert("RGB").copy())
        rendered = []
        for index, image in enumerate(pages):
            image = ImageOps.contain(image, (1600, 1800))
            image.save(source / ("page-" + str(index + 1) + ".png"))
            rendered.append(image)
        canvas = Image.new("RGB", (max(image.width for image in rendered), sum(image.height for image in rendered)), "white")
        offset = 0
        for image in rendered:
            canvas.paste(image, (0, offset))
            offset += image.height
        canvas.save(source / "page.png")
        canvas.save(source / "view.png")
        receipt = {"drawing": drawing, "source": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "pages": len(pages), "view_size": list(canvas.size), "coverage": "All readable views, whole sheet; original page positions retained. No physical scale inferred."}
        save(source / "source.json", receipt)
        inventory.append(receipt)
    for name, (deployment, version) in MODELS.items():
        config = json.loads((ROOT / "config/astra-local.json").read_text())
        config.update(native_qcad=backend == "qcad", deployment=deployment, model_version=version, evaluator_deployment=MODELS["astra"][0],
                      max_total_tokens_per_route=None, max_calls_per_route=12, max_output_tokens=32000,
                      analysis_max_output_tokens=16000, request_timeout_seconds=900,
                      coverage_instruction="Reconstruct ALL readable orthographic, section and detail views of this whole sheet, maintaining their relative positions. Omit title block, dimensions/text, leaders and handwritten annotations. Identify unreadable or unsupported views explicitly; never silently omit a readable view. Use only 2D; this is a draft, no physical dimensions or human approval established.")
        save(campaign / (name + "-config.json"), config)
    save(campaign / "inventory.json", inventory)
    save(campaign / "protocol.json", {"models": MODELS, "backend": backend, "passes": 2,
                                       "order": "All originals with Astra, then all originals with Sol", "evaluator": MODELS["astra"][0],
                                       "token_cost_cap": None, "hard_route_timeout_seconds": 7200, "check_interval_seconds": 120,
                                       "model_training": False, "independence": "No intermediate models/CAD/evaluations copied between passes; only original rasters shared."})
    print(str(campaign), flush=True)


def summarize(campaign):
    inventory = json.loads((campaign / "inventory.json").read_text())
    backend = json.loads((campaign / "protocol.json").read_text()).get("backend", "freecad-neka")
    gallery = ROOT / "comparisons" / (("qcad-astra-sol-" if backend == "qcad" else "neka-astra-sol-") + uuid4().hex[:8])
    gallery.mkdir()
    results = []
    lines = ["# " + backend + ": Astra versus GPT-6.1 Sol", "", "Two independent passes over all ten originals. All readable views requested, whole-sheet layout. No model weights were trained.", "",
             "Astra is the common evaluator; same-provider bias remains possible. Internal acceptance is not human technical approval. All originals and prior results preserved.", "",
             "| Drawing | Generator | Outcome | Score | Seconds | CAD s | Calls | Input | Cached | Output |", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for original in inventory:
        drawing = original["drawing"]
        sheet = Image.new("RGB", (1800, 1500), "#eceff1")
        painter = ImageDraw.Draw(sheet)
        source = Image.open(campaign / drawing / "source/view.png").convert("RGB")
        tile = ImageOps.contain(source, (1700, 560))
        sheet.paste(tile, ((1800 - tile.width) // 2, 40))
        painter.text((20, 10), "Drawing " + drawing + " / original", fill="black")
        for index, name in enumerate(MODELS):
            directory = campaign / drawing / name
            result = json.loads((directory / "result.json").read_text())
            result.update(drawing=drawing, generator=name, directory=str(directory))
            results.append(result)
            cad_seconds = sum(item["seconds"] for item in result.get("builds", []))
            lines.append("| " + " | ".join(str(value) for value in (drawing, name, result["status"], result.get("final_score", "unknown"), round(result.get("elapsed_seconds", 0), 2), round(cad_seconds, 2), result.get("calls", "unknown"), result.get("input_tokens", "unknown"), result.get("cached_tokens", "unknown"), result.get("output_tokens", "unknown"))) + " |")
            left = index * 900
            painter.text((left + 20, 640), name + " / " + result["status"] + " / evaluator score " + str(result.get("final_score", "unknown")), fill="black")
            if result.get("last_valid_cad"):
                image = Image.open(Path(result["last_valid_cad"]) / "preview.png").convert("RGB")
                mask = ImageChops.difference(image, Image.new("RGB", image.size, "white")).convert("L").point(lambda value: 255 if value > 50 else 0)
                box = mask.getbbox()
                if box:
                    image = image.crop(box)
                tile = ImageOps.contain(image, (850, 680))
                sheet.paste(tile, (left + (900 - tile.width) // 2, 700 + (680 - tile.height) // 2))
            else:
                painter.text((left + 20, 880), "No validated CAD output; inspect failure receipt", fill="#a51b36")
        painter.text((20, 1430), "Same source, " + backend + " and protocol. Independent generation/correction, common Astra evaluator. Review whole-sheet coverage.", fill="#a51b36")
        painter.text((20, 1460), "Last validated draft shown even if rejected. No confirmed physical dimensions. Scores are not metrology or human approval.", fill="#a51b36")
        sheet.save(gallery / (drawing + "-astra-versus-sol.png"))
    totals = {}
    for name in MODELS:
        selected = [item for item in results if item["generator"] == name]
        totals[name] = {"drawings": len(selected), "internally_accepted": sum(item["status"] == "internally_accepted" for item in selected),
                        "seconds": sum(item.get("elapsed_seconds", 0) for item in selected),
                        "input_tokens": sum(item.get("input_tokens", 0) for item in selected),
                        "output_tokens": sum(item.get("output_tokens", 0) for item in selected),
                        "usage_complete": all(item.get("usage_complete", False) for item in selected)}
    lines.extend(["", "[Image-only comparison folder](" + Path(os.path.relpath(gallery, campaign)).as_posix() + ")", "",
                  "Input includes cache hits; output includes reasoning. All usage is provider-reported, not invoiced cost. Unknown timeout usage is not zero. No monetary/token cap; operation/correction bounds remain for safety.", ""])
    for item in results:
        lines.extend(["## " + item["drawing"] + " / " + item["generator"], "", item.get("assessment", item.get("error", "No evaluator result.")), ""])
        if item.get("last_valid_cad"):
            lines.extend(["[Native CAD](" + Path(os.path.relpath(Path(item["last_valid_cad"]) / ("draft.dxf" if backend == "qcad" else "draft.FCStd"), campaign)).as_posix() + ")", ""])
    (campaign / "report.md").write_text("\n".join(lines), encoding="utf-8")
    save(campaign / "results.json", results)
    save(campaign / "summary.json", {"gallery": str(gallery), "totals": totals, "results": results})
    print(json.dumps({"campaign": str(campaign), "gallery": str(gallery), "totals": totals}, indent=2), flush=True)


def status(campaign):
    rows = []
    for source in json.loads((campaign / "inventory.json").read_text()):
        for name in MODELS:
            directory = campaign / source["drawing"] / name
            row = {"drawing": source["drawing"], "generator": name, "status": "not_started"}
            for receipt_name in ("worker-progress.json", "checkpoint.json", "result.json"):
                receipt = directory / receipt_name
                if receipt.exists():
                    data = json.loads(receipt.read_text())
                    row.update({key: data[key] for key in ("status", "phase", "elapsed_seconds", "last_valid_cad", "final_score", "error") if key in data})
                    if receipt_name == "result.json":
                        row.pop("phase", None)
                    row["receipt_age_seconds"] = time.time() - receipt.stat().st_mtime
            for folder in ("inference", "evaluation-inference"):
                pending = directory / folder / "pending-request.json"
                if pending.exists():
                    request = json.loads(pending.read_text())
                    if request.get("status") == "waiting_for_response":
                        row["pending_request"] = {"phase": request["phase"], "elapsed_seconds": time.time() - request["started_unix_seconds"]}
            rows.append(row)
    print(json.dumps({"campaign": str(campaign), "summary_exists": (campaign / "summary.json").exists(), "routes": rows}, indent=2), flush=True)
    return rows


def run(campaign):
    inventory = json.loads((campaign / "inventory.json").read_text())
    backend = json.loads((campaign / "protocol.json").read_text()).get("backend", "freecad-neka")
    if backend == "FreeCAD Neka only":
        backend = "freecad-neka"
    lock = ROOT / "work/.astra-campaign.lock"
    with lock.open("x") as handle:
        handle.write(str(os.getpid()))
    try:
        for name in MODELS:
            for original in inventory:
                drawing = original["drawing"]
                directory = campaign / drawing / name
                if (directory / "result.json").exists():
                    continue
                directory.mkdir()
                print(backend + " pass " + name + " / drawing " + drawing, flush=True)
                command = [sys.executable, str(ROOT / "scripts/quality_campaign.py"), "worker", str(directory),
                           "--method", backend, "--config", str(campaign / (name + "-config.json"))]
                try:
                    process(command, directory, dict(os.environ), 7200)
                except Exception as error:
                    if not (directory / "result.json").exists():
                        save(directory / "result.json", {"method": backend, "status": "supervisor_failed", "error": str(error), "usage_complete": False})
                save(campaign / "progress.json", {"pass": name, "drawing": drawing, "completed": len(list(campaign.glob("*/*/result.json"))), "time": time.time()})
                save(campaign / "partial-results.json", [json.loads(path.read_text()) | {"drawing": path.parents[1].name, "generator": path.parent.name}
                                                        for path in sorted(campaign.glob("*/*/result.json"))])
    finally:
        lock.unlink()
    summarize(campaign)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "summarize", "status"))
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--backend", choices=("freecad-neka", "qcad"), default="freecad-neka")
    arguments = parser.parse_args()
    if arguments.action == "prepare":
        prepare(arguments.campaign.resolve(), arguments.backend)
    else:
        {"run": run, "summarize": summarize, "status": status}[arguments.action](arguments.campaign.resolve())