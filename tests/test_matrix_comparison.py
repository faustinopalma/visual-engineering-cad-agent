import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import matrix_comparison


class MatrixTests(unittest.TestCase):
    def test_plan_run_collect_report_and_viewer(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            source = temporary / "campaign" / "06" / "source"
            source.mkdir(parents=True)
            Image.new("RGB", (400, 300), "white").save(source / "view.png")
            Image.new("RGB", (400, 300), "white").save(source / "page.png")
            models = {}
            for key, deployment in (("astra", "astra-dep"), ("sol", "sol-dep")):
                models[key] = temporary / (key + ".json")
                models[key].write_text(json.dumps({"deployment": deployment, "evaluator_deployment": "astra-dep", "reasoning_effort": "high"}))
            output = temporary / "matrix"
            plan = matrix_comparison.plan_matrix(output, [source], models, 1, 2)
            self.assertEqual(len(plan["routes"]), 12)
            self.assertEqual(sum(route["kind"] != "base" for route in plan["routes"]), 8)
            config = lambda route_id: json.loads(Path(next(route for route in plan["routes"] if route["id"] == route_id)["config"]).read_text())
            self.assertEqual((config("06/freecad/sol/base")["deployment"], config("06/freecad/sol/base")["max_attempts"], config("06/freecad/sol/base")["native_qcad"]),
                             ("sol-dep", 1, False))
            self.assertEqual((config("06/qcad/astra/drafter_choice")["revision_mode"], config("06/qcad/astra/drafter_choice")["max_attempts"],
                              config("06/qcad/astra/drafter_choice")["native_qcad"], config("06/qcad/astra/drafter_choice")["evaluator_deployment"]),
                             ("drafter_choice", 2, True, "astra-dep"))
            self.assertEqual(json.loads((output / "judge.config.json").read_text())["deployment"], "astra-dep")
            self.assertTrue((output / "06-qcad" / "source" / "view.png").exists())

            def fake_process(command, supervisor, environment, timeout):
                directory = Path(command[3])
                directory.mkdir(parents=True, exist_ok=True)
                route = directory.parent.name + "/" + directory.name
                if "--seed-route" in command:
                    self.assertNotEqual(route, "06-qcad/sol-drafter_choice")
                    score = 90 if directory.name.endswith("drafter_choice") else 60
                    candidates = [{"attempt": 1, "seeded": True, "cad": "seed", "score": 70, "accepted": False},
                                  {"attempt": 2, "mode": "edit_existing" if score == 90 else "generated", "base_attempt": 1, "operations": {"replaced": 1},
                                   "cad": str(directory / "cad-2"), "score": score, "accepted": score >= 85}]
                    result = {"status": "internally_accepted" if score >= 85 else "not_accepted", "candidates": candidates,
                              "calls": 4, "input_tokens": 40, "output_tokens": 20, "elapsed_seconds": 10.0}
                else:
                    accepted = route == "06-qcad/sol-base"
                    result = {"status": "internally_accepted" if accepted else "not_accepted", "calls": 3, "input_tokens": 30, "output_tokens": 15,
                              "elapsed_seconds": 5.0, "candidates": [{"attempt": 1, "mode": "generated", "cad": str(directory / "cad-1"),
                                                                     "score": 88 if accepted else 70, "accepted": accepted}]}
                    (directory / "analysis.json").write_text("{}")
                (directory / "result.json").write_text(json.dumps(result))

            original_process, original_root = matrix_comparison.process, matrix_comparison.ROOT
            matrix_comparison.process, matrix_comparison.ROOT = fake_process, temporary
            (temporary / "work").mkdir()
            try:
                matrix_comparison.run(output)
            finally:
                matrix_comparison.process, matrix_comparison.ROOT = original_process, original_root
            self.assertFalse((temporary / "work" / ".astra-campaign.lock").exists())
            _, entries = matrix_comparison.collect(output)
            by_id = {entry["id"]: entry for entry in entries}
            edit = by_id["06/freecad/astra/drafter_choice"]
            self.assertEqual((edit["final"]["origin"], edit["final"]["attempt"], edit["route_cost"]["calls"], edit["route_cost"]["input_tokens"]), ("arm", 2, 7, 70))
            scratch = by_id["06/freecad/astra/full_regeneration"]
            self.assertEqual((scratch["final"]["origin"], scratch["final"]["attempt"], scratch["final"]["score"]), ("base", 1, 70))
            skipped = by_id["06/qcad/sol/drafter_choice"]
            self.assertEqual((skipped["result"]["status"], skipped["final"]["origin"], skipped["final"]["score"]), ("base_accepted", "base", 88))

            matrix_comparison.report(output)
            text = (output / "report.md").read_text(encoding="utf-8")
            self.assertIn("## FreeCAD versus QCAD, same drawing, drafter and strategy", text)
            self.assertIn("| 06 | Astra | edit-capable | 90 | 90 |", text)
            self.assertIn("base attempt 1", text)
            self.assertIn("Not run: the base route was already internally accepted.", text)

            geometry = {"polylines": [[(10, 10), (50, 10)]], "fills": [], "counts": {}, "source": "synthetic"}
            original_geometry = matrix_comparison.native_geometry
            matrix_comparison.native_geometry = lambda cad, compiled: geometry
            try:
                matrix_comparison.viewer(output)
            finally:
                matrix_comparison.native_geometry = original_geometry
            page = (output / "viewer.html").read_text(encoding="utf-8")
            data = json.loads(page.split("const DATA = ", 1)[1].split(";\n", 1)[0])
            layers = data["drawings"][0]["layers"]
            self.assertEqual(len(layers), 12)
            self.assertEqual(layers[0]["key"], "06/freecad/astra/drafter_choice")
            self.assertTrue(layers[0]["visible"])
            self.assertEqual(sum(layer["visible"] for layer in layers), 1)
            self.assertEqual(sum(bool(layer["dash"]) for layer in layers), 4)
            self.assertEqual(len({layer["color"] for layer in layers}), 12)
            self.assertEqual(layers[0]["tags"], ["FreeCAD", "Astra", "edit-capable"])
            self.assertEqual(layers[0]["lines"], "M40.0,260.0 L200.0,260.0")


if __name__ == "__main__":
    unittest.main()
