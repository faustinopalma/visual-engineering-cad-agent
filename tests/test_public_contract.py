import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_cad_agent import compile_model
from qcad_model import compile_qcad


class PublicContractTests(unittest.TestCase):
    def test_circle_compilation_and_unconfirmed_dimensions(self):
        model = {"notes": "Synthetic", "components": [{"id": "Body", "meaning": "circle", "shapes": [
            {"type": "circle", "points": [[20, 30]], "radius": 5, "closed": True}]}]}
        result = compile_model(model, 100, 100)
        self.assertEqual(result["entities"][0]["center"], [5, 17.5])
        self.assertFalse(result["human_confirmation"])
        model["components"][0]["id"] = "../unsafe"
        with self.assertRaises(ValueError):
            compile_model(model, 100, 100)

    def test_native_hatch_void_and_invalid_region(self):
        shape = {"type": "hatch", "points": [], "radius": 0, "closed": True, "layer": "HATCH", "loops": [
            [[10, 10], [110, 10], [110, 90], [10, 90]], [[40, 30], [40, 60], [70, 60], [70, 30]]], "angle": 0, "spacing": 6}
        model = {"notes": "Synthetic", "components": [{"id": "Section", "meaning": "material around void", "shapes": [shape]}]}
        result = compile_qcad(model, 150, 120)
        self.assertEqual(result["entities"][0]["area"], 443.75)
        invalid = copy.deepcopy(model)
        invalid["components"][0]["shapes"][0]["loops"] = [[[10, 10], [110, 90], [110, 10], [10, 90]]]
        with self.assertRaises(ValueError):
            compile_qcad(invalid, 150, 120)

    def test_configuration_contains_only_placeholders(self):
        config = json.loads((ROOT / "config/astra-example.json").read_text())
        self.assertTrue(config["subscription"].startswith("REPLACE_"))
        self.assertFalse(any(key in config for key in ("api_key", "accessToken", "client_secret")))


if __name__ == "__main__":
    unittest.main()