import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mode_comparison
from mode_comparison import bspline_points, catmull_rom, freecad_geometry, overlay, qcad_geometry, report


def document_xml(placement="Px=\"0\" Py=\"0\" Pz=\"0\" Q0=\"0\" Q1=\"0\" Q2=\"0\" Q3=\"1\""):
    return f"""<?xml version='1.0' encoding='utf-8'?>
<Document><Objects Count="1"><Object type="Sketcher::SketchObject" name="Body"/></Objects>
<ObjectData Count="1"><Object name="Body"><Properties Count="3">
<Property name="Constraints" type="Sketcher::PropertyConstraintList"><ConstraintList count="0"/></Property>
<Property name="Placement" type="App::PropertyPlacement"><PropertyPlacement {placement} A="0" Ox="0" Oy="0" Oz="1"/></Property>
<Property name="Geometry" type="Part::PropertyGeometryList"><GeometryList count="4">
<Geometry type="Part::GeomLineSegment"><LineSegment StartX="1" StartY="2" StartZ="0" EndX="11" EndY="2" EndZ="0"/><Construction value="0"/></Geometry>
<Geometry type="Part::GeomLineSegment"><LineSegment StartX="0" StartY="0" StartZ="0" EndX="99" EndY="99" EndZ="0"/><Construction value="1"/></Geometry>
<Geometry type="Part::GeomCircle"><Circle CenterX="5" CenterY="5" CenterZ="0" NormalX="0" NormalY="0" NormalZ="1" AngleXU="0" Radius="2"/><Construction value="0"/></Geometry>
<Geometry type="Part::GeomBSplineCurve"><BSplineCurve PolesCount="3" KnotsCount="2" Degree="2" IsPeriodic="0">
<Pole X="0" Y="0" Z="0" Weight="1"/><Pole X="1" Y="2" Z="0" Weight="1"/><Pole X="2" Y="0" Z="0" Weight="1"/>
<Knot Value="0" Mult="3"/><Knot Value="1" Mult="3"/></BSplineCurve><Construction value="0"/></Geometry>
</GeometryList></Property></Properties></Object></ObjectData></Document>"""


class GeometryReaderTests(unittest.TestCase):
    def test_bspline_matches_quadratic_bezier(self):
        points = bspline_points([(0, 0), (1, 2), (2, 0)], [1, 1, 1], [0, 0, 0, 1, 1, 1], 2, 4)
        self.assertEqual(points[0], (0.0, 0.0))
        self.assertEqual(points[-1], (2.0, 0.0))
        self.assertAlmostEqual(points[2][0], 1.0)
        self.assertAlmostEqual(points[2][1], 1.0)

    def test_catmull_rom_passes_through_fit_points(self):
        fit = [(0, 0), (3, 4), (7, 3), (10, 0)]
        curve = catmull_rom(fit, 8)
        for point in fit:
            self.assertLess(min(math.dist(point, sample) for sample in curve), 1e-9)

    def test_freecad_reader_skips_construction_and_rejects_moved_sketch(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "draft.FCStd"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("Document.xml", document_xml())
            geometry = freecad_geometry(path)
            self.assertEqual(geometry["counts"], {"Part::GeomLineSegment": 1, "Part::GeomCircle": 1, "Part::GeomBSplineCurve": 1})
            self.assertEqual(geometry["polylines"][0], [(1.0, 2.0), (11.0, 2.0)])
            self.assertTrue(all(abs(math.dist(point, (5, 5)) - 2) < 1e-9 for point in geometry["polylines"][1]))
            moved = Path(temporary) / "moved.FCStd"
            with zipfile.ZipFile(moved, "w") as archive:
                archive.writestr("Document.xml", document_xml("Px=\"10\" Py=\"0\" Pz=\"0\" Q0=\"0\" Q1=\"0\" Q2=\"0\" Q3=\"1\""))
            with self.assertRaisesRegex(ValueError, "placement"):
                freecad_geometry(moved)

    def test_qcad_reader_requires_verified_hatch_loops(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "geometry.json").write_text(json.dumps({"status": "passed", "reopened": True, "entities": [
                {"type": "line", "start": [0, 0], "end": [5, 0]}, {"type": "hatch"}]}))
            (directory / "compiled.json").write_text(json.dumps({"entities": []}))
            with self.assertRaisesRegex(ValueError, "hatch"):
                qcad_geometry(directory / "geometry.json", directory / "compiled.json")
            (directory / "compiled.json").write_text(json.dumps({"entities": [{"type": "hatch", "loops": [[[0, 0], [5, 0], [5, 5]]]}]}))
            geometry = qcad_geometry(directory / "geometry.json", directory / "compiled.json")
            self.assertEqual(len(geometry["fills"]), 1)


class OverlayTests(unittest.TestCase):
    def test_metrics_reward_cad_on_source_lines_and_penalize_offsets(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = Image.new("RGB", (240, 240), "white")
            painter = ImageDraw.Draw(source)
            painter.line([(30, 120), (210, 120)], fill="black", width=4)
            painter.line([(120, 30), (120, 210)], fill="black", width=4)
            source.save(directory / "view.png")
            def cad(x, y):
                return (x * mode_comparison.SCALE, (240 - y) * mode_comparison.SCALE)
            on_line = {"polylines": [[cad(40, 120), cad(200, 120)]], "fills": [], "counts": {}, "source": "synthetic"}
            metrics = overlay(directory / "view.png", on_line, directory / "on")
            self.assertGreater(metrics["ink_precision"], 0.99)
            self.assertTrue(0.3 < metrics["ink_recall"] < 0.7)
            offset = {"polylines": [[cad(40, 150), cad(200, 150)]], "fills": [], "counts": {}, "source": "synthetic"}
            moved = overlay(directory / "view.png", offset, directory / "off")
            self.assertLess(moved["ink_precision"], 0.1)
            for name in ("overlay.png", "agreement.png", "overlay-metrics.json"):
                self.assertTrue((directory / "on" / name).exists())


class ReportTests(unittest.TestCase):
    def test_report_tabulates_start_and_both_arms(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "comparison"
            seed = Path(temporary) / "seed" / "astra"
            (seed / "cad-1").mkdir(parents=True)
            (seed / "cad-1" / "build.json").write_text("{}")
            (seed / "1-model.json").write_text(json.dumps({"components": []}))
            (seed / "1-evaluation.json").write_text(json.dumps({"score": 70, "accepted": False, "defects": [], "correction_instructions": ""}))
            arms = []
            for mode in mode_comparison.MODES:
                route = output / "06-freecad-neka" / mode
                route.mkdir(parents=True)
                (output / "06-freecad-neka" / (mode + ".config.json")).write_text(json.dumps({"revision_mode": mode, "max_attempts": 2}))
                arms.append({"label": "06-freecad-neka", "seed": str(seed), "method": "freecad-neka", "mode": mode, "route": str(route),
                             "config": str(output / "06-freecad-neka" / (mode + ".config.json"))})
            (output / "06-freecad-neka" / "source").mkdir()
            seeded = {"attempt": 1, "seeded": True, "score": 70}
            (output / "06-freecad-neka" / "drafter_choice" / "result.json").write_text(json.dumps({
                "status": "not_accepted", "calls": 4, "input_tokens": 100, "output_tokens": 50, "elapsed_seconds": 12.0,
                "candidates": [seeded, {"attempt": 2, "mode": "edit_existing", "base_attempt": 1, "operations": {"replace": 1},
                                        "cad": "x", "score": 82, "accepted": False}]}))
            (output / "06-freecad-neka" / "full_regeneration" / "result.json").write_text(json.dumps({
                "status": "not_accepted", "calls": 2, "candidates": [seeded, {"attempt": 2, "mode": "generated", "error": "Geometry budget exceeded."}]}))
            (output / "plan.json").write_text(json.dumps({"created_unix_seconds": 1, "max_attempts": 2, "arms": arms,
                                                          "code": {"branch": "b", "commit": "abcdef1", "dirty": False}}))
            (output / "judge.config.json").write_text(json.dumps({"deployment": "judge"}))
            mode_comparison.add_arm(output, "06-freecad-neka", "drafter_choice", "drafter_choice-rerun", "validator fix")
            with self.assertRaisesRegex(ValueError, "already used"):
                mode_comparison.add_arm(output, "06-freecad-neka", "drafter_choice", "drafter_choice-rerun", "again")
            rerun = output / "06-freecad-neka" / "drafter_choice-rerun"
            self.assertEqual(json.loads((output / "06-freecad-neka" / "drafter_choice-rerun.config.json").read_text())["revision_mode"], "drafter_choice")
            rerun.mkdir()
            (rerun / "result.json").write_text(json.dumps({"status": "not_accepted", "candidates": [seeded, {"attempt": 2, "mode": "regenerate", "cad": "y", "score": 77, "accepted": False}]}))
            for name, adherence in (("06-freecad-neka__start", 60), ("06-freecad-neka__drafter_choice__2", 75)):
                (output / "overlays" / name).mkdir(parents=True)
                (output / "overlays" / name / "overlay-metrics.json").write_text(json.dumps({"ink_precision": 0.8, "ink_recall": 0.4}))
                (output / "overlays" / name / "overlay-judgment.json").write_text(json.dumps({"adherence_score": adherence, "coverage_score": 50, "assessment": "ok"}))
            report(output)
            text = (output / "report.md").read_text(encoding="utf-8")
            self.assertIn("| 06-freecad-neka | start (seed) | attempt 1 |", text)
            self.assertIn("edit_existing (base 1; replace 1)", text)
            self.assertIn("| 75 |", text)
            self.assertIn("no valid new output", text)
            self.assertIn("generated -> failed validation", text)
            table = text.split("## All new candidates")[0]
            self.assertLess(table.index("| drafter_choice |"), table.index("| drafter_choice-rerun |"))
            self.assertLess(table.index("| drafter_choice-rerun |"), table.index("| full_regeneration |"))
            self.assertIn("Extra arm 06-freecad-neka / drafter_choice-rerun", text)
            self.assertTrue((output / "report.html").exists())


if __name__ == "__main__":
    unittest.main()
