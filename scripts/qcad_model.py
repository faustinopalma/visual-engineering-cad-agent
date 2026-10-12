import copy
import math

from shapely.geometry import Polygon

from astra_cad_agent import MODEL_SCHEMA, POINT, compile_model, validate_model


LAYERS = ("OUTLINE", "CENTERLINE", "HIDDEN", "HATCH")
QCAD_SCHEMA = copy.deepcopy(MODEL_SCHEMA)
shape_schema = QCAD_SCHEMA["properties"]["components"]["items"]["properties"]["shapes"]["items"]
shape_schema["properties"]["type"]["enum"].append("hatch")
shape_schema["properties"].update(layer={"type": "string", "enum": list(LAYERS)},
    loops={"type": "array", "items": {"type": "array", "items": POINT}},
    angle={"type": "number"}, spacing={"type": "number"})
shape_schema["required"].extend(["layer", "loops", "angle", "spacing"])

GUIDANCE = """Use native QCAD operations represented by structured data, not traced scan lines.
Components become editable native blocks; connected contours become native polylines, closed when appropriate.
Each shape requires layer OUTLINE, CENTERLINE, HIDDEN or HATCH, plus loops, angle, spacing.
For ordinary shapes loops=[], angle=0, spacing=0. Standard line/circle/polyline/spline rules apply.
For hatch type: layer=HATCH, points=[], radius=0, closed=true, loops=[outer polygon, optional hole polygons],
angle is rotation in radians relative to native ANSI31's base 45 degrees; spacing is positive raster-pixel pattern scale.
Prefer angle 0 and spacing 4-12 pixels for technical sections, adjusted for legibility, not copied individual strokes.
Every hatch loop requires at least 3 distinct ordered vertices; closed implicitly, do not repeat first point.
No self-intersections, zero area, crossing islands or holes outside the outer polygon. Curved boundaries may be
polygon approximations ONLY for the hatch clipping region; keep visible curved contour geometry native separately.
Hatch ONLY sectioned material; exclude voids/bores via inner loops. Do not hatch exterior views, axes, hidden lines,
knurl texture or annotation. Adjacent distinct parts can use different angle/spacing. Keep hatch on HATCH layer.
Use outline curves and conventional hidden/centerline segments by meaning. Never produce hundreds of individual
hatch lines. Native hatch errors or open region boundaries must be repaired before quality acceptance.
"""


def compile_qcad(model, width, height):
    if not isinstance(model, dict) or set(model) != {"notes", "components"}:
        raise ValueError("Invalid QCAD model envelope.")
    ordinary = {"notes": model["notes"], "components": []}
    entities = []
    hatch_polygons = []
    def point(value):
        if not isinstance(value, list) or len(value) != 2 or any(isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) for number in value):
            raise ValueError("Invalid hatch coordinate.")
        if not -5 <= value[0] <= width + 5 or not -5 <= value[1] <= height + 5:
            raise ValueError("Hatch coordinate outside source.")
        return [value[0] * 0.25, (height - value[1]) * 0.25]
    names = set()
    for component in model["components"]:
        standard = dict(component, shapes=[])
        for shape in component["shapes"]:
            if set(shape) != {"type", "points", "radius", "closed", "layer", "loops", "angle", "spacing"} or shape["layer"] not in LAYERS:
                raise ValueError("Invalid QCAD shape fields/layer.")
            base = {key: shape[key] for key in ("type", "points", "radius", "closed")}
            if shape["type"] != "hatch":
                if shape["loops"] != [] or shape["angle"] != 0 or shape["spacing"] != 0 or shape["layer"] == "HATCH":
                    raise ValueError("Only native hatches use hatch fields/layer.")
                standard["shapes"].append(base)
            else:
                if shape["layer"] != "HATCH" or shape["points"] != [] or shape["radius"] != 0 or shape["closed"] is not True:
                    raise ValueError("Hatch requires dedicated layer and closed region.")
                if not isinstance(shape["loops"], list) or not 1 <= len(shape["loops"]) <= 20:
                    raise ValueError("Invalid hatch loop count.")
                loops = []
                for loop in shape["loops"]:
                    if not isinstance(loop, list) or not 3 <= len(loop) <= 80:
                        raise ValueError("Hatch loop needs 3-80 vertices.")
                    converted = [point(vertex) for vertex in loop]
                    if len(set(map(tuple, converted))) != len(converted):
                        raise ValueError("Duplicate hatch vertices; closure is implicit.")
                    polygon = Polygon(converted)
                    if not polygon.is_valid or polygon.area < 0.001:
                        raise ValueError("Invalid/self-intersecting/degenerate hatch loop.")
                    loops.append(converted)
                polygon = Polygon(loops[0], loops[1:])
                if not polygon.is_valid or polygon.area < 0.001:
                    raise ValueError("Invalid hatch region or holes outside/crossing shell.")
                for field in ("angle", "spacing"):
                    if isinstance(shape[field], bool) or not isinstance(shape[field], (int, float)) or not math.isfinite(shape[field]):
                        raise ValueError("Nonfinite hatch parameter.")
                if not -math.tau <= shape["angle"] <= math.tau or not 0.5 <= shape["spacing"] <= 50:
                    raise ValueError("Hatch scale/angle out of bounds.")
                hatch_polygons.append(polygon)
                entities.append({"type": "hatch", "component": component["id"], "layer": "HATCH", "loops": loops,
                                 "pattern": "ANSI31", "angle": -shape["angle"], "scale": shape["spacing"] * 0.25,
                                 "area": polygon.area})
        if not standard["shapes"]:
            standard["shapes"] = [{"type": "circle", "points": [[0, 0]], "radius": 1, "closed": False}]
        ordinary["components"].append(standard)
    validate_model(ordinary, width, height)
    count = sum(len(component["shapes"]) for component in model["components"])
    if count > 180 or len(hatch_polygons) > 60:
        raise ValueError("QCAD entity budget exceeded.")
    for component in model["components"]:
        for shape in component["shapes"]:
            if shape["type"] == "hatch":
                continue
            base = {key: shape[key] for key in ("type", "points", "radius", "closed")}
            if shape["type"] == "polyline":
                entity = {"type": "polyline", "points": [point(vertex) for vertex in shape["points"]], "closed": shape["closed"]}
                generated = [entity]
            else:
                generated = compile_model({"notes": "", "components": [dict(component, shapes=[base])]}, width, height)["entities"]
            for entity in generated:
                entity.update(component=component["id"], layer=shape["layer"])
                entities.append(entity)
    for index, entity in enumerate(entities):
        entity["id"] = "Q" + str(index + 1).zfill(4)
    return {"entities": entities, "component_meanings": {component["id"]: component["meaning"] for component in model["components"]},
            "units": "mm", "unit_status": "Display scale only, physical dimensions unconfirmed.", "status": "needs_review", "human_confirmation": False,
            "native_qcad": True}