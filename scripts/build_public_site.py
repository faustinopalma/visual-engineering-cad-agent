import argparse
from html import escape
from pathlib import Path
import shutil
import json
import hashlib

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
.two{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.two>*{min-width:0}.table-scroll{max-width:100%;min-width:0}.comparison img{height:400px}.intro.home{padding-bottom:12px}.home+.band{padding-top:24px}
@media(max-width:700px){.top{padding:18px}.brand{font-size:16px}nav{gap:14px}main{padding:30px 18px 50px}h1{font-size:30px}.lead{font-size:17px}.two{grid-template-columns:1fr;gap:28px}.flow{grid-template-columns:1fr 1fr}figure img{height:240px}.bar-row{grid-template-columns:110px 1fr 48px;gap:8px}.band{padding:28px 0}}
@media(prefers-reduced-motion:no-preference){main{animation:appear .3s ease-out}@keyframes appear{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}}
@media(max-width:700px){.comparison img{height:280px}}
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


def drawing_pair(drawing, title, description):
    name = "assets/drawing-" + drawing
    revision = hashlib.sha256((SITE / (name + "-output.dxf")).read_bytes()).hexdigest()[:12]
    output = name + "-output.png?v=" + revision
    download = name + "-output.dxf?v=" + revision
    return '<section class="band"><h2>' + escape(title) + '</h2><p>' + escape(description) + '</p><div class="two comparison"><figure><a href="' + name + '-input.png"><img src="' + name + '-input.png" alt="Original degraded scan for drawing ' + drawing + '"></a><figcaption><span class="figure-title">Input: original scan</span></figcaption></figure><figure><a href="' + output + '"><img src="' + output + '" alt="Actual native QCAD reconstruction of drawing ' + drawing + '"></a><figcaption><span class="figure-title">Output: editable CAD</span>Generated geometry, rendered from the saved DXF.</figcaption></figure></div><p style="margin-top:16px"><a href="' + download + '" download>Download DXF</a></p></section>'


def build(copy_assets=False, reviewed_drawings=False):
    SITE.mkdir(exist_ok=True)
    (SITE / "assets").mkdir(exist_ok=True)
    if reviewed_drawings:
        copy_reviewed_drawings()
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
    page("architecture.html", "Architecture", '''<section class="intro"><div class="eyebrow">Pipeline and roadmap</div><h1>Architecture</h1><p class="lead">Python coordinates model requests, local CAD scripts and validation.</p></section>
<section class="band"><h2>The local loop</h2><div class="flow"><div class="step"><span>01 / SOURCE</span><h3>Preserve evidence</h3><p>Keep originals, hashes, pages and raster transforms. Never invent unreadable measurements.</p></div><div class="step"><span>02 / PROPOSAL</span><h3>Describe components</h3><p>Stateless inference proposes typed data, not executable code. Geometry validators reject invalid input.</p></div><div class="step"><span>03 / CAD</span><h3>Construct and reopen</h3><p>Isolated scripts build native objects, save, close, reopen and measure the actual document.</p></div><div class="step"><span>04 / REVIEW</span><h3>Evaluate and revise</h3><p>Inspect native rendering. Correct only within finite attempts; rejected work remains a labeled draft.</p></div></div></section>
<section class="band"><h2>Three evolution stages</h2><div class="table-scroll"><table><thead><tr><th>Stage</th><th>Implemented</th><th>Next requirement</th></tr></thead><tbody><tr><td>Supervised laboratory</td><td>Native scripts, synthetic tests and interpretation experiments</td><td>Validate every new operation and expose conceptual failures</td></tr><tr><td>Local independent agent</td><td>Model proposal, deterministic CAD, independent evaluator, progressive checkpoints and deadlines</td><td>Calibrated quality gates, component revisions and mid-route recovery</td></tr><tr><td>Remote conversion worker</td><td>Architecture only; no hosted CAD service</td><td>Upload/storage, durable registry, queue ownership, runtime identity and restart validation</td></tr></tbody></table></div></section>
<section class="band two"><div><h2>CAD integration</h2><p>FreeCAD runs directly or through MCP. QCAD runs ECMAScript scripts. Both read validated component data; model-generated code is not executed.</p><p>Current scan sketches are not fully constrained. Curved hatch clipping may use polygon approximations.</p></div><div><h2>Execution controls</h2><p>CAD runs sequentially with separate profiles. The runner records progress every 120 seconds, saves checkpoints and applies timeouts. Credentials stay in memory.</p><p>Automatic mid-route restart is not implemented. The planned remote worker must handle queue redelivery, job ownership and recovery without a remote desktop session.</p></div></section>
<section class="band"><h2>Local checks</h2><pre><code>python scripts/cad_agent.py doctor --check-qcad
python scripts/cad_agent.py smoke --gui --timeout 60
python -m unittest discover -s tests -p test_public_contract.py -v</code></pre><p class="muted">Windows-oriented prototype; install dependencies, adapt local CAD paths and configure your own authorized model deployment. Model experiments incur charges. Public tests need no customer drawings.</p></section>''')
    page("experiments.html", "Experiments", '''<section class="intro"><div class="eyebrow">Local test results</div><h1>Experiments</h1><p class="lead">Tests cover CAD operations, reconstruction quality and processing time.</p></section>
<section class="band"><h2>Independent interpretations: three views, four methods</h2><p>Twelve routes began from original rasters with no intermediate geometry or evaluator feedback shared between methods. All saved native files passed persistence checks. One Robust candidate was corrected and reevaluated. Internal scores were too generous on some mechanically wrong nut contours.</p><div class="table-scroll"><table><thead><tr><th>Method</th><th>Calls</th><th>Total seconds</th><th>Input tokens</th><th>Cached input</th><th>Output tokens</th></tr></thead><tbody><tr><td>QCAD</td><td>9</td><td>1,069.59</td><td>21,834</td><td>0</td><td>46,695</td></tr><tr><td>FreeCAD direct</td><td>9</td><td>1,181.51</td><td>22,213</td><td>9,636</td><td>48,119</td></tr><tr><td>FreeCAD Neka</td><td>9</td><td>1,168.56</td><td>22,271</td><td>9,636</td><td>45,385</td></tr><tr><td>FreeCAD Robust</td><td>11</td><td>1,326.41</td><td>32,004</td><td>9,636</td><td>52,658</td></tr></tbody></table></div><p class="muted">Cached input is included in input; reasoning is included in output. Fixed order and cache effects confound rankings. Provider usage is not an invoice; dollar costs were not verified.</p></section>
<section class="band two"><div><h2>Neka and Robust MCP</h2><p>Both passed 3/3 trials on the same 140-entity model. Median time including startup, rendering and cleanup: <strong>Neka 23.33 s</strong>, <strong>Robust 30.39 s</strong>.</p><p class="muted">This compares execution, not model interpretation. Six trials are too few to establish reliability.</p></div><div><h2>Full-sheet reconstruction</h2><div class="table-scroll"><table><thead><tr><th>Campaign</th><th>Astra accepted</th><th>Sol accepted</th></tr></thead><tbody><tr><td>FreeCAD Neka</td><td>4/10</td><td>5/10</td></tr><tr><td>Native QCAD</td><td>4/10</td><td>3/10</td></tr></tbody></table></div><p class="muted">Accepted by the common Astra evaluator, not by a human reviewer. Campaign conditions differed, so these are not backend accuracy rankings.</p></div></section>
<section class="band"><h2>Where the QCAD campaign spent its time</h2><p>Twenty whole-sheet routes took 9 h 43 m 34 s wall time. CAD accounted for about 6 m 31 s; the model/correction workflow was the bottleneck.</p><div class="bars" aria-label="Recorded durations by phase"><div class="bar-row"><span>Analysis / 20 calls</span><div class="track"><div class="fill" style="width:18.3%"></div></div><span>63 min</span></div><div class="bar-row"><span>Generation / 75 calls</span><div class="track"><div class="fill" style="width:100%"></div></div><span>346 min</span></div><div class="bar-row"><span>Evaluation / 64 calls</span><div class="track"><div class="fill" style="width:48.2%"></div></div><span>167 min</span></div><div class="bar-row"><span>Successful CAD builds</span><div class="track"><div class="fill" style="width:1.9%"></div></div><span>6.5 min</span></div></div><div class="notice">Client-observed request duration includes network, service, reasoning and possible suspension. Roughly 29 minutes of Modern Standby events overlapped the run; do not add them again or interpret all waiting as cloud compute time.</div></section>
<section class="band"><h2>Next tests</h2><ul><li>Check the evaluator against known defects.</li><li>Correct individual components instead of regenerating whole sheets.</li><li>Compare reasoning settings with the PC kept awake.</li><li>Test checkpoint recovery before remote hosting.</li></ul><p><a href="''' + REPOSITORY + '''/blob/main/docs/public/experiments.md">Test details and prerequisites</a></p><p class="muted">Original drawings, derived images and raw responses remain private.</p></section>''')
    example_manifest = SITE / "assets/drawing-examples.json"
    if example_manifest.exists():
        cases = json.loads(example_manifest.read_text())
        page("index.html", "Overview", '''<section class="intro home"><div class="eyebrow">Scanned drawing to CAD</div><h1>Convert old engineering drawings into editable CAD</h1><p class="lead">The system reads a PDF or image and rebuilds its components in FreeCAD or QCAD. It checks the saved geometry, compares the output with the scan, and refines the drawing for review.</p></section>'''
             + drawing_pair("05", "A degraded assembly drawing, rebuilt in CAD", "Three views of an assembly, including a longitudinal section, internal passages, handle and union fittings. Cut material is represented by native hatches.")
             + '''<section class="band"><h2>How the conversion works</h2><ol><li>The model identifies views, components and drawing conventions.</li><li>Local CAD scripts construct editable objects from validated data.</li><li>The file is saved, reopened and checked. An evaluator reviews the rendering and requests corrections when needed.</li></ol><p>The example above was built with QCAD and Astra. Its saved DXF passed native geometry and hatch checks. Dimensions that cannot be read reliably remain unconfirmed.</p><p><a href="examples.html">More reconstructed drawings</a> &nbsp; <a href="architecture.html">Architecture</a></p></section>
<section class="band two"><div><h2>Two CAD backends</h2><p>QCAD provides 2D blocks, layers, polylines and hatches. FreeCAD provides sketches and constraints, with a potential future 3D extension. Both remain in development.</p></div><div><h2>Use and adaptation</h2><p>Code and documentation are MIT-licensed. The same pipeline could be adapted to rough sketches by changing interpretation instructions and testing the required geometry.</p><p><a href="experiments.html">Measurements and test scope</a></p></div></section>''')
        content = '''<section class="intro"><div class="eyebrow">Actual reconstruction experiments</div><h1>Input and output</h1><p class="lead">Selected drawing scans and the editable CAD produced by the agent.</p><p>All three examples use the latest saved Astra revision, selected for visual accuracy. These are actual experiment outputs, not manually redrawn replacements. Each passed native geometry and reopening checks; visual selection is separate from the automatic evaluator's verdict and dimensional approval.</p></section>'''
        for case in cases:
            content += drawing_pair(case["drawing"], case["title"], case["description"] + " QCAD / " + ("Astra" if case["generator"] == "astra" else "GPT-6.1 Sol") + ".")
        content += '''<section class="band"><h2>What is included</h2><p>Downloads contain native DXF entities, not embedded scans. The ten supplied PDF and TIFF inputs are available in the <a href="''' + REPOSITORY + '''/tree/main/drawings">drawings folder</a>.</p><p>Selected inputs and outputs were cleared for publication by the user. This permission does not change ownership of the original drawings or license them under MIT.</p><p><a href="architecture.html">How the system is built</a> &nbsp; <a href="experiments.html">Test measurements</a></p></section>'''
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
    args = parser.parse_args()
    build(args.copy_local_synthetic_assets, args.copy_authorized_drawing_examples)