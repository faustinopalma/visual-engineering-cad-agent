"""Drafter-selected incremental CAD revisions.

After an independent evaluation, the drafter may edit a previously built and validated candidate
instead of regenerating the whole model. Edits are component-level operations. The executor copies
the saved native document of the chosen candidate, applies only those operations, saves the result
in a new attempt directory and verifies after reopening that untouched components were preserved.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path


OPERATIONS = ("replace_component", "append_shapes", "add_component", "remove_component")
ACTIONS = ("edit_existing", "regenerate")
MAX_OPERATIONS = 30
LIMITS = {"shapes": 180, "edges": 450, "components": 30}


def revision_schema(generation_schema):
    shape = generation_schema["properties"]["components"]["items"]["properties"]["shapes"]["items"]
    operation = {"type": "object", "properties": {
        "op": {"type": "string", "enum": list(OPERATIONS)},
        "component_id": {"type": "string"},
        "meaning": {"type": "string"},
        "shapes": {"type": "array", "items": copy.deepcopy(shape)}},
        "required": ["op", "component_id", "meaning", "shapes"], "additionalProperties": False}
    return {"type": "object", "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "base_attempt": {"type": "integer"},
        "rationale": {"type": "string"},
        "operations": {"type": "array", "items": operation},
        "model": copy.deepcopy(generation_schema)},
        "required": ["action", "base_attempt", "rationale", "operations", "model"], "additionalProperties": False}


def budget_usage(model):
    shapes = sum(len(component["shapes"]) for component in model["components"])
    edges = sum(len(shape["points"]) if shape["type"] == "polyline" else 1
                for component in model["components"] for shape in component["shapes"])
    return {"shapes": shapes, "edges": edges, "components": len(model["components"])}


def safe_budget_usage(model):
    try:
        return budget_usage(model)
    except (KeyError, TypeError, AttributeError):
        return None


def apply_operations(base_model, operations):
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise ValueError("edit_existing requires 1-" + str(MAX_OPERATIONS) + " operations.")
    model = copy.deepcopy(base_model)
    components = {component["id"]: component for component in model["components"]}
    touched = set()
    summary = {"removed": [], "replaced": [], "appended": [], "added": []}
    for operation in operations:
        if not isinstance(operation, dict) or set(operation) != {"op", "component_id", "meaning", "shapes"}:
            raise ValueError("Invalid edit operation fields.")
        kind, name, meaning, shapes = operation["op"], operation["component_id"], operation["meaning"], operation["shapes"]
        if kind not in OPERATIONS or not isinstance(name, str) or not isinstance(meaning, str) or not isinstance(shapes, list):
            raise ValueError("Invalid edit operation.")
        if name in touched:
            raise ValueError("Each component may be targeted by at most one operation: " + name)
        touched.add(name)
        if kind == "add_component":
            if name in components:
                raise ValueError("add_component target already exists: " + name + "; use replace_component or append_shapes.")
            if not shapes or not meaning.strip():
                raise ValueError("add_component requires meaning and shapes: " + name)
            component = {"id": name, "meaning": meaning, "shapes": copy.deepcopy(shapes)}
            model["components"].append(component)
            components[name] = component
            summary["added"].append(name)
            continue
        if name not in components:
            raise ValueError(kind + " target does not exist in the base candidate: " + name)
        if kind == "remove_component":
            if shapes:
                raise ValueError("remove_component must not include shapes: " + name)
            model["components"] = [component for component in model["components"] if component["id"] != name]
            del components[name]
            summary["removed"].append(name)
        elif kind == "replace_component":
            if not shapes or not meaning.strip():
                raise ValueError("replace_component requires meaning and complete replacement shapes: " + name)
            components[name]["meaning"] = meaning
            components[name]["shapes"] = copy.deepcopy(shapes)
            summary["replaced"].append(name)
        else:
            if not shapes:
                raise ValueError("append_shapes requires at least one shape: " + name)
            components[name]["shapes"].extend(copy.deepcopy(shapes))
            summary["appended"].append(name)
    if not model["components"]:
        raise ValueError("Edit removes every component; use regenerate instead.")
    summary["preserved"] = [component["id"] for component in model["components"] if component["id"] not in touched]
    return model, summary


def resolve_revision(revision, editable_models):
    """Return the complete model selected by the drafter and, for edits, the component summary."""
    action = revision.get("action")
    rationale = revision.get("rationale", "")
    if action == "regenerate":
        model = revision["model"]
        if not model.get("components"):
            raise ValueError("regenerate requires a complete non-empty model.")
        return {"action": action, "model": model, "base_attempt": None, "summary": None,
                "ignored_fields": ["operations"] if revision.get("operations") else []}
    if action != "edit_existing":
        raise ValueError("Unsupported revision action.")
    base_attempt = revision.get("base_attempt")
    if base_attempt not in editable_models:
        raise ValueError("base_attempt must be one of the editable attempts " + str(sorted(editable_models)) + ".")
    model, summary = apply_operations(editable_models[base_attempt], revision["operations"])
    model["notes"] = (model.get("notes", "") + "\nEdited from attempt " + str(base_attempt) + ": " + rationale[:2000]).strip()
    return {"action": action, "model": model, "base_attempt": base_attempt, "summary": summary,
            "ignored_fields": ["model"] if revision.get("model", {}).get("components") else []}


def entity_key(entity):
    return json.dumps({key: value for key, value in entity.items() if key != "id"}, sort_keys=True)


def executor_plan(base_compiled, compiled, summary):
    """Translate component edits into native executor operations on compiled entities."""
    def group(model):
        groups = {}
        for entity in model["entities"]:
            groups.setdefault(entity["component"], []).append(entity)
        return groups
    base_groups, groups = group(base_compiled), group(compiled)
    meanings = compiled["component_meanings"]
    if entity_key_list(base_compiled["entities"]) == entity_key_list(compiled["entities"]) and base_compiled["component_meanings"] == meanings:
        raise ValueError("Edit produces no geometric or semantic change.")
    operations = [{"op": "remove", "component": name} for name in summary["removed"]]
    operations += [{"op": "replace", "component": name, "meaning": meanings[name], "entities": groups.get(name, [])}
                   for name in summary["replaced"]]
    for name in summary["appended"]:
        remaining = Counter(entity_key(entity) for entity in base_groups.get(name, []))
        added = []
        for entity in groups.get(name, []):
            key = entity_key(entity)
            if remaining[key]:
                remaining[key] -= 1
            else:
                added.append(entity)
        if sum(remaining.values()) or not added:
            raise ValueError("append_shapes must keep every existing native entity of " + name + ".")
        operations.append({"op": "append", "component": name, "entities": added})
    operations += [{"op": "add", "component": name, "meaning": meanings[name], "entities": groups.get(name, [])}
                   for name in summary["added"]]
    for name in summary["preserved"]:
        if sorted(map(entity_key, base_groups.get(name, []))) != sorted(map(entity_key, groups.get(name, []))):
            raise ValueError("Preserved component differs after compilation: " + name)
    for operation in operations:
        if operation["op"] in {"replace", "add"} and not operation["entities"]:
            raise ValueError("Native component would be empty after edit: " + operation["component"])
    return {"operations": operations, "preserved": list(summary["preserved"]),
            "counts": {key: len(value) for key, value in summary.items()}}


def entity_key_list(entities):
    return sorted(map(entity_key, entities))


def offered_bases(editable):
    """Offer the latest and best-scoring validated candidates; both are already saved and reopened."""
    latest = editable[-1]
    best = max(editable, key=lambda item: (item["score"], item["attempt"]))
    return [latest] if best is latest else sorted([best, latest], key=lambda item: item["attempt"])


def describe_candidate(candidate):
    line = "- Attempt " + str(candidate["attempt"]) + " (" + candidate.get("mode", "generated")
    if candidate.get("base_attempt"):
        line += " from attempt " + str(candidate["base_attempt"])
    line += "): "
    budget = (" Model budget used " + json.dumps(candidate["budget"]) + " of " + json.dumps(LIMITS) + ".") if candidate.get("budget") else ""
    if candidate.get("error"):
        return line + "FAILED before evaluation: " + candidate["error"][:1500] + budget
    line += "native CAD saved/reopened; evaluator score " + str(candidate.get("score")) + ", " + ("accepted" if candidate.get("accepted") else "rejected") + "." + budget
    if candidate.get("defects"):
        line += "\n  Defects: " + " | ".join(defect[:600] for defect in candidate["defects"][:10])
    if candidate.get("correction_instructions"):
        line += "\n  Evaluator instructions: " + candidate["correction_instructions"][:1500]
    return line


def revision_prompt(conventions, plan, candidates, offered, models, failed_proposal=None):
    lines = ["You are the DRAFTER in a bounded draft/evaluate loop for an editable mechanical 2D CAD reconstruction.",
             "An independent evaluator judged earlier candidates against the source. Internal acceptance is never human approval.",
             conventions, "Plan: " + json.dumps(plan), "", "Candidate history:"]
    lines += [describe_candidate(candidate) for candidate in candidates]
    if failed_proposal is not None:
        lines += ["", "Last failed proposal (repair or abandon it): " + json.dumps(failed_proposal)[:60000]]
    lines += ["", "Editable validated candidates: " + ", ".join(str(item["attempt"]) for item in offered) + ".",
              "Images: first the source view, then the native CAD render of each editable candidate in the same order."]
    for item in offered:
        usage = budget_usage(models[item["attempt"]])
        lines.append("Attempt " + str(item["attempt"]) + " model; budget used " + json.dumps(usage) + " of " + json.dumps(LIMITS) + ": " + json.dumps(models[item["attempt"]]))
    lines += ["", "DECIDE how to produce the next candidate:",
              "- edit_existing: the executor copies the chosen candidate's saved native CAD document and applies ONLY your component operations. Every component you do not name is preserved exactly, with its native geometry and constraints. Prefer this when defects are localized and the remaining components are acceptable.",
              "- regenerate: a complete new model replaces all geometry for this attempt. Prefer this when the view interpretation, layout or most components are wrong, or an edit would touch most components.",
              "Operations (component_id must match exactly; target each component at most once; 1-" + str(MAX_OPERATIONS) + " operations):",
              "  replace_component: complete replacement meaning and shapes for one existing component.",
              "  append_shapes: add shapes to one existing component, keeping its current shapes and meaning; use meaning \"\".",
              "  add_component: new unique component_id with meaning and shapes.",
              "  remove_component: delete one existing component; use meaning \"\" and shapes [].",
              "For edit_existing: base_attempt is one editable attempt and model is {\"notes\": \"\", \"components\": []}.",
              "For regenerate: base_attempt 0, operations [] and model is the complete new model.",
              "The model after operations must satisfy all shape conventions and budgets. Do not exceed limits; when near a limit, replace verbose components with simpler supported geometry.",
              "Rationale: state which evaluator defects you address, why you chose the action and base, and what remains uncertain. Never claim acceptance or human approval."]
    return "\n".join(lines)


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def synthetic_model(native_qcad):
    def shape(kind, points, radius=0, closed=False, layer="OUTLINE"):
        value = {"type": kind, "points": points, "radius": radius, "closed": closed}
        if native_qcad:
            value.update(layer=layer, loops=[], angle=0, spacing=0)
        return value
    components = [
        {"id": "Body", "meaning": "rectangular body with bore", "shapes": [
            shape("polyline", [[40, 60], [260, 60], [260, 220], [40, 220]], closed=True), shape("circle", [[150, 140]], 30)]},
        {"id": "Axis", "meaning": "horizontal centerline", "shapes": [shape("line", [[20, 140], [280, 140]], layer="CENTERLINE")]},
        {"id": "Boss", "meaning": "boss outline", "shapes": [shape("circle", [[330, 140]], 25)]},
        {"id": "Spare", "meaning": "provisional stray contour", "shapes": [shape("spline", [[300, 230], [330, 250], [360, 235]])]}]
    if native_qcad:
        components.append({"id": "Section", "meaning": "sectioned material around a void", "shapes": [
            {"type": "hatch", "points": [], "radius": 0, "closed": True, "layer": "HATCH", "angle": 0, "spacing": 6,
             "loops": [[[300, 20], [380, 20], [380, 90], [300, 90]], [[325, 40], [325, 70], [355, 70], [355, 40]]]}]})
    first_edit = {"action": "edit_existing", "base_attempt": 1, "rationale": "Synthetic localized correction.", "model": {"notes": "", "components": []},
                  "operations": [
                      {"op": "replace_component", "component_id": "Boss", "meaning": "boss with smaller outline", "shapes": [shape("circle", [[330, 140]], 18)]},
                      {"op": "append_shapes", "component_id": "Body", "meaning": "", "shapes": [shape("line", [[40, 100], [260, 100]])]},
                      {"op": "add_component", "component_id": "Rib", "meaning": "added rib", "shapes": [shape("polyline", [[60, 230], [120, 260], [180, 230]])]},
                      {"op": "remove_component", "component_id": "Spare", "meaning": "", "shapes": []}]}
    second_edit = {"action": "edit_existing", "base_attempt": 2, "rationale": "Synthetic chained correction.", "model": {"notes": "", "components": []},
                   "operations": [{"op": "replace_component", "component_id": "Axis", "meaning": "shortened centerline", "shapes": [
                       shape("line", [[30, 140], [270, 140]], layer="CENTERLINE")]}]}
    return {"notes": "Synthetic incremental-edit fixture; no physical dimensions.", "components": components}, [first_edit, second_edit]


def smoke(output, method):
    """Build a synthetic candidate, then apply two chained native edits and verify preservation."""
    from astra_cad_agent import build, compile_model, save
    native_qcad = method == "qcad-native"
    if native_qcad:
        from qcad_model import compile_qcad as compile_function
    else:
        compile_function = compile_model
    backend = "qcad" if method.startswith("qcad") else method
    if method in {"freecad-neka", "freecad-robust"}:
        os.environ["CAD_AGENT_MCP_CANDIDATE"] = method.split("-")[1]
        backend = "freecad-mcp"
    width, height = 400, 300
    output.mkdir(parents=True)
    model, edits = synthetic_model(native_qcad)
    models = {1: model}
    save(output / "1-model.json", model)
    save(output / "1-compiled.json", compile_function(model, width, height))
    results = [dict(build(output / "1-compiled.json", output / "cad-1", backend), attempt=1, mode="generated")]
    native_name = "draft.dxf" if backend == "qcad" else "draft.FCStd"
    hashes = {1: file_sha256(output / "cad-1" / native_name)}
    for attempt, revision in enumerate(edits, start=2):
        resolved = resolve_revision(revision, models)
        models[attempt] = resolved["model"]
        save(output / (str(attempt) + "-model.json"), resolved["model"])
        compiled = compile_function(resolved["model"], width, height)
        save(output / (str(attempt) + "-compiled.json"), compiled)
        base_compiled = compile_function(models[revision["base_attempt"]], width, height)
        plan = dict(executor_plan(base_compiled, compiled, resolved["summary"]), base_attempt=revision["base_attempt"],
                    base_cad=str(output / ("cad-" + str(revision["base_attempt"]))))
        metrics = build(output / (str(attempt) + "-compiled.json"), output / ("cad-" + str(attempt)), backend, plan)
        report = json.loads((output / ("cad-" + str(attempt)) / "geometry.json").read_text())
        if not report.get("edit", {}).get("preserved_verified") or not metrics.get("base_unchanged"):
            raise RuntimeError("Native edit lacks preservation evidence.")
        hashes[attempt] = file_sha256(output / ("cad-" + str(attempt)) / native_name)
        results.append(dict(metrics, attempt=attempt, mode="edit_existing", preserved=plan["preserved"], counts=plan["counts"]))
    for attempt, digest in hashes.items():
        if file_sha256(output / ("cad-" + str(attempt)) / native_name) != digest:
            raise RuntimeError("Earlier candidate changed after a later edit.")
    summary = {"method": method, "status": "passed", "builds": results, "native_sha256": hashes,
               "evidence": "Native documents reopened; preserved components compared before/after edits; earlier candidates unchanged."}
    save(output / "smoke.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("smoke",))
    parser.add_argument("output", type=Path)
    parser.add_argument("--method", choices=("qcad", "qcad-native", "freecad-direct", "freecad-neka", "freecad-robust"), default="freecad-direct")
    arguments = parser.parse_args()
    smoke(arguments.output.resolve(), arguments.method)
