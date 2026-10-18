import argparse
from html import escape
from pathlib import Path
import shutil
import json
import hashlib
import re
import sys

from PIL import Image, ImageChops, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
REPOSITORY = "https://github.com/faustinopalma/visual-engineering-cad-agent"
STYLE = """
:root {
  color-scheme: light;
  --cp-bg: #f7f4ef;
  --cp-bg-elevated: #fcfbf8;
  --cp-surface: #ffffff;
  --cp-surface-soft: #f5f5f5;
  --cp-border: #dedede;
  --cp-border-strong: #919191;
  --cp-text: #242424;
  --cp-text-muted: #5c5c5c;
  --cp-text-soft: #6f6f6f;
  --cp-accent: #b11f4b;
  --cp-accent-hover: #9a1a41;
  --cp-accent-soft: rgba(177, 31, 75, 0.08);
  --cp-accent-fg: #ffffff;
  --cp-success: #16a34a;
  --cp-danger: #dc2626;
  --cp-warning: #f59e0b;
  --cp-link: #0078d4;
  --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.12);
  --cp-overlay: rgba(255, 255, 255, 0.8);
  --cp-panel: rgba(255, 255, 255, 0.86);
  --cp-panel-strong: rgba(255, 255, 255, 0.96);
  --cp-sheen: rgba(255, 255, 255, 0.55);
  --cp-highlight: rgba(177, 31, 75, 0.12);
}
html[data-theme="dark"] {
  color-scheme: dark;
  --cp-bg: #3d3b3a;
  --cp-bg-elevated: #343231;
  --cp-surface: #292929;
  --cp-surface-soft: #2e2e2e;
  --cp-border: #474747;
  --cp-border-strong: #5f5f5f;
  --cp-text: #dedede;
  --cp-text-muted: #919191;
  --cp-text-soft: #b0b0b0;
  --cp-accent: #fd8ea1;
  --cp-accent-hover: #fb7b91;
  --cp-accent-soft: rgba(253, 142, 161, 0.14);
  --cp-accent-fg: #1a1a1a;
  --cp-success: #4ade80;
  --cp-danger: #f87171;
  --cp-warning: #fbbf24;
  --cp-link: #4da6ff;
  --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
  --cp-overlay: rgba(41, 41, 41, 0.88);
  --cp-panel: rgba(41, 41, 41, 0.72);
  --cp-panel-strong: rgba(41, 41, 41, 0.96);
  --cp-sheen: rgba(255, 255, 255, 0.04);
  --cp-highlight: rgba(253, 142, 161, 0.12);
}
*{box-sizing:border-box}body{margin:0;background:var(--cp-surface);color:var(--cp-text);font-family:"Segoe UI",Aptos,Calibri,-apple-system,BlinkMacSystemFont,sans-serif;line-height:1.65;letter-spacing:0}
a{color:var(--cp-link);text-underline-offset:4px}a:hover{color:var(--cp-accent)}a:focus-visible,select:focus-visible{outline:3px solid var(--cp-accent);outline-offset:4px}
.skip{position:absolute;left:12px;top:-80px;background:var(--cp-surface);padding:12px;z-index:2}.skip:focus{top:12px}
header{border-bottom:1px solid var(--cp-border);background:var(--cp-bg-elevated)}.top{max-width:1180px;margin:auto;padding:20px 28px;display:flex;flex-wrap:wrap;gap:20px;align-items:center;justify-content:space-between}.brand{font-weight:700;color:var(--cp-text);text-decoration:none;font-size:18px}nav{display:flex;flex-wrap:wrap;gap:20px;align-items:center}nav a{text-decoration:none;color:var(--cp-text-muted);font-size:14px}nav a[aria-current]{color:var(--cp-accent);border-bottom:2px solid var(--cp-accent)}select{font:inherit;font-size:13px;padding:6px;background:var(--cp-surface);color:var(--cp-text);border:1px solid var(--cp-border)}
main{max-width:1180px;margin:auto;padding:42px 28px 70px}.eyebrow{font-size:12px;font-weight:700;text-transform:uppercase;color:var(--cp-accent)}h1{font-size:40px;line-height:1.15;margin:12px 0 18px;max-width:950px;overflow-wrap:anywhere}h2{font-size:25px;line-height:1.25;margin:0 0 16px}h3{font-size:18px;margin:0 0 8px}p{margin:0 0 16px;max-width:78ch}.lead{font-size:19px;color:var(--cp-text-muted);max-width:75ch}.intro{padding-bottom:28px}.band{padding:36px 0;border-top:1px solid var(--cp-border)}.two{display:grid;grid-template-columns:1fr 1fr;gap:32px}.notice{padding:16px 20px;border-left:4px solid var(--cp-accent);background:var(--cp-accent-soft);margin:24px 0;font-size:15px}
figure{margin:0}figure img{display:block;width:100%;height:300px;object-fit:contain;background:var(--cp-surface-soft);border:1px solid var(--cp-border)}figcaption{color:var(--cp-text-muted);font-size:14px;margin-top:12px}.figure-title{display:block;font-size:16px;font-weight:600;color:var(--cp-text)}.table-scroll{overflow-x:auto;margin:20px 0;border-top:2px solid var(--cp-accent)}table{border-collapse:collapse;width:100%;font-size:14px;min-width:620px}th,td{text-align:left;padding:13px 12px;border-bottom:1px solid var(--cp-border);vertical-align:top}th{background:var(--cp-surface-soft);font-weight:600}td.num{font-variant-numeric:tabular-nums;text-align:right}.muted{color:var(--cp-text-muted);font-size:14px}code,pre{font-family:Consolas,"Courier New",Courier,monospace}pre{background:var(--cp-surface-soft);padding:20px;overflow:auto;border:1px solid var(--cp-border);font-size:13px}.flow{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin:24px 0}.step{padding:18px;border:1px solid var(--cp-border);background:var(--cp-bg-elevated);min-height:145px}.step span{display:block;font-size:12px;color:var(--cp-accent);font-weight:700}.step p{font-size:14px;color:var(--cp-text-muted);margin:6px 0 0}.bars{max-width:800px}.bar-row{display:grid;grid-template-columns:180px 1fr 65px;gap:16px;align-items:center;margin:16px 0;font-size:14px}.track{height:16px;background:var(--cp-surface-soft)}.fill{height:16px;background:var(--cp-accent)}ul{padding-left:22px;max-width:78ch}li{margin:8px 0}footer{border-top:1px solid var(--cp-border);background:var(--cp-bg-elevated);padding:24px 28px;font-size:13px;color:var(--cp-text-muted)}footer div{max-width:1124px;margin:auto;display:flex;flex-wrap:wrap;gap:20px;justify-content:space-between}
.two{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.two>*{min-width:0}.table-scroll{max-width:100%;min-width:0}.comparison img{height:400px}.intro.home{padding-bottom:12px}.home+.band{padding-top:24px}.three{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.three>*{min-width:0}
@media(max-width:700px){.three{grid-template-columns:1fr;gap:28px}}
@media(max-width:700px){.top{padding:18px}.brand{font-size:16px}nav{gap:14px}main{padding:30px 18px 50px}h1{font-size:30px}.lead{font-size:17px}.two{grid-template-columns:1fr;gap:28px}.flow{grid-template-columns:1fr 1fr}figure img{height:240px}.bar-row{grid-template-columns:110px 1fr 48px;gap:8px}.band{padding:28px 0}}
@media(prefers-reduced-motion:no-preference){main{animation:appear .3s ease-out}@keyframes appear{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}}
@media(max-width:700px){.comparison img{height:280px}}
.architecture-map{margin:24px 0}.architecture-route{display:grid;grid-template-columns:minmax(0,1fr) 30px minmax(0,1fr) 30px minmax(0,1fr);align-items:stretch;gap:8px}.architecture-node{border:1px solid var(--cp-border-strong);border-radius:4px;padding:18px;background:var(--cp-bg-elevated);min-width:0}.architecture-node h3{font-size:18px}.architecture-node p{font-size:14px;margin:8px 0 0}.architecture-node .place{display:block;font-size:12px;font-weight:700;color:var(--cp-accent);margin-bottom:8px}.route-arrow{display:flex;align-items:center;justify-content:center;color:var(--cp-text-muted)}.route-arrow svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:2}.route-down{height:44px;width:100%;display:flex;align-items:center;justify-content:center}.route-down svg{fill:none;stroke:var(--cp-text-muted);stroke-width:2}.route-down .desktop-return{width:100%;height:44px}.route-down .mobile-return{display:none;width:24px;height:24px}.feedback-route{border-left:3px solid var(--cp-accent);background:var(--cp-accent-soft);padding:14px 18px;margin:16px 0}.feedback-route p{margin:0;font-size:14px}.outputs-route{border-top:2px solid var(--cp-success);padding-top:18px;margin-top:24px}.architecture-roles{display:grid;grid-template-columns:180px minmax(0,1fr);gap:0 24px;margin:0}.architecture-roles dt,.architecture-roles dd{border-top:1px solid var(--cp-border);padding:16px 0;margin:0}.architecture-roles dt{font-weight:600}.architecture-roles dd p{margin:0}.code-link{font-size:13px;display:block;margin-top:8px}
@media(max-width:700px){.architecture-route{grid-template-columns:1fr;gap:0}.route-arrow{height:36px}.route-arrow svg{transform:rotate(90deg)}.route-down{height:36px}.route-down .desktop-return{display:none}.route-down .mobile-return{display:block}.architecture-roles{grid-template-columns:1fr}.architecture-roles dd{border:0;padding-top:0}.architecture-node{padding:16px}}
.architecture-map{position:relative;padding-right:44px}.feedback-arrows{position:absolute;inset:0;pointer-events:none;width:100%;height:100%;overflow:visible}.feedback-arrows path{fill:none;stroke:var(--cp-accent);stroke-width:1.5;vector-effect:non-scaling-stroke}.feedback-arrows .execution-return{stroke-dasharray:5 4}
@media(max-width:700px){.architecture-map{padding-right:32px}}
"""


def page(filename, title, content):
    navigation = "".join('<a href="' + path + '"' + (' aria-current="page"' if path == filename else '') + '>' + label + '</a>'
                         for path, label in (("index.html", "Overview"), ("examples.html", "Examples"), ("architecture.html", "Architecture"), ("experiments.html", "Experiments")))
    document = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Open-source experiments in visual engineering to editable CAD, with deterministic execution and explicit review gates.">
<title>''' + escape(title) + ''' | Visual Engineering CAD Agent</title>
<script>(()=>{const param=new URLSearchParams(window.location.search).get("scoutTheme");const theme=param||(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.setAttribute("data-theme",theme);})();</script>
<style>''' + STYLE + '''</style></head><body><a class="skip" href="#main">Skip to content</a><header><div class="top"><a class="brand" href="index.html">Visual Engineering CAD Agent</a><nav aria-label="Main navigation">''' + navigation + '''<a href="''' + REPOSITORY + '''">GitHub</a><select id="theme" aria-label="Color theme"><option value="light">Light</option><option value="dark">Dark</option></select></nav></div></header><main id="main">''' + content + '''</main><footer><div><span>MIT project code and documentation. Third-party software retains its own licenses.</span><a href="''' + REPOSITORY + '''/blob/main/EVOLVING_CAD_AGENT_PLAN.md">Evolving project plan</a><span>Experiment snapshot: October 2026</span></div></footer>
<script>const theme=document.getElementById("theme");theme.value=document.documentElement.getAttribute("data-theme");theme.addEventListener("change",()=>{document.documentElement.setAttribute("data-theme",theme.value);const url=new URL(location.href);url.searchParams.set("scoutTheme",theme.value);history.replaceState(null,"",url);});</script></body></html>'''
    (SITE / filename).write_text(document, encoding="utf-8")


def copy_reviewed_drawings():
    campaign = ROOT / "work/qcad-native-astra-sol-all-20261011"
    cases = [("05", "astra", "Mechanical assembly", "Three views, a longitudinal section, native hatches and union fittings."),
             ("01", "astra", "Section and plan", "Sectioned housing, internal passages, concentric details and mounting holes."),
             ("07", "astra", "Turned component", "Stepped profile, rounded transitions and a knurled band.")]
    released = []
    for drawing, generator, title, description in cases:
        result = json.loads((campaign / drawing / generator / "result.json").read_text())
        cad = Path(result["last_valid_cad"])
        latest_build = max(result["builds"], key=lambda build: build["attempt"])
        geometry = json.loads((cad / "geometry.json").read_text())
        if cad != Path(latest_build["directory"]):
            raise ValueError("Selected example is not the latest persisted revision.")
        if geometry["status"] != "passed" or not geometry["reopened"]:
            raise ValueError("Selected example did not pass the recorded checks.")
        source = Image.open(campaign / drawing / "source/page.png").convert("RGB")
        source.save(SITE / "assets" / ("drawing-" + drawing + "-input.png"))
        output = Image.open(cad / "preview.png").convert("RGB")
        mask = ImageChops.difference(output, Image.new("RGB", output.size, "white")).convert("L").point(lambda value: 255 if value > 50 else 0)
        box = mask.getbbox()
        if box is None:
            raise ValueError("Blank example output.")
        output = ImageOps.expand(output.crop(box), border=16, fill="white")
        output.save(SITE / "assets" / ("drawing-" + drawing + "-output.png"))
        shutil.copy2(cad / "draft.dxf", SITE / "assets" / ("drawing-" + drawing + "-output.dxf"))
        released.append({"drawing": drawing, "generator": generator, "backend": "QCAD", "title": title,
                         "description": description, "native_entities": len(geometry["entities"]),
                         "native_hatches": sum(item["type"] == "hatch" for item in geometry["entities"]),
                         "reopened": True, "internal_evaluation": result["status"], "human_dimensional_approval": False,
                         "source_campaign": campaign.name, "source_revision": cad.name,
                         "selection_basis": "Latest persisted Astra revision, selected by the user for the examples.",
                         "publication_authorization": "User authorized selected drawing inputs and outputs on October 12, 2026."})
    (SITE / "assets/drawing-examples.json").write_text(json.dumps(released, indent=2) + "\n", encoding="utf-8")


MATRIX_FEATURED = [
    ("03", "qcad", "astra", "drafter_choice", "Gear housing section, edited in place",
     "A sectioned right-angle gear assembly: two shafts, ball bearings, gear webs and native QCAD section hatches."),
    ("06", "freecad", "astra", "drafter_choice", "Motor and screw jack, edited in place",
     "Front and side views of a geared motor driving a lead screw, rebuilt as FreeCAD sketches without hatching."),
]
MATRIX_GROUPS = [("FreeCAD", {"backend": "freecad"}), ("QCAD", {"backend": "qcad"}),
                 ("Astra drafter", {"model": "astra"}), ("Sol drafter", {"model": "sol"}),
                 ("Edit-capable", {"kind": "drafter_choice"}), ("From scratch", {"kind": "full_regeneration"}),
                 ("Astra, edit-capable", {"model": "astra", "kind": "drafter_choice"}), ("Astra, from scratch", {"model": "astra", "kind": "full_regeneration"}),
                 ("Sol, edit-capable", {"model": "sol", "kind": "drafter_choice"}), ("Sol, from scratch", {"model": "sol", "kind": "full_regeneration"})]


def cropped_preview(source, target):
    output = Image.open(source).convert("RGB")
    mask = ImageChops.difference(output, Image.new("RGB", output.size, "white")).convert("L").point(lambda value: 255 if value > 50 else 0)
    box = mask.getbbox()
    if box is None:
        raise ValueError("Blank example output: " + str(source))
    ImageOps.expand(output.crop(box), border=16, fill="white").save(target)


def public_text(text):
    """Replace private inference deployment names with the public model names."""
    return re.sub(r"\b(?:lab|cad)-gpt-[\w.-]+", lambda match: "Sol" if "sol" in match.group(0) else "Astra", text)


def copy_matrix_comparison(matrix):
    sys.path.insert(0, str(ROOT / "scripts"))
    import matrix_comparison

    matrix = Path(matrix).resolve()
    plan, entries = matrix_comparison.collect(matrix)
    arms = [entry for entry in entries if entry["kind"] != "base"]
    for entry in arms:
        entry["metrics"], entry["judgment"] = matrix_comparison.evidence(matrix, entry)
    viewer = (matrix / "viewer.html").read_text(encoding="utf-8")
    for drawing in dict.fromkeys(entry["drawing"] for entry in entries):
        label = drawing + "-freecad"
        source = matrix / label / "source"
        if (source / "view.png").read_bytes() != (source / "page.png").read_bytes():
            raise ValueError("Matrix overlays use a cropped view; publish the view image instead of the page.")
        shutil.copy2(source / "page.png", SITE / "assets" / ("drawing-" + drawing + "-input.png"))
        reference = '"image":"' + label + '/source/view.png"'
        if reference not in viewer:
            raise ValueError("Viewer image reference not found: " + reference)
        viewer = viewer.replace(reference, '"image":"assets/drawing-' + drawing + '-input.png"')
    viewer = public_text(viewer).replace('<h1 id="title">', '<p style="margin:0 0 6px"><a href="experiments.html">&larr; Experiments</a></p><h1 id="title">', 1)
    if re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]|source/view\.png|Users[\\/]", viewer):
        raise ValueError("Public viewer still references local paths.")
    (SITE / "matrix-viewer.html").write_text(viewer, encoding="utf-8")

    featured = []
    for drawing, backend, model, kind, title, description in MATRIX_FEATURED:
        entry = next(item for item in arms if (item["drawing"], item["backend"], item["model"], item["kind"]) == (drawing, backend, model, kind))
        final, cad = entry["final"], Path(entry["final"]["cad"])
        geometry = json.loads((cad / "geometry.json").read_text())
        if final["origin"] != "arm" or not final["accepted"] or geometry["status"] != "passed" or not geometry["reopened"]:
            raise ValueError("Featured matrix output is not an accepted, reopened arm candidate: " + entry["id"])
        edits = [item for item in entry["result"]["candidates"] if not item.get("seeded") and item.get("mode") == "edit_existing"]
        if not edits:
            raise ValueError("Featured edit-capable output contains no edit: " + entry["id"])
        stem = "drawing-" + drawing + "-" + backend + "-edit"
        native = cad / ("draft.dxf" if backend == "qcad" else "draft.FCStd")
        cropped_preview(cad / "preview.png", SITE / "assets" / (stem + "-output.png"))
        shutil.copy2(matrix_comparison.overlay_dir(matrix, cad) / "overlay.png", SITE / "assets" / (stem + "-overlay.png"))
        shutil.copy2(native, SITE / "assets" / (stem + native.suffix))
        featured.append({"drawing": drawing, "backend": matrix_comparison.BACKENDS[backend]["title"], "drafter": model.capitalize(),
                         "strategy": "edit-capable (drafter_choice)", "title": title, "description": description,
                         "input": "drawing-" + drawing + "-input.png", "output": stem + "-output.png", "overlay": stem + "-overlay.png",
                         "native": stem + native.suffix, "attempt": final["attempt"], "internal_score": final["score"],
                         "internal_evaluation": "accepted", "drafter_decisions": matrix_comparison.decisions(entry["result"]),
                         "judge_adherence": entry["judgment"].get("adherence_score"), "judge_coverage": entry["judgment"].get("coverage_score"),
                         "ink_precision": entry["metrics"].get("ink_precision"), "native_entities": len(geometry["entities"]),
                         "reopened": True, "human_dimensional_approval": False, "source_campaign": matrix.name})
    groups = []
    for name, keys in MATRIX_GROUPS:
        group = [entry for entry in arms if all(entry[key] == value for key, value in keys.items())]
        scored = [entry for entry in group if entry["final"]]
        groups.append({"group": name, "outputs": len(group), "accepted": sum(entry["final"]["accepted"] for entry in scored),
                       "mean_internal": matrix_comparison.mean([entry["final"]["score"] for entry in scored]),
                       "judge_adherence": matrix_comparison.mean([entry["judgment"].get("adherence_score") for entry in group]),
                       "judge_coverage": matrix_comparison.mean([entry["judgment"].get("coverage_score") for entry in group]),
                       "ink_precision": matrix_comparison.mean([entry["metrics"].get("ink_precision") for entry in group]),
                       "input_tokens": sum(entry["route_cost"]["input_tokens"] for entry in group),
                       "output_tokens": sum(entry["route_cost"]["output_tokens"] for entry in group),
                       "seconds": round(sum(entry["route_cost"]["elapsed_seconds"] for entry in group))})
    manifest = {"campaign": matrix.name, "code": plan["code"], "outputs": len(arms), "featured": featured, "groups": groups,
                "selection_basis": "Edit-capable outputs that made at least one native edit and passed the internal evaluation; the user prefers the edit-capable strategy.",
                "publication_authorization": "User authorized publishing the matrix experiment, its inputs and outputs on October 18, 2026."}
    (SITE / "assets/matrix-comparison.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def matrix_examples(manifest):
    content = ""
    for case in manifest["featured"]:
        name = "assets/" + case["output"]
        revision = hashlib.sha256((SITE / "assets" / case["native"]).read_bytes()).hexdigest()[:12]
        kind = "DXF" if case["native"].endswith(".dxf") else "FreeCAD document"
        steps = "; ".join(case["drafter_decisions"]).replace("edit_existing", "edit").replace("base ", "candidate ")
        content += ('<section class="band"><h2>' + escape(case["title"]) + '</h2><p>' + escape(case["description"]) + ' ' + case["backend"] + ' / ' + case["drafter"]
                    + ', edit-capable strategy. Drafter decisions: ' + escape(steps) + '.</p><div class="three comparison">'
                    + '<figure><a href="assets/' + case["input"] + '"><img src="assets/' + case["input"] + '" alt="Original scan of drawing ' + case["drawing"] + '"></a><figcaption><span class="figure-title">Input: original scan</span></figcaption></figure>'
                    + '<figure><a href="' + name + '?v=' + revision + '"><img src="' + name + '?v=' + revision + '" alt="Native ' + case["backend"] + ' reconstruction of drawing ' + case["drawing"] + '"></a><figcaption><span class="figure-title">Output: editable CAD</span>Rendered from the saved, reopened file.</figcaption></figure>'
                    + '<figure><a href="assets/' + case["overlay"] + '?v=' + revision + '"><img src="assets/' + case["overlay"] + '?v=' + revision + '" alt="Reconstruction drawn over the original scan of drawing ' + case["drawing"] + '"></a><figcaption><span class="figure-title">Overlay on the scan</span>Internal score ' + str(case["internal_score"])
                    + ', judge adherence ' + str(case["judge_adherence"]) + '/' + str(case["judge_coverage"]) + ' coverage, ink precision ' + format(case["ink_precision"], ".0%") + '.</figcaption></figure></div>'
                    + '<p style="margin-top:16px"><a href="assets/' + case["native"] + '?v=' + revision + '" download>Download ' + kind + '</a> &nbsp; <a href="matrix-viewer.html">Compare all versions in the overlay viewer</a></p></section>')
    return content


def matrix_band(manifest):
    rows = "".join("<tr><td>" + escape(item["group"]) + "</td><td class=num>" + str(item["accepted"]) + " / " + str(item["outputs"]) + "</td><td class=num>" + format(item["mean_internal"], ".1f")
                   + "</td><td class=num>" + format(item["judge_adherence"], ".1f") + " / " + format(item["judge_coverage"], ".1f") + "</td><td class=num>" + format(item["ink_precision"], ".1%")
                   + "</td><td class=num>" + format(item["input_tokens"], ",") + " / " + format(item["output_tokens"], ",") + "</td></tr>" for item in manifest["groups"])
    return ('<section class="band"><h2>Matrix: backend, drafter model and strategy</h2><p>Three drawings (06, 03, 10) were rebuilt by FreeCAD and QCAD, with Astra and Sol as drafter, each with the edit-capable strategy and with regeneration from scratch: '
            + str(manifest["outputs"]) + ' final outputs. Each drawing, backend and drafter combination began with one shared attempt; each strategy then added two attempts. The evaluator, the blind overlay judge, reasoning effort and limits were the same everywhere. FreeCAD has no hatch entity, so it was told to omit hatching and was not penalized for it.</p>'
            + '<div class="table-scroll"><table><thead><tr><th>Group</th><th>Internally accepted</th><th>Mean internal score</th><th>Judge adherence / coverage</th><th>Ink precision</th><th>Input / output tokens</th></tr></thead><tbody>'
            + rows + '</tbody></table></div><ul><li><strong>Strategy:</strong> overall a tie, 5/12 each. With the stronger Astra drafter the edit-capable arms were accepted slightly more often and scored higher, and editing used about 12% fewer output tokens. It remains the default revision mode.</li>'
            + '<li><strong>Drafter:</strong> Astra did better than Sol on every aggregate and was faster.</li><li><strong>Backend:</strong> FreeCAD was accepted more often than QCAD, but QCAD was also judged on hatching, which FreeCAD omits, so the comparison is not like-for-like.</li></ul>'
            + '<p><a href="matrix-viewer.html">Open the full-page overlay viewer</a>: toggle the original and every version per drawing, filter by backend, drafter or strategy.</p>'
            + '<p class="muted">One route per cell; differences of a few points are within judge and route variation. The judge and drafters share a provider. The client switched to streamed responses mid-run after network drops, and two FreeCAD bases lost their first attempt to an MCP connection timeout. No output has human approval; the overlay is not metrology.</p></section>')


def drawing_pair(drawing, title, description):
    name = "assets/drawing-" + drawing
    revision = hashlib.sha256((SITE / (name + "-output.dxf")).read_bytes()).hexdigest()[:12]
    output = name + "-output.png?v=" + revision
    download = name + "-output.dxf?v=" + revision
    return '<section class="band"><h2>' + escape(title) + '</h2><p>' + escape(description) + '</p><div class="two comparison"><figure><a href="' + name + '-input.png"><img src="' + name + '-input.png" alt="Original degraded scan for drawing ' + drawing + '"></a><figcaption><span class="figure-title">Input: original scan</span></figcaption></figure><figure><a href="' + output + '"><img src="' + output + '" alt="Actual native QCAD reconstruction of drawing ' + drawing + '"></a><figcaption><span class="figure-title">Output: editable CAD</span>Generated geometry, rendered from the saved DXF.</figcaption></figure></div><p style="margin-top:16px"><a href="' + download + '" download>Download DXF</a></p></section>'


def build(copy_assets=False, reviewed_drawings=False, matrix=None):
    SITE.mkdir(exist_ok=True)
    (SITE / "assets").mkdir(exist_ok=True)
    if reviewed_drawings:
        copy_reviewed_drawings()
    if matrix:
        copy_matrix_comparison(matrix)
    matrix_manifest = SITE / "assets/matrix-comparison.json"
    matrix_manifest = json.loads(matrix_manifest.read_text()) if matrix_manifest.exists() and (SITE / "matrix-viewer.html").exists() else None
    if copy_assets:
        sources = {"freecad-synthetic.png": ROOT / "work/20261010T085534Z-94fa927a/revised.png",
               "freecad-input.png": ROOT / "work/20261010T085534Z-94fa927a/initial.png",
               "freecad-example.FCStd": ROOT / "work/20261010T085534Z-94fa927a/revised.FCStd",
               "qcad-hatch.png": ROOT / "work/qcad-hatch-probe-a6cf98c9/cad-visible/preview.png",
               "qcad-hatch.dxf": ROOT / "work/qcad-hatch-probe-a6cf98c9/cad-visible/draft.dxf",
               "qcad-boundaries.json": ROOT / "work/qcad-hatch-probe-a6cf98c9/model.json"}
        for name, source in sources.items():
            if not source.exists():
                raise FileNotFoundError("Synthetic evidence asset missing: " + str(source))
            shutil.copy2(source, SITE / "assets" / name)
        image = Image.new("RGB", (1200, 800), "white")
        painter = ImageDraw.Draw(image)
        model = json.loads((SITE / "assets/qcad-boundaries.json").read_text())
        hatch = next(entity for entity in model["entities"] if entity["type"] == "hatch")
        for loop in hatch["loops"]:
            points = [(200 + (point[0] - 2.5) * 28, 680 - (point[1] - 7.5) * 28) for point in loop]
            painter.line(points + points[:1], fill="black", width=3)
        image.save(SITE / "assets/qcad-boundaries.png")
    for name in ("freecad-synthetic.png", "qcad-hatch.png"):
        if not (SITE / "assets" / name).exists():
            raise FileNotFoundError("Run with --copy-local-synthetic-assets once, or use the released assets.")
    page("index.html", "Overview", '''<section class="intro"><div class="eyebrow">Experimental local converter</div><h1>Visual Engineering CAD Agent</h1><p class="lead">Convert drawing images and PDFs into editable CAD with FreeCAD or QCAD.</p><p>A model reads the drawing and proposes components. Local scripts create the CAD file, reopen it for checks, and render it for review.</p></section>
<section class="band"><h2>Working examples</h2><div class="two"><figure><a href="assets/freecad-synthetic.png"><img src="assets/freecad-synthetic.png" alt="FreeCAD rectangle and two circles after a dimension change" width="1200" height="800"></a><figcaption><span class="figure-title">FreeCAD: dimension changes</span>Changing the rectangle width updates the constrained geometry. Measurements are checked after reopening the saved file.</figcaption></figure><figure><a href="assets/qcad-hatch.png"><img src="assets/qcad-hatch.png" alt="QCAD section hatch with an internal hole" width="1200" height="800"></a><figcaption><span class="figure-title">QCAD: native section hatch</span>The hatch uses closed boundaries and excludes the internal hole. Pattern, area and layer are checked after reopening the DXF.</figcaption></figure></div></section>
<section class="band"><h2>Current scope</h2><p>The local agent supports generation, CAD checks and model-requested corrections. Remote conversion jobs are planned. FreeCAD and QCAD remain under evaluation.</p><p><a href="examples.html">Input and output examples</a> &nbsp; <a href="architecture.html">Architecture</a> &nbsp; <a href="experiments.html">Results and timings</a></p><p class="muted">Generated drawings remain drafts requiring technical review.</p></section>
<section class="band two"><div><h2>Backend choices</h2><p>FreeCAD supports constraints and a possible future 3D workflow. QCAD supports 2D layers, blocks, polylines and hatches. The project currently reconstructs 2D drawings only.</p></div><div><h2>Reuse</h2><p>Code and documentation use MIT. Outputs include native CAD, DXF, JSON, PNG and PDF. Rough sketches are a possible next input; they need adapted prompts and fresh tests.</p><p class="muted">Private drawings and derived images are excluded. Third-party software keeps its own license.</p></div></section>''')
    page("examples.html", "Examples", '''<section class="intro"><div class="eyebrow">Input / output</div><h1>Examples</h1><p class="lead">Two successful native CAD operations, with downloadable files.</p><p>These examples use synthetic geometry. They show editable output and saved-file checks; they are not scan-reconstruction accuracy tests.</p></section>
<section class="band"><h2>FreeCAD: change a dimension</h2><p>Increase a constrained rectangle from 100 to 120 units wide. Keep its height and both circle radii unchanged; preserve the circles' relationships to the edges.</p><div class="two"><figure><a href="assets/freecad-input.png"><img src="assets/freecad-input.png" alt="Input FreeCAD synthetic rectangle 100 units wide and two constrained circles" width="1200" height="800"></a><figcaption><span class="figure-title">Input</span>Known synthetic geometry before the dimension change.</figcaption></figure><figure><a href="assets/freecad-synthetic.png"><img src="assets/freecad-synthetic.png" alt="Output FreeCAD rectangle widened to 120 units, preserving circle constraints" width="1200" height="800"></a><figcaption><span class="figure-title">Output</span>Native parametric edit, saved and reopened for measurement.</figcaption></figure></div><p style="margin-top:20px"><a href="assets/freecad-example.FCStd" download>Download FreeCAD output</a></p></section>
<section class="band"><h2>QCAD: hatch a material region</h2><p>Create a native ANSI31 hatch inside a closed contour, excluding the rectangular hole. Put the hatch and outline on separate layers.</p><div class="two"><figure><a href="assets/qcad-boundaries.png"><img src="assets/qcad-boundaries.png" alt="Input synthetic outer closed rectangular boundary and internal hole boundary" width="1200" height="800"></a><figcaption><span class="figure-title">Input</span>Closed boundaries from the structured JSON definition; diagram rendered from the input coordinates.</figcaption></figure><figure><a href="assets/qcad-hatch.png"><img src="assets/qcad-hatch.png" alt="Output native QCAD hatch excludes the internal hole" width="1200" height="800"></a><figcaption><span class="figure-title">Output</span>Native HATCH entity. Two loops, pattern, area and layer verified after DXF reopening.</figcaption></figure></div><p style="margin-top:20px"><a href="assets/qcad-boundaries.json" download>Download input JSON</a> &nbsp; <a href="assets/qcad-hatch.dxf" download>Download DXF output</a></p></section>
<section class="band"><h2>From these operations to drawing conversion</h2><p>The agent builds a larger drawing from validated components and checks the result. Experiments have produced editable drafts from degraded scans. Those customer drawings and derived images are not part of the public release.</p><p><a href="experiments.html">Experiment summary</a></p></section>''')
    arrow = '<span class="route-arrow" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 12h17M13 5l7 7-7 7"/></svg></span>'
    page("architecture.html", "Architecture", '''<section class="intro"><div class="eyebrow">From scan to editable objects</div><h1>Architecture</h1><p class="lead">A Python runner rebuilds scanned drawings as editable 2D CAD, connecting visual interpretation, native construction and comparison with the source.</p><p>The model decides what the drawing means. FreeCAD or QCAD creates the objects. The runner decides whether to request another candidate or finish the job. This separation makes an interpretation error correctable without allowing the model to execute arbitrary code.</p></section>
<section class="band"><h2>The reconstruction loop</h2><p>The diagram shows one drawing job in the full-sheet campaigns. Reading the source and planning happen once. Generation, construction and evaluation can repeat up to four times.</p>
<div class="architecture-map" aria-label="Reconstruction flow with feedback and terminal outcomes"><p><strong>Python runner / local job control.</strong> The runner dispatches the steps below, records each attempt and enforces the stop conditions. Model requests send the relevant images and JSON to the configured inference endpoint; CAD processes and native files remain on the workstation.</p><div class="architecture-route">
<div class="architecture-node"><span class="place">1 / LOCAL PREPARATION</span><h3>PDF or image</h3><p>Render the pages and select the drawing area. Keep the source hash, pixel size and transform so every candidate uses the same reference.</p></div>''' + arrow + '''
<div class="architecture-node"><span class="place">2 / REMOTE MODEL</span><h3>Interpret and plan</h3><p>Identify views, bodies, fittings, axes and sections. Return a component plan and uncertain readings, not drawing commands.</p></div>''' + arrow + '''
<div class="architecture-node"><span class="place">3 / REMOTE MODEL</span><h3>Generate candidate</h3><p>Use the scan and plan to describe components, curves and hatch regions as structured JSON. After an evaluation, the drafter either edits a saved candidate with component operations or regenerates the full model.</p></div></div>
<div class="route-down" aria-hidden="true"><svg class="desktop-return" viewBox="0 0 1000 44" preserveAspectRatio="none"><path vector-effect="non-scaling-stroke" d="M850 0v20H150v22m-7-7 7 7 7-7"/></svg><svg class="mobile-return" viewBox="0 0 24 24"><path d="M12 3v17M5 13l7 7 7-7"/></svg></div>
<div class="architecture-route">
<div class="architecture-node"><span class="place">4 / LOCAL VALIDATION</span><h3>Validate and compile</h3><p>Check IDs, coordinate limits, shape counts and hatch boundaries. Convert valid component data into the selected backend's native entity description.</p></div>''' + arrow + '''
<div class="architecture-node"><span class="place">5 / LOCAL CAD PROCESS</span><h3>Build, reopen, render</h3><p>Create native objects in FreeCAD or QCAD, or apply component edits to a copy of the chosen candidate's native file. Save and reopen the document, check the stored geometry, then render it as the evaluator's input.</p></div>''' + arrow + '''
<div class="architecture-node"><span class="place">6 / REMOTE EVALUATOR</span><h3>Compare with source</h3><p>The evaluator receives the scan and CAD rendering, not the generator's reasoning. It returns an acceptance decision, score and defects located by view or component.</p></div></div>
<div class="feedback-route"><p><strong>Build or validation error: 4 or 5 returns to 3.</strong> Send the actual error to the generator. Skip visual evaluation because no valid new CAD candidate exists.</p></div>
<div class="feedback-route"><p><strong>Visual rejection: 6 returns to 3.</strong> The drafter receives the candidate history and defect reports, then edits a saved candidate, keeping untouched components, or regenerates. Build or edit, then evaluate again; changing JSON alone does not complete a correction.</p></div>
<div class="outputs-route"><h3>Finish the job</h3><p><strong>Accepted:</strong> stop the loop and retain the CAD, rendering, native checks and evaluation. <strong>Four candidates exhausted:</strong> stop with a not-accepted result and retain the last valid CAD for review. <strong>Request error or deadline:</strong> record the failure and preserve completed artifacts; if no build succeeded, there is no CAD output.</p></div><svg class="feedback-arrows" aria-hidden="true"><path class="execution-return"/><path class="execution-return"/><path/></svg></div>
<script>(()=>{
    const map=document.querySelector('.architecture-map');
    const nodes=[...map.querySelectorAll('.architecture-node')];
    const paths=[...map.querySelectorAll('.feedback-arrows path')];
    const draw=()=>{
        const bounds=map.getBoundingClientRect();
        const target=nodes[2].getBoundingClientRect();
        const edge=target.right-bounds.left;
        [3,4,5].forEach((sourceIndex,index)=>{
            const source=nodes[sourceIndex].getBoundingClientRect();
            const startX=source.right-bounds.left;
            const startY=source.top-bounds.top+source.height*(index===0?.72:.5);
            const endY=target.top-bounds.top+target.height*(.35+index*.18);
            const rail=bounds.width-8-index*8;
            const mobile=innerWidth<=700;
            const route=index<2&&!mobile
                ?'M '+(source.left-bounds.left+source.width/2)+' '+(source.bottom-bounds.top)+' v 9 H '+rail+' V '+endY+' H '+edge
                :'M '+startX+' '+startY+' H '+rail+' V '+endY+' H '+edge;
            paths[index].setAttribute('d',route+' m 6 -5 -6 5 6 5');
        });
    };
    new ResizeObserver(draw).observe(map);
    requestAnimationFrame(draw);
})();</script></section>
<section class="band"><h2>Why each component exists</h2><dl class="architecture-roles">
<dt>Python runner</dt><dd><p>Owns job state, request order, attempt limits and process timeouts. It supplies the next request with the plan, previous model and feedback rather than relying on a persistent chat. It records checkpoints after analysis, model generation, native construction and evaluation.</p><a class="code-link" href="''' + REPOSITORY + '''/blob/main/scripts/quality_campaign.py">Runner: quality_campaign.py</a></dd>
<dt>Generator</dt><dd><p>Interprets damaged drawing conventions that a geometric tracer would miss: a chamfer is not a separate lobe, and a section hatch describes material rather than a set of diagonal edges. It proposes the geometric data; it does not operate the CAD application.</p></dd>
<dt>Validator and compiler</dt><dd><p>Turn a flexible model proposal into a restricted CAD input. Invalid points or open/self-intersecting hatch regions are rejected before they reach QCAD. The compiler maps raster coordinates into provisional drawing coordinates; readable dimensions still need a separate confirmation step.</p><a class="code-link" href="''' + REPOSITORY + '''/blob/main/scripts/qcad_model.py">QCAD schema, geometry validation and compilation</a></dd>
<dt>CAD executor</dt><dd><p>Creates editable geometry and checks what was actually stored. QCAD uses component blocks, layers, polylines and native hatches. FreeCAD uses component sketches, selected constraints and splines, directly or through MCP. MCP changes the execution connection, not the interpretation loop.</p><a class="code-link" href="''' + REPOSITORY + '''/blob/main/scripts/astra_cad_agent.py">Native build and saved-document checks</a></dd>
<dt>Evaluator</dt><dd><p>Checks a different question from the validator: does the result depict the same mechanical features? Valid CAD can still omit a view, invert material and voids, or give a union nut the wrong contour. A separate request reduces dependence on the generator's explanation, but using the same model family can still produce shared judgment errors.</p></dd>
<dt>Artifact directory</dt><dd><p>Retains each candidate's JSON, compiled entities, native document, image, geometry report and evaluation. A final result points to the last valid CAD. This lets an operator compare revisions and investigate a rejected or interrupted job without overwriting earlier evidence.</p></dd></dl></section>
<section class="band"><h2>A correction in drawing 05</h2><p>The assembly example took four candidates in the QCAD/Astra campaign. The first evaluation found that adjacent components used the same hatch direction and that the spacing was too coarse. Those defects were fed back with the previous model. Later checks identified missing interface details and a wrongly opened passage in the upper boss. Candidate four restored the terminating boundary and passed the internal evaluation.</p><p>This is why both kinds of checks are needed: the earlier DXFs already contained valid native hatches, but their material interpretation and mechanical details still needed correction.</p><p><a href="examples.html">View the final drawing and download its DXF</a></p></section>
<section class="band"><h2>When does the loop stop?</h2><p>The automatic evaluator must return acceptance and a score of at least 85/100. Otherwise the runner uses another candidate, up to four total, including the first. A deadline or unrecoverable request error can end the route earlier. Limits are enforced by the runner, not left to the model.</p><p>An accepted result is ready for technical review, not for manufacture. The operator checks ambiguous features and confirms physical dimensions. The site can show a visually selected draft even when the automatic evaluator rejected it; the recorded result remains unchanged.</p></section>
<section class="band"><h2>What is complete today?</h2><div class="table-scroll"><table><thead><tr><th>Part</th><th>Current implementation</th><th>Still needed</th></tr></thead><tbody>
<tr><td>Local reconstruction loop</td><td>Source preparation, analysis, JSON generation, native construction, rendering, evaluation and bounded retries have run end to end.</td><td>Better evaluation calibration. Retries can edit individual components of a saved candidate or regenerate. Matched tests on three drawings, two backends and two drafters found only small differences; editing remains the default because it preserved verified components and used fewer output tokens.</td></tr>
<tr><td>Failure handling</td><td>Separate run directories, progressive checkpoints, 120-second progress reports, deadlines and cleanup of owned processes.</td><td>Automatic continuation from an interrupted mid-route checkpoint. Saving a checkpoint is not the same as being able to resume it.</td></tr>
<tr><td>Engineering handoff</td><td>Native 2D geometry, preview and reports are retained for manual inspection. Dimension text, labels and title blocks are not reconstructed.</td><td>Confirmed physical dimensions, drawing annotations and a formal approval workflow. Current coordinates describe the scan, not certified part measurements.</td></tr>
<tr><td>Remote service</td><td>No hosted CAD worker or public upload/conversion application. The website documents local experiments.</td><td>Job submission, storage, queue, worker ownership, durable recovery and delivery controls before unattended hosting.</td></tr></tbody></table></div><p>The local loop is implemented; a production conversion service is not. FreeCAD and QCAD remain experimental alternatives, and neither has been selected as the final backend.</p></section>''')
    page("experiments.html", "Experiments", '''<section class="intro"><div class="eyebrow">Local test results</div><h1>Experiments</h1><p class="lead">Tests cover CAD operations, reconstruction quality and processing time.</p></section>
<section class="band"><h2>Independent interpretations: three views, four methods</h2><p>Twelve routes began from original rasters with no intermediate geometry or evaluator feedback shared between methods. All saved native files passed persistence checks. One Robust candidate was corrected and reevaluated. Internal scores were too generous on some mechanically wrong nut contours.</p><div class="table-scroll"><table><thead><tr><th>Method</th><th>Calls</th><th>Total seconds</th><th>Input tokens</th><th>Cached input</th><th>Output tokens</th></tr></thead><tbody><tr><td>QCAD</td><td>9</td><td>1,069.59</td><td>21,834</td><td>0</td><td>46,695</td></tr><tr><td>FreeCAD direct</td><td>9</td><td>1,181.51</td><td>22,213</td><td>9,636</td><td>48,119</td></tr><tr><td>FreeCAD Neka</td><td>9</td><td>1,168.56</td><td>22,271</td><td>9,636</td><td>45,385</td></tr><tr><td>FreeCAD Robust</td><td>11</td><td>1,326.41</td><td>32,004</td><td>9,636</td><td>52,658</td></tr></tbody></table></div><p class="muted">Cached input is included in input; reasoning is included in output. Fixed order and cache effects confound rankings. Provider usage is not an invoice; dollar costs were not verified.</p></section>
<section class="band two"><div><h2>Neka and Robust MCP</h2><p>Both passed 3/3 trials on the same 140-entity model. Median time including startup, rendering and cleanup: <strong>Neka 23.33 s</strong>, <strong>Robust 30.39 s</strong>.</p><p class="muted">This compares execution, not model interpretation. Six trials are too few to establish reliability.</p></div><div><h2>Full-sheet reconstruction</h2><div class="table-scroll"><table><thead><tr><th>Campaign</th><th>Astra accepted</th><th>Sol accepted</th></tr></thead><tbody><tr><td>FreeCAD Neka</td><td>4/10</td><td>5/10</td></tr><tr><td>Native QCAD</td><td>4/10</td><td>3/10</td></tr></tbody></table></div><p class="muted">Accepted by the common Astra evaluator, not by a human reviewer. Campaign conditions differed, so these are not backend accuracy rankings.</p></div></section>
<section class="band"><h2>Where the QCAD campaign spent its time</h2><p>Twenty whole-sheet routes took 9 h 43 m 34 s wall time. CAD accounted for about 6 m 31 s; the model/correction workflow was the bottleneck.</p><div class="bars" aria-label="Recorded durations by phase"><div class="bar-row"><span>Analysis / 20 calls</span><div class="track"><div class="fill" style="width:18.3%"></div></div><span>63 min</span></div><div class="bar-row"><span>Generation / 75 calls</span><div class="track"><div class="fill" style="width:100%"></div></div><span>346 min</span></div><div class="bar-row"><span>Evaluation / 64 calls</span><div class="track"><div class="fill" style="width:48.2%"></div></div><span>167 min</span></div><div class="bar-row"><span>Successful CAD builds</span><div class="track"><div class="fill" style="width:1.9%"></div></div><span>6.5 min</span></div></div><div class="notice">Client-observed request duration includes network, service, reasoning and possible suspension. Roughly 29 minutes of Modern Standby events overlapped the run; do not add them again or interpret all waiting as cloud compute time.</div></section>
''' + (matrix_band(matrix_manifest) if matrix_manifest else "") + '''
<section class="band"><h2>Next tests</h2><ul><li>Check the evaluator against known defects.</li><li>Repeat the backend, drafter and strategy matrix with several routes per cell and human review.</li><li>Compare reasoning settings with the PC kept awake.</li><li>Test checkpoint recovery before remote hosting.</li></ul><p><a href="''' + REPOSITORY + '''/blob/main/docs/public/experiments.md">Test details and prerequisites</a></p><p class="muted">Original drawings, derived images and raw responses remain private.</p></section>''')
    example_manifest = SITE / "assets/drawing-examples.json"
    if example_manifest.exists():
        cases = json.loads(example_manifest.read_text())
        page("index.html", "Overview", '''<section class="intro home"><div class="eyebrow">Scanned drawing to CAD</div><h1>Convert old engineering drawings into editable CAD</h1><p class="lead">The system reads a PDF or image and rebuilds its components in FreeCAD or QCAD. It checks the saved geometry, compares the output with the scan, and refines the drawing for review.</p></section>'''
             + drawing_pair("05", "A degraded assembly drawing, rebuilt in CAD", "Three views of an assembly, including a longitudinal section, internal passages, handle and union fittings. Cut material is represented by native hatches.")
             + '''<section class="band"><h2>How the conversion works</h2><ol><li>The model identifies views, components and drawing conventions.</li><li>Local CAD scripts construct editable objects from validated data.</li><li>The file is saved, reopened and checked. An evaluator reviews the rendering and requests corrections when needed.</li></ol>             <p>The example above was built with QCAD and Astra. Its saved DXF passed native geometry and hatch checks. Dimensions that cannot be read reliably remain unconfirmed.</p><p><a href="examples.html">More reconstructed drawings</a> &nbsp; <a href="architecture.html">Architecture</a></p></section>'''
                          + ('''<section class="band"><h2>Edit a draft instead of starting over</h2><p>After each evaluation the drafter can edit components of a saved candidate, keeping verified components unchanged, or regenerate the whole drawing. A matrix of 24 reconstructions compares both strategies with FreeCAD and QCAD and with two drafter models.</p><p><a href="matrix-viewer.html">Open the overlay viewer</a> &nbsp; <a href="experiments.html">Matrix results</a></p></section>''' if matrix_manifest else "")
                          + '''
             <section class="band two"><div><h2>Two CAD backends</h2><p>QCAD provides 2D blocks, layers, polylines and hatches. FreeCAD provides sketches and constraints, with a potential future 3D extension. Both remain in development.</p></div><div><h2>Use and adaptation</h2><p>Code and documentation are MIT-licensed. The same pipeline could be adapted to rough sketches by changing interpretation instructions and testing the required geometry.</p><p><a href="experiments.html">Measurements and test scope</a></p></div></section>''')
        content = '''<section class="intro"><div class="eyebrow">Reconstruction examples</div><h1>Input and output</h1><p class="lead">Scanned drawings rebuilt as editable CAD with Astra.</p><p>''' + ('''The first two come from the matrix experiment, where the drafter edited its own saved candidate; the overlay shows the result over the scan. The others show the latest saved QCAD version. ''' if matrix_manifest else '''Each comparison shows the source and latest saved Astra version. ''') + '''Download the native file to inspect its objects and layers. Physical dimensions still require confirmation.</p></section>''' + (matrix_examples(matrix_manifest) if matrix_manifest else "")
        for case in cases:
            content += drawing_pair(case["drawing"], case["title"], case["description"] + " QCAD / " + ("Astra" if case["generator"] == "astra" else "GPT-6.1 Sol") + ".")
        content += '''<section class="band"><h2>What is included</h2><p>Downloads contain native DXF or FreeCAD entities, not embedded scans. The ten supplied PDF and TIFF inputs are available in the <a href="''' + REPOSITORY + '''/tree/main/drawings">drawings folder</a>.</p><p>Selected inputs and outputs were cleared for publication by the user. This permission does not change ownership of the original drawings or license them under MIT.</p><p><a href="architecture.html">How the system is built</a> &nbsp; <a href="experiments.html">Test measurements</a></p></section>'''
        page("examples.html", "Examples", content)
        for name in ("architecture.html", "experiments.html"):
            path = SITE / name
            text = path.read_text().replace("Original drawings, derived images and raw responses remain private.",
                "Selected drawing examples are published with authorization. Other originals, raw responses and private configuration remain local.")
            path.write_text(text, encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    print(str(SITE))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the static public-safe documentation site.")
    parser.add_argument("--copy-local-synthetic-assets", action="store_true")
    parser.add_argument("--copy-authorized-drawing-examples", action="store_true")
    parser.add_argument("--copy-matrix-comparison", metavar="DIRECTORY", help="Local matrix_comparison.py output directory to publish.")
    args = parser.parse_args()
    build(args.copy_local_synthetic_assets, args.copy_authorized_drawing_examples, args.copy_matrix_comparison)