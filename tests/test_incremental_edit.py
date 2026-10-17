import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_cad_agent import MODEL_SCHEMA, compile_model
import incremental_edit
from incremental_edit import apply_operations, executor_plan, resolve_revision, revision_schema, synthetic_model
import quality_campaign


BASE, EDITS = synthetic_model(False)
REJECT = {"accepted": False, "score": 60, "assessment": "Synthetic rejection.", "defects": ["Boss too large."], "correction_instructions": "Shrink Boss."}
ACCEPT = {"accepted": True, "score": 90, "assessment": "Synthetic acceptance.", "defects": [], "correction_instructions": ""}


def operation(kind, name, shapes=(), meaning=""):
    return {"op": kind, "component_id": name, "meaning": meaning, "shapes": list(shapes)}


def line(*points):
    return {"type": "line", "points": [list(point) for point in points], "radius": 0, "closed": False}


class OperationTests(unittest.TestCase):
    def test_component_operations_preserve_untouched_components(self):
        model, summary = apply_operations(BASE, EDITS[0]["operations"])
        self.assertEqual(summary, {"removed": ["Spare"], "replaced": ["Boss"], "appended": ["Body"], "added": ["Rib"], "preserved": ["Axis"]})
        components = {component["id"]: component for component in model["components"]}
        self.assertNotIn("Spare", components)
        self.assertEqual(components["Axis"], BASE["components"][1])
        self.assertEqual(components["Body"]["shapes"][:2], BASE["components"][0]["shapes"])
        self.assertEqual(len(components["Body"]["shapes"]), 3)
        self.assertEqual(components["Boss"]["shapes"][0]["radius"], 18)
        self.assertEqual(len(BASE["components"]), 4)

    def test_invalid_operations_are_rejected(self):
        cases = [[],
                 [operation("replace_component", "Missing", [line((0, 0), (1, 1))], "x")],
                 [operation("add_component", "Body", [line((0, 0), (1, 1))], "x")],
                 [operation("remove_component", "Spare", [line((0, 0), (1, 1))])],
                 [operation("append_shapes", "Body")],
                 [operation("append_shapes", "Body", [line((0, 0), (1, 1))]), operation("remove_component", "Body")],
                 [operation("remove_component", name) for name in ("Body", "Axis", "Boss", "Spare")]]
        for operations in cases:
            with self.subTest(operations=operations), self.assertRaises(ValueError):
                apply_operations(BASE, operations)

    def test_revision_resolution_limits_bases_and_keeps_regeneration_complete(self):
        regenerate = {"action": "regenerate", "base_attempt": 0, "rationale": "Layout wrong.", "operations": [], "model": BASE}
        self.assertEqual(resolve_revision(regenerate, {1: BASE})["model"], BASE)
        with self.assertRaises(ValueError):
            resolve_revision(dict(EDITS[0], base_attempt=7), {1: BASE})
        resolved = resolve_revision(EDITS[0], {1: BASE})
        self.assertEqual(resolved["base_attempt"], 1)
        self.assertIn("Edited from attempt 1", resolved["model"]["notes"])

    def test_executor_plan_contains_only_changed_native_entities(self):
        resolved = resolve_revision(EDITS[0], {1: BASE})
        base, edited = compile_model(BASE, 400, 300), compile_model(resolved["model"], 400, 300)
        plan = executor_plan(base, edited, resolved["summary"])
        operations = {item["op"]: item for item in plan["operations"]}
        self.assertEqual(set(operations), {"remove", "replace", "append", "add"})
        base_body = [entity for entity in base["entities"] if entity["component"] == "Body"]
        self.assertEqual([entity["geometry_index"] for entity in operations["append"]["entities"]], [len(base_body)])
        self.assertEqual(plan["preserved"], ["Axis"])
        noop = resolve_revision(dict(EDITS[0], operations=[operation("replace_component", "Boss", BASE["components"][2]["shapes"], BASE["components"][2]["meaning"])]), {1: BASE})
        with self.assertRaises(ValueError):
            executor_plan(base, compile_model(noop["model"], 400, 300), noop["summary"])

    def test_revision_schema_is_strict(self):
        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertFalse(node["additionalProperties"])
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(revision_schema(MODEL_SCHEMA))


class FakeClient:
    scripts = {}

    def __init__(self, config, output):
        self.metrics = []
        self.calls = []
        self.role = "evaluator" if output.name == "evaluation-inference" else "drafter"
        FakeClient.instances[self.role] = self

    def call(self, phase, prompt, images=(), schema=None, max_output_tokens=None):
        self.calls.append({"phase": phase, "prompt": prompt, "images": [str(image) for image in images]})
        self.metrics.append({"phase": phase, "usage": {"input_tokens": 1, "output_tokens": 1}})
        response = FakeClient.scripts[phase]
        return copy.deepcopy(response(prompt, images) if callable(response) else response)


def fake_build(model_path, output, backend, edit=None):
    output.mkdir()
    Image.new("RGB", (40, 30), "black").save(output / "preview.png")
    (output / "draft.FCStd").write_bytes(model_path.read_bytes())
    metrics = {"backend": backend, "mode": "edit_existing" if edit else "generated", "base_attempt": edit and edit["base_attempt"]}
    (output / "geometry.json").write_text(json.dumps({"status": "passed"}))
    (output / "build.json").write_text(json.dumps(metrics))
    fake_build.calls.append({"output": output.name, "edit": edit})
    return metrics


class WorkerHarness(unittest.TestCase):
    def run_worker(self, scripts, config, directory=None, build=fake_build, method="freecad-direct"):
        FakeClient.scripts, FakeClient.instances, fake_build.calls = scripts, {}, []
        temporary = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = temporary / "case" / "source"
        source.mkdir(parents=True)
        Image.new("RGB", (400, 300), "white").save(source / "view.png")
        Image.new("RGB", (400, 300), "white").save(source / "page.png")
        directory = directory(temporary) if directory else temporary / "case" / method
        directory.mkdir(exist_ok=True)
        config_path = temporary / "config.json"
        config_path.write_text(json.dumps(dict({"deployment": "fake-drafter", "evaluator_deployment": "fake-evaluator"}, **config)))
        with mock.patch.object(quality_campaign, "AstraClient", FakeClient), mock.patch.object(quality_campaign, "build", build), \
                contextlib.redirect_stdout(io.StringIO()):
            quality_campaign.worker(directory, method, config_path)
        return json.loads((directory / "result.json").read_text()), directory


class WorkerLoopTests(WorkerHarness):
    def test_drafter_can_edit_evaluated_candidate(self):
        result, directory = self.run_worker({"01-analysis": {"plan": "synthetic"}, "1-generate": BASE, "1-evaluate": REJECT,
                                             "2-revise": EDITS[0], "2-evaluate": ACCEPT}, {})
        self.assertEqual(result["status"], "internally_accepted", result.get("error"))
        self.assertEqual(result["revision_mode"], "drafter_choice")
        self.assertEqual([item["mode"] for item in result["candidates"]], ["generated", "edit_existing"])
        self.assertEqual(result["candidates"][1]["preserved"], ["Axis"])
        self.assertIsNone(fake_build.calls[0]["edit"])
        self.assertEqual(fake_build.calls[1]["edit"]["base_attempt"], 1)
        self.assertTrue(fake_build.calls[1]["edit"]["base_cad"].endswith("cad-1"))
        revise = FakeClient.instances["drafter"].calls[-1]
        self.assertIn("edit_existing", revise["prompt"])
        self.assertTrue(revise["images"][1].endswith(str(Path("cad-1") / "preview.png")))
        evaluations = FakeClient.instances["evaluator"].calls
        self.assertEqual(evaluations[0]["prompt"], evaluations[1]["prompt"])
        self.assertEqual(json.loads((directory / "2-model.json").read_text())["components"][-1]["id"], "Rib")
        self.assertEqual(result["best_candidate"]["attempt"], 2)

    def test_full_regeneration_keeps_legacy_correction_loop(self):
        def regenerate(prompt, images):
            self.assertIn("Correct your own previous model only", prompt)
            return BASE
        result, directory = self.run_worker({"01-analysis": {}, "1-generate": BASE, "1-evaluate": REJECT,
                                             "2-generate": regenerate, "2-evaluate": ACCEPT}, {"revision_mode": "full_regeneration"})
        self.assertEqual(result["status"], "internally_accepted", result.get("error"))
        self.assertEqual([call["edit"] for call in fake_build.calls], [None, None])
        self.assertFalse((directory / "2-revision.json").exists())

    def test_failed_edit_is_reported_back_and_drafter_may_regenerate(self):
        bad = dict(EDITS[0], operations=[operation("replace_component", "Missing", [line((1, 1), (5, 5))], "x")])
        def regenerate(prompt, images):
            self.assertIn("Last failed proposal", prompt)
            self.assertIn("Missing", prompt)
            return {"action": "regenerate", "base_attempt": 0, "rationale": "Restart.", "operations": [], "model": BASE}
        result, _ = self.run_worker({"01-analysis": {}, "1-generate": BASE, "1-evaluate": REJECT, "2-revise": bad,
                                     "3-revise": regenerate, "3-evaluate": ACCEPT}, {"max_attempts": 3})
        self.assertEqual(result["status"], "internally_accepted", result.get("error"))
        self.assertIn("does not exist", result["candidates"][1]["error"])
        self.assertEqual(result["candidates"][2]["mode"], "regenerate")
        self.assertIsNone(fake_build.calls[-1]["edit"])

    def test_invalid_revision_mode_fails_without_calls(self):
        result, _ = self.run_worker({}, {"revision_mode": "patch_everything"})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["calls"], 0)

    def test_seeded_route_continues_without_new_analysis_and_leaves_source_unchanged(self):
        temporary = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = temporary / "old"
        (source / "cad-1").mkdir(parents=True)
        files = {"analysis.json": {"plan": "seeded"}, "result.json": {"method": "freecad-neka", "status": "not_accepted"},
                 "config.json": {"native_qcad": False}, "1-model.json": BASE, "1-compiled.json": compile_model(BASE, 400, 300),
                 "1-evaluation.json": REJECT, "2-model.json": BASE, "2-failure.json": {"error": "Native failure: budget."}}
        for name, value in files.items():
            (source / name).write_text(json.dumps(value))
        for name in ("build.json", "geometry.json"):
            (source / "cad-1" / name).write_text("{}")
        (source / "cad-1" / "draft.FCStd").write_bytes(b"fcstd")
        Image.new("RGB", (40, 30), "black").save(source / "cad-1" / "preview.png")
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob("*") if path.is_file()}
        def seeded(temporary):
            target = temporary / "case" / "freecad-direct"
            with contextlib.redirect_stdout(io.StringIO()):
                quality_campaign.seed_route(source, target)
            return target
        def revise(prompt, images):
            self.assertIn("Native failure: budget.", prompt)
            self.assertIn("Model budget used", prompt.split("Attempt 2")[1])
            return EDITS[0]
        result, directory = self.run_worker({"3-revise": revise, "3-evaluate": ACCEPT}, {"max_attempts": 1}, seeded)
        self.assertEqual(result["status"], "internally_accepted", result.get("error"))
        self.assertEqual([item["attempt"] for item in result["candidates"]], [1, 2, 3])
        self.assertEqual(FakeClient.instances["drafter"].calls[0]["phase"], "3-revise")
        self.assertEqual(fake_build.calls[0]["edit"]["base_attempt"], 1)
        self.assertEqual(result["seed"]["source_method"], "freecad-neka")
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob("*") if path.is_file()})
        with self.assertRaises(ValueError), contextlib.redirect_stdout(io.StringIO()):
            quality_campaign.seed_route(source, directory)


@unittest.skipUnless(os.environ.get("CAD_AGENT_NATIVE_TESTS") == "1", "set CAD_AGENT_NATIVE_TESTS=1 to run real CAD edits")
class NativeWorkerTests(WorkerHarness):
    def test_qcad_worker_edits_saved_native_candidate(self):
        result, directory = self.run_worker({"01-analysis": {}, "1-generate": BASE, "1-evaluate": REJECT,
                                             "2-revise": EDITS[0], "2-evaluate": ACCEPT}, {}, build=quality_campaign.build, method="qcad")
        self.assertEqual(result["status"], "internally_accepted", result.get("error"))
        build = json.loads((directory / "cad-2" / "build.json").read_text())
        self.assertEqual((build["mode"], build["base_attempt"], build["base_unchanged"]), ("edit_existing", 1, True))
        report = json.loads((directory / "cad-2" / "geometry.json").read_text())
        self.assertTrue(report["reopened"] and report["edit"]["preserved_verified"])
        self.assertEqual(incremental_edit.file_sha256(directory / "cad-1" / "draft.dxf"),
                         json.loads((directory / "cad-2" / "edit-plan.json").read_text())["base_sha256"])


if __name__ == "__main__":
    unittest.main()
