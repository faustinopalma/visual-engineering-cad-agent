"""Matrix comparison: drawings x CAD backends x drafter models x revision strategies.

For every drawing, backend and drafter model, one base route starts from the raw source: independent analysis, first
generation and evaluation, with max_attempts set by the plan. Both strategy arms (drafter_choice, full_regeneration) copy
that base and add the same number of attempts. Strategies are therefore compared from an identical start, while backends
and models are compared from the same input view, evaluator and limits. Each arm's final output is the best evaluated
candidate of the whole route (base plus arm), as the pipeline would deliver it. Overlays and the overlay judge are relative
visual evidence, not metrology or human approval.
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import sys
import time

from PIL import Image

from astra_cad_agent import ROOT, process, save
from mode_comparison import JUDGE_PROMPT, MODES, VIEWER_HTML, decisions, fmt, git_state, judge_once, native_geometry, overlay, svg_paths


BACKENDS = {"freecad": {"method": "freecad-neka", "native_qcad": False, "title": "FreeCAD"},
            "qcad": {"method": "qcad", "native_qcad": True, "title": "QCAD"}}
STRATEGIES = {"drafter_choice": "edit-capable", "full_regeneration": "from scratch"}
COLORS = {("freecad", "astra", "drafter_choice"): "#0072B2", ("freecad", "astra", "full_regeneration"): "#56B4E9",
          ("freecad", "sol", "drafter_choice"): "#009E73", ("freecad", "sol", "full_regeneration"): "#7FC97F",
          ("qcad", "astra", "drafter_choice"): "#D55E00", ("qcad", "astra", "full_regeneration"): "#E69F00",
          ("qcad", "sol", "drafter_choice"): "#CC79A7", ("qcad", "sol", "full_regeneration"): "#7B3294"}
BASE_COLORS = {("freecad", "astra"): "#1F3B57", ("freecad", "sol"): "#1E5631", ("qcad", "astra"): "#7A2E00", ("qcad", "sol"): "#4B1D52"}
NO_HATCH_JUDGE_NOTE = ("This reconstruction backend has no hatch entity: section hatching is intentionally omitted and is NOT missing "
                       "geometry; judge section outlines only.")


def plan_matrix(output, sources, models, base_attempts, arm_attempts):
    output.mkdir(parents=True)
    routes = []
    index = 0
    for source in sources:
        source = source.resolve()
        drawing = source.parent.name
        for backend, spec in BACKENDS.items():
            label = drawing + "-" + backend
            (output / label / "source").mkdir(parents=True)
            for path in sorted(source.iterdir()):
                if path.is_file():
                    (output / label / "source" / path.name).write_bytes(path.read_bytes())
            for model, config_path in models.items():
                template = json.loads(Path(config_path).read_text())
                base_id = "/".join((drawing, backend, model, "base"))
                base_dir = output / label / (model + "-base")
                base_config = output / label / (model + "-base.config.json")
                save(base_config, dict(template, native_qcad=spec["native_qcad"], revision_mode="full_regeneration", max_attempts=base_attempts))
                common = {"drawing": drawing, "backend": backend, "model": model, "label": label, "method": spec["method"]}
                routes.append(dict(common, id=base_id, kind="base", dir=str(base_dir), config=str(base_config)))
                for strategy in (MODES if index % 2 == 0 else MODES[::-1]):
                    config = output / label / (model + "-" + strategy + ".config.json")
                    save(config, dict(template, native_qcad=spec["native_qcad"], revision_mode=strategy, max_attempts=arm_attempts))
                    routes.append(dict(common, id="/".join((drawing, backend, model, strategy)), kind=strategy, base=base_id,
                                       dir=str(output / label / (model + "-" + strategy)), config=str(config)))
                index += 1
    judge_template = json.loads(Path(models["astra"] if "astra" in models else next(iter(models.values()))).read_text())
    save(output / "judge.config.json", dict(judge_template, deployment=judge_template.get("evaluator_deployment", judge_template["deployment"]),
                                            max_calls_per_route=2, max_total_tokens_per_route=None))
    plan = {"created_unix_seconds": time.time(), "code": git_state(), "base_attempts": base_attempts, "arm_attempts": arm_attempts,
            "models": {key: json.loads(Path(value).read_text())["deployment"] for key, value in models.items()},
            "evaluator": judge_template.get("evaluator_deployment"), "routes": routes, "human_approval": False,
            "protocol": "Base route per drawing, backend and drafter model from the raw source (" + str(base_attempts) + " attempt); each strategy arm copies the base and adds "
                        + str(arm_attempts) + " attempts. Same evaluator, reasoning effort and limits everywhere; only drafter deployment and backend differ. "
                        "FreeCAD has no hatch entity, so its drafter is told to omit hatching and its evaluator not to penalize it. Routes run sequentially; strategy order alternates."}
    save(output / "plan.json", plan)
    return plan


def load(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def run(output):
    plan = load(output / "plan.json")
    lock = ROOT / "work/.astra-campaign.lock"
    with lock.open("x") as handle:
        handle.write(str(os.getpid()))
    try:
        routes = {route["id"]: route for route in plan["routes"]}
        for route in plan["routes"]:
            directory = Path(route["dir"])
            if (directory / "result.json").exists():
                continue
            if directory.exists():
                raise RuntimeError("Interrupted route needs manual review before rerun: " + str(directory))
            command = [sys.executable, str(ROOT / "scripts/quality_campaign.py"), "worker", str(directory), "--method", route["method"], "--config", route["config"]]
            if route["kind"] != "base":
                base_dir = Path(routes[route["base"]]["dir"])
                base = load(base_dir / "result.json", {})
                if base.get("status") == "internally_accepted" or not (base_dir / "analysis.json").exists():
                    status = "base_accepted" if base.get("status") == "internally_accepted" else "base_unusable"
                    directory.mkdir(parents=True)
                    save(directory / "result.json", {"method": route["method"], "status": status, "revision_mode": route["kind"], "candidates": [],
                                                     "calls": 0, "input_tokens": 0, "output_tokens": 0, "elapsed_seconds": 0, "usage_complete": True,
                                                     "note": "Not run: the base route " + ("was already internally accepted" if status == "base_accepted" else "has no analysis to continue from") + "."})
                    print(json.dumps({"event": "route_skipped", "route": route["id"], "status": status}), flush=True)
                    continue
                command += ["--seed-route", str(base_dir)]
            else:
                directory.mkdir(parents=True)
            supervisor = directory.parent / (directory.name + "-supervisor")
            supervisor.mkdir(exist_ok=True)
            print(json.dumps({"event": "route_started", "route": route["id"]}), flush=True)
            try:
                process(command, supervisor, dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), 3600)
            except Exception as error:
                if not (directory / "result.json").exists():
                    directory.mkdir(parents=True, exist_ok=True)
                    save(directory / "result.json", {"method": route["method"], "status": "supervisor_failed", "error": str(error),
                                                     "revision_mode": route["kind"], "candidates": [], "usage_complete": False})
            print(json.dumps({"event": "route_finished", "route": route["id"], "status": load(directory / "result.json", {}).get("status")}), flush=True)
    finally:
        lock.unlink()


TRANSPORT_ERRORS = ("10054", "timed out", "Connection", "connection", "RemoteDisconnected", "IncompleteRead", "Inference HTTP 5")


def retry_failed(output, limit=1):
    """Preserve transport-failed routes (and arms seeded from a failed base) under a new name so `run` executes them again."""
    plan = load(output / "plan.json")
    retries = load(output / "retries.json", [])
    marked = []
    for route in plan["routes"]:
        result = load(Path(route["dir"]) / "result.json")
        if not result or result.get("status") not in ("failed", "supervisor_failed") or not any(text in str(result.get("error", "")) for text in TRANSPORT_ERRORS):
            continue
        if sum(item["route"] == route["id"] for item in retries) >= limit:
            continue
        marked.append(route)
        if route["kind"] == "base":
            marked += [arm for arm in plan["routes"] if arm.get("base") == route["id"] and arm not in marked]
    for route in marked:
        directory = Path(route["dir"])
        if not directory.exists():
            continue
        result = load(directory / "result.json", {})
        number = sum(item["route"] == route["id"] for item in retries) + 1
        target = directory.with_name(directory.name + ".transport-failed-" + str(number))
        directory.rename(target)
        prefix = Path(os.path.relpath(directory, output)).as_posix().replace("/", "__") + "__"
        for stale in sorted((output / "overlays").glob(prefix + "*")) if (output / "overlays").exists() else []:
            stale.rename(stale.with_name("transport-failed-" + str(number) + "__" + stale.name))
        supervisor = directory.parent / (directory.name + "-supervisor")
        if supervisor.exists():
            supervisor.rename(supervisor.with_name(supervisor.name + ".transport-failed-" + str(number)))
        retries.append({"route": route["id"], "status": result.get("status"), "error": str(result.get("error", ""))[:200], "preserved_as": str(target),
                        "reason": "transport failure" if result.get("status") in ("failed", "supervisor_failed") else "seeded from a transport-failed base",
                        "calls": result.get("calls"), "input_tokens": result.get("input_tokens"), "output_tokens": result.get("output_tokens"),
                        "unix_seconds": time.time()})
        print(json.dumps({"retry": route["id"], "preserved_as": str(target)}), flush=True)
    save(output / "retries.json", retries)
    return marked


def built(route_dir, result, include_seeded):
    rows = []
    for candidate in result.get("candidates", []):
        if candidate.get("seeded") and not include_seeded or not candidate.get("cad") or candidate.get("score") is None:
            continue
        rows.append({"attempt": candidate["attempt"], "score": candidate["score"], "accepted": candidate["accepted"], "cad": candidate["cad"],
                     "compiled": str(Path(route_dir) / (str(candidate["attempt"]) + "-compiled.json")), "mode": candidate.get("mode")})
    return rows


def overlay_dir(output, cad):
    return output / "overlays" / Path(os.path.relpath(cad, output)).as_posix().replace("/", "__")


def collect(output):
    """One entry per route. Final output = best evaluated candidate of the whole route (base candidates plus the arm's new ones)."""
    plan = load(output / "plan.json")
    routes = {route["id"]: route for route in plan["routes"]}
    entries = []
    for route in plan["routes"]:
        result = load(Path(route["dir"]) / "result.json", {"status": "not_run", "candidates": []})
        base = routes.get(route.get("base"))
        base_result = load(Path(base["dir"]) / "result.json", {"status": "not_run", "candidates": []}) if base else None
        pool = [dict(item, origin="base") for item in built(base["dir"], base_result, False)] if base else []
        pool += [dict(item, origin="base" if route["kind"] == "base" else "arm") for item in built(route["dir"], result, False)]
        final = max(pool, key=lambda item: (item["score"], item["origin"] == "arm", item["attempt"])) if pool else None
        cost = {key: (result.get(key) or 0) + ((base_result or {}).get(key) or 0) for key in ("calls", "input_tokens", "output_tokens", "elapsed_seconds")}
        entries.append(dict(route, result=result, base_result=base_result, final=final, route_cost=cost,
                            new_valid=sum(item["origin"] == "arm" for item in pool) if base else len(pool),
                            new_attempts=len([item for item in result.get("candidates", []) if not item.get("seeded")])))
    return plan, entries


def finals(output, entries):
    unique = {}
    for entry in entries:
        if entry["final"]:
            unique.setdefault(entry["final"]["cad"], entry)
    return unique


def measure(output):
    _, entries = collect(output)
    for cad, entry in finals(output, entries).items():
        target = overlay_dir(output, cad)
        if (target / "overlay-metrics.json").exists():
            continue
        overlay(output / entry["label"] / "source" / "view.png", native_geometry(cad, entry["final"]["compiled"]), target)
        print(json.dumps({"overlay": entry["id"], "cad": cad}), flush=True)


def judge(output):
    plan, entries = collect(output)
    config = load(output / "judge.config.json")
    items = sorted(finals(output, entries).items(), key=lambda pair: hashlib.sha256((str(plan["created_unix_seconds"]) + pair[0]).encode()).hexdigest())
    for cad, entry in items:
        target = overlay_dir(output, cad)
        if (target / "overlay-judgment.json").exists() or not (target / "overlay.png").exists():
            continue
        note = NO_HATCH_JUDGE_NOTE if not BACKENDS[entry["backend"]]["native_qcad"] else ""
        judgment = judge_once(config, output / entry["label"] / "source" / "view.png", target, "overlay-judgment.json", "judge-inference", note)
        print(json.dumps({"judged": entry["id"], "adherence": judgment["adherence_score"], "coverage": judgment["coverage_score"]}), flush=True)


def evidence(output, entry):
    if not entry["final"]:
        return {}, {}
    target = overlay_dir(output, entry["final"]["cad"])
    return load(target / "overlay-metrics.json", {}), load(target / "overlay-judgment.json", {})


def mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def report(output):
    plan, entries = collect(output)
    for entry in entries:
        entry["metrics"], entry["judgment"] = evidence(output, entry)
    arms = [entry for entry in entries if entry["kind"] != "base"]
    header = ["Drawing", "Backend", "Drafter", "Strategy", "Final output", "Drafter decisions", "Internal score", "Judge adherence / coverage",
              "Ink precision / recall", "Route calls", "Route tokens in / out", "Route seconds", "Status"]
    def row(entry):
        final = entry["final"]
        base = entry["kind"] == "base"
        output_name = "-" if not final else (("base " if final["origin"] == "base" else "") + "attempt " + str(final["attempt"]))
        steps = "first generation" if base else ("; ".join(decisions(entry["result"])) or entry["result"].get("note", "-"))
        cost = entry["result"] if base else entry["route_cost"]
        return [entry["drawing"], BACKENDS[entry["backend"]]["title"], entry["model"].capitalize(), "base" if base else STRATEGIES[entry["kind"]],
                output_name, steps, "-" if not final else fmt(final["score"]) + (" accepted" if final["accepted"] else ""),
                fmt(entry["judgment"].get("adherence_score")) + " / " + fmt(entry["judgment"].get("coverage_score")),
                fmt(entry["metrics"].get("ink_precision"), percent=True) + " / " + fmt(entry["metrics"].get("ink_recall"), percent=True),
                fmt(cost.get("calls")), fmt(cost.get("input_tokens")) + " / " + fmt(cost.get("output_tokens")),
                fmt(None if cost.get("elapsed_seconds") is None else round(cost["elapsed_seconds"])), entry["result"].get("status", "-")]
    aggregate_header = ["Group", "Outputs", "Internally accepted", "Mean internal", "Mean judge adherence", "Mean judge coverage",
                        "Mean ink precision", "Mean ink recall", "Route tokens in / out", "Route seconds"]
    def aggregate(name, group):
        scored = [entry for entry in group if entry["final"]]
        return [name, str(len(scored)) + " / " + str(len(group)), str(sum(entry["final"]["accepted"] for entry in scored)),
                fmt(mean([entry["final"]["score"] for entry in scored]), 1), fmt(mean([entry["judgment"].get("adherence_score") for entry in group]), 1),
                fmt(mean([entry["judgment"].get("coverage_score") for entry in group]), 1),
                fmt(mean([entry["metrics"].get("ink_precision") for entry in group]), percent=True), fmt(mean([entry["metrics"].get("ink_recall") for entry in group]), percent=True),
                fmt(sum(entry["route_cost"]["input_tokens"] for entry in group)) + " / " + fmt(sum(entry["route_cost"]["output_tokens"] for entry in group)),
                fmt(round(sum(entry["route_cost"]["elapsed_seconds"] for entry in group)))]
    groups = [("All 24 final outputs" if len(arms) == 24 else "All final outputs", arms)]
    groups += [(BACKENDS[key]["title"], [entry for entry in arms if entry["backend"] == key]) for key in BACKENDS]
    groups += [(key.capitalize() + " drafter", [entry for entry in arms if entry["model"] == key]) for key in plan["models"]]
    groups += [(STRATEGIES[key], [entry for entry in arms if entry["kind"] == key]) for key in MODES]
    groups += [(BACKENDS[backend]["title"] + " / " + model.capitalize() + " / " + STRATEGIES[kind],
                [entry for entry in arms if (entry["backend"], entry["model"], entry["kind"]) == (backend, model, kind)])
               for backend in BACKENDS for model in plan["models"] for kind in MODES]
    paired_header = ["Drawing", "Drafter", "Strategy", "FreeCAD internal", "QCAD internal", "FreeCAD judge adh/cov", "QCAD judge adh/cov",
                     "FreeCAD ink precision", "QCAD ink precision"]
    paired = []
    for drawing in dict.fromkeys(entry["drawing"] for entry in arms):
        for model in plan["models"]:
            for kind in MODES:
                pair = {entry["backend"]: entry for entry in arms if (entry["drawing"], entry["model"], entry["kind"]) == (drawing, model, kind)}
                if set(pair) != set(BACKENDS):
                    continue
                values = [drawing, model.capitalize(), STRATEGIES[kind]]
                values += [fmt(pair[key]["final"] and pair[key]["final"]["score"]) for key in BACKENDS]
                values += [fmt(pair[key]["judgment"].get("adherence_score")) + "/" + fmt(pair[key]["judgment"].get("coverage_score")) for key in BACKENDS]
                values += [fmt(pair[key]["metrics"].get("ink_precision"), percent=True) for key in BACKENDS]
                paired.append(values)
    judged = [load(overlay_dir(output, cad) / "overlay-judgment.json") for cad in finals(output, entries)]
    judged = [item for item in judged if item]
    failures = sum(len(list(overlay_dir(output, cad).glob("*error-*.json"))) for cad in finals(output, entries) if overlay_dir(output, cad).exists())
    notes = [plan["protocol"]] + plan.get("amendments", []) + [
             "Final output = best evaluated candidate of the whole route (base plus arm) by internal score; 'base attempt' means the arm did not improve on the shared base.",
             "Route calls, tokens and seconds include the shared base route, so each arm shows the full cost of producing its final output; base rows show the base alone.",
             "Ink precision = share of CAD line pixels within 3 px of source ink; ink recall = share of source ink near CAD lines. Source ink includes text, dimensions, title block and hatching, so recall compares outputs of the same drawing. QCAD hatch fills are not counted as lines.",
             "Overlay judge: stateless call (" + load(output / "judge.config.json")["deployment"] + ") seeing only source and overlay, blind to model and strategy. For FreeCAD it is told that hatching is intentionally omitted. Same provider as drafter/evaluator: errors may be correlated.",
             "One route per cell; differences of a few points are within observed judge and route variation. Internal acceptance is not human approval; no USD cost verified."]
    retries = load(output / "retries.json", [])
    if retries:
        notes.append("Transport retries: " + str(len(retries)) + " route run(s) failed on the network or service (connection reset, read timeout, HTTP 5xx), were interrupted to switch transport, or were seeded from such a base; they were preserved as *.transport-failed-N / *.interrupted-N and rerun once with the same configuration: "
                     + ", ".join(item["route"] for item in retries) + ". Their partial usage (" + fmt(sum(item.get("input_tokens") or 0 for item in retries)) + " input / "
                     + fmt(sum(item.get("output_tokens") or 0 for item in retries)) + " output tokens recorded, more unknown) is not included in route costs.")
    for entry in entries:
        if entry["kind"] == "base" and not entry["final"]:
            notes.append("Base " + entry["id"] + " produced no evaluated candidate (" + str(entry["result"].get("status")) + ": " + str(entry["result"].get("error", "-"))[:120]
                         + "). Its arms continued from the shared analysis with only their own attempts, one fewer than other cells.")
    if judged:
        notes.append("Overlay judge usage: " + str(sum(item.get("calls", 0) for item in judged)) + " successful calls, " + str(sum(item.get("input_tokens", 0) for item in judged))
                     + " input / " + str(sum(item.get("output_tokens", 0) for item in judged)) + " output tokens" + (" plus " + str(failures) + " failed call(s) with unknown usage" if failures else "") + ".")
    def md_table(head, body):
        return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(str(cell).replace("|", "/") for cell in cells) + " |" for cells in body]
    lines = ["# Matrix comparison: backend x drafter model x revision strategy", "",
             "Code: " + plan["code"]["branch"] + " @ " + plan["code"]["commit"][:7] + (" (uncommitted changes)" if plan["code"]["dirty"] else ""), "",
             "## Aggregates", ""] + md_table(aggregate_header, [aggregate(name, group) for name, group in groups])
    lines += ["", "## FreeCAD versus QCAD, same drawing, drafter and strategy", ""] + md_table(paired_header, paired)
    lines += ["", "## All routes", ""] + md_table(header, [row(entry) for entry in entries])
    lines += ["", "## Notes", ""] + ["- " + note for note in notes]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    def html_table(head, body):
        return "<table><tr>" + "".join("<th>" + html.escape(cell) + "</th>" for cell in head) + "</tr>" + "".join(
            "<tr>" + "".join("<td>" + html.escape(str(cell)) + "</td>" for cell in cells) + "</tr>" for cells in body) + "</table>"
    page = ("<!doctype html><meta charset=utf-8><title>Matrix comparison</title><style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1b1f24}"
            "table{border-collapse:collapse;font-size:13px;margin-bottom:18px}td,th{border:1px solid #c9d1d9;padding:5px 7px;vertical-align:top}th{background:#eef2f6}</style>"
            "<h1>Matrix comparison: backend x drafter model x revision strategy</h1><p><a href='viewer.html'>Open the overlay viewer</a></p>"
            "<h2>Aggregates</h2>" + html_table(aggregate_header, [aggregate(name, group) for name, group in groups])
            + "<h2>FreeCAD versus QCAD</h2>" + html_table(paired_header, paired)
            + "<h2>All routes</h2>" + html_table(header, [row(entry) for entry in entries])
            + "<h2>Notes</h2><ul>" + "".join("<li>" + html.escape(note) + "</li>" for note in notes) + "</ul>")
    (output / "report.html").write_text(page, encoding="utf-8")
    print(json.dumps({"report": str(output / "report.md"), "routes": len(entries)}), flush=True)


def viewer(output):
    plan, entries = collect(output)
    drawings = []
    for drawing in dict.fromkeys(entry["drawing"] for entry in entries):
        group = [entry for entry in entries if entry["drawing"] == drawing]
        label = group[0]["label"]
        with Image.open(output / label / "source" / "view.png") as image:
            width, height = image.size
        layers = []
        order = [(backend, model, kind) for backend in BACKENDS for model in plan["models"] for kind in MODES]
        order += [(backend, model, "base") for backend in BACKENDS for model in plan["models"]]
        for backend, model, kind in order:
            entry = next((item for item in group if (item["backend"], item["model"], item["kind"]) == (backend, model, kind)), None)
            if entry is None:
                continue
            metrics, judgment = evidence(output, entry)
            final = entry["final"]
            base = kind == "base"
            cost = entry["result"] if base else entry["route_cost"]
            title = BACKENDS[backend]["title"] + " · " + model.capitalize() + " · " + ("base (first attempt, shared)" if base else STRATEGIES[kind])
            detail = ("Shared start of both strategy arms." if base else ("; ".join(decisions(entry["result"])) or entry["result"].get("note", "")))
            if final and not base and final["origin"] == "base":
                detail += " Final output is the shared base candidate (no improvement)."
            if not base and entry["result"].get("candidates") and not any(item.get("seeded") for item in entry["result"]["candidates"]):
                detail += " The shared base produced no evaluated candidate; this arm started from the shared analysis only."
            layer = {"key": entry["id"], "title": title, "detail": detail, "tags": [BACKENDS[backend]["title"], model.capitalize(), "base" if base else STRATEGIES[kind]],
                     "color": BASE_COLORS[(backend, model)] if base else COLORS[(backend, model, kind)], "dash": base,
                     "visible": not base and (backend, model, kind) == order[0], "attempt": final and final["attempt"],
                     "internal_score": final and final["score"], "internal_accepted": bool(final and final["accepted"]),
                     "ink_precision": metrics.get("ink_precision"), "ink_recall": metrics.get("ink_recall"),
                     "judge_adherence": judgment.get("adherence_score"), "judge_coverage": judgment.get("coverage_score"),
                     "calls": cost.get("calls"), "input_tokens": cost.get("input_tokens"), "output_tokens": cost.get("output_tokens"),
                     "seconds": None if cost.get("elapsed_seconds") is None else round(cost["elapsed_seconds"])}
            if final:
                try:
                    layer["lines"], layer["fills"] = svg_paths(native_geometry(final["cad"], final["compiled"]), height)
                except Exception as error:
                    layer["error"] = str(error)
            else:
                layer["error"] = "No valid output (" + str(entry["result"].get("status")) + ")."
            layers.append(layer)
        drawings.append({"label": "Drawing " + drawing, "image": label + "/source/view.png", "width": width, "height": height, "layers": layers})
    data = {"title": "Drawing vs reconstructions: backend × drafter × strategy", "drawings": drawings,
            "notes": ["Each strategy layer is the final output of its route: the best evaluated candidate of the shared base plus the arm's attempts. Dashed layers are the shared bases.",
                      "All routes started from the same source view with the same evaluator (" + str(plan["evaluator"]) + ") and limits: base " + str(plan["base_attempts"]) + " attempt, arms +" + str(plan["arm_attempts"]) + ".",
                      "FreeCAD has no hatch entity and was told to omit hatching; QCAD hatch regions are shown as light fills.",
                      "Route cost includes the shared base. Geometry is read back from saved native documents at the pipeline transform; visual evidence only, not metrology or human approval."]}
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    (output / "viewer.html").write_text(VIEWER_HTML.replace("__DATA__", payload), encoding="utf-8")
    print(json.dumps({"viewer": str(output / "viewer.html"), "layers": sum(len(item["layers"]) for item in drawings)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "run", "retry-failed", "overlay", "judge", "report", "viewer", "all"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--source", type=Path, action="append", default=[], help="plan: prepared drawing source directory (contains view.png and page.png)")
    parser.add_argument("--model", action="append", default=[], help="plan: KEY=CONFIG, for example astra=path\\config.json")
    parser.add_argument("--base-attempts", type=int, default=1)
    parser.add_argument("--arm-attempts", type=int, default=2)
    arguments = parser.parse_args()
    directory = arguments.directory.resolve()
    if arguments.action == "plan":
        if not arguments.source or not arguments.model:
            parser.error("plan needs --source and --model")
        plan_matrix(directory, arguments.source, dict(item.split("=", 1) for item in arguments.model), arguments.base_attempts, arguments.arm_attempts)
        raise SystemExit(0)
    if arguments.action == "retry-failed":
        retry_failed(directory)
        raise SystemExit(0)
    if arguments.action in ("run", "all"):
        run(directory)
    if arguments.action in ("overlay", "all"):
        measure(directory)
    if arguments.action in ("judge", "all"):
        judge(directory)
    if arguments.action in ("report", "all"):
        report(directory)
    if arguments.action in ("viewer", "all"):
        viewer(directory)
