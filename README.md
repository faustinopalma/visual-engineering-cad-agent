# Visual Engineering CAD Agent

An experimental converter from drawing images and PDFs to editable CAD. A model reads the drawing; local FreeCAD or QCAD scripts create the file, reopen it for checks and render it for review.

**FreeCAD and QCAD both remain under development.** Local conversion and evaluation loops are implemented; dependable unattended conversion and remote jobs are not yet established. The [evolving plan](EVOLVING_CAD_AGENT_PLAN.md) records current capabilities and next decisions.

## Featured Results

Both drawings below were finished by the drafter **editing its own saved candidate** rather than redrawing it from scratch: it replaced a few components and kept the verified ones. Each was internally accepted, saved and reopened. The overlay draws the reconstruction over the original scan.

**Gear housing section: QCAD, Astra, two edits.** Native section hatches; internal score 91, judge adherence 87 and coverage 91.

<table><tr>
<td width="33%"><a href="site/assets/drawing-03-input.png"><img src="site/assets/drawing-03-input.png" alt="Original scan of drawing 03"></a><br>Original scan</td>
<td width="33%"><a href="site/assets/drawing-03-qcad-edit-output.png"><img src="site/assets/drawing-03-qcad-edit-output.png" alt="QCAD reconstruction of drawing 03"></a><br>Editable CAD (<a href="site/assets/drawing-03-qcad-edit.dxf">DXF</a>)</td>
<td width="33%"><a href="site/assets/drawing-03-qcad-edit-overlay.png"><img src="site/assets/drawing-03-qcad-edit-overlay.png" alt="Reconstruction over the scan of drawing 03"></a><br>Overlay on the scan</td>
</tr></table>

**Motor and screw jack, two views: FreeCAD, Astra, one edit.** 6 components replaced and 14 preserved; no hatching, because FreeCAD has no hatch entity. Internal score 88, judge adherence 90 and coverage 89.

<table><tr>
<td width="33%"><a href="site/assets/drawing-06-input.png"><img src="site/assets/drawing-06-input.png" alt="Original scan of drawing 06"></a><br>Original scan</td>
<td width="33%"><a href="site/assets/drawing-06-freecad-edit-output.png"><img src="site/assets/drawing-06-freecad-edit-output.png" alt="FreeCAD reconstruction of drawing 06"></a><br>Editable CAD (<a href="site/assets/drawing-06-freecad-edit.FCStd">FCStd</a>)</td>
<td width="33%"><a href="site/assets/drawing-06-freecad-edit-overlay.png"><img src="site/assets/drawing-06-freecad-edit-overlay.png" alt="Reconstruction over the scan of drawing 06"></a><br>Overlay on the scan</td>
</tr></table>

These come from a 24-output matrix (3 drawings × FreeCAD/QCAD × Astra/Sol × edit-capable/from scratch). The [overlay viewer](https://faustinopalma.github.io/visual-engineering-cad-agent/matrix-viewer.html) lets you toggle the original and every version per drawing at full page. Scores come from the automatic evaluator and a blind overlay judge, not from human dimensional approval.

## Architecture

```text
Original image or PDF
  -> source-preserving preparation
  -> interpretation and structured component proposal
  -> deterministic validation and native CAD construction
  -> saved-file reopening, measurements and rendering
  -> separate visual evaluation
  -> drafter decision: edit a saved candidate or regenerate
  -> rebuilt or natively edited, reopened and reevaluated
  -> editable draft, evidence and human review
```

The model returns structured data, not executable code. Geometry checks verify the saved file. Visual evaluation checks the interpretation and reports defects. After each evaluation the drafter decides how to produce the next candidate: edit a previously built candidate with component-level operations (replace, append, add, remove) or regenerate the complete model. An edit copies the chosen candidate's native file; only named components change, and untouched components are compared after reopening. Earlier candidates are never modified. The evaluator is not told how a candidate was produced. Outputs still require technical review; unreadable dimensions remain unconfirmed.

## Evolution

| Stage | Purpose | Current position |
|---|---|---|
| Supervised laboratory | Validate native operations, parametric edits and interpretation hypotheses | Implemented; continues to test new capabilities |
| Independent local agent | Convert and correct without an active IDE assistant | Working pilot with progressive state and bounded execution |
| Remote job worker | Accept uploads, queue conversions and publish verified results | Planned; needs durable recovery and unattended CAD validation |

The remote design preserves the same boundaries: storage holds originals and revisions, a registry tracks jobs, and a queue dispatches work to an isolated CAD worker. The model service supplies inference, not CAD execution. Start sequentially and add concurrency only after isolation, ownership and recovery are demonstrated.

## CAD Backends

**FreeCAD** supports constraints and parametric edits. It runs directly or through MCP. Current scan drafts are not fully constrained; 3D reconstruction has not been tested.

**QCAD** supports native 2D blocks, polylines, layers and hatches. The executor checks closed hatch regions and internal holes. Curved clipping boundaries may use polygon approximations.

Both remain active candidates. Selection will depend on quality, editability, reliability and licensing.

## Feasibility Examples

Open the site's [input/output examples](https://faustinopalma.github.io/visual-engineering-cad-agent/examples.html) for actual drawing reconstructions and downloadable native files. The home page shows the degraded assembly drawing and its reconstructed three-view CAD output.

- [Gear housing section](site/assets/drawing-03-qcad-edit-output.png) and [motor and screw jack](site/assets/drawing-06-freecad-edit-output.png), shown above, were finished by drafter edits.
- [Mechanical assembly reconstruction](site/assets/drawing-05-output.png) includes three views, a section with native hatches, internal passages and fittings.
- [Section and plan reconstruction](site/assets/drawing-01-output.png) includes a housing, passages, concentric details and mounting holes.
- [Turned component reconstruction](site/assets/drawing-07-output.png) includes a stepped profile and knurled band.
- [Experiment findings](docs/public/experiments.md) explain independent generation, matched bridge execution and evaluator limitations.

The [documentation site](https://faustinopalma.github.io/visual-engineering-cad-agent/) presents these selected examples, architecture and measurements. Supplied inputs are in [drawings](drawings). Native checks and internal acceptance establish a reviewable draft, not dimensional certification.

## Reusable Concepts and Formats

The same pipeline could be adapted to rough sketches. Start by changing the prompt and evaluation rules; new geometry or symbols may also require schema changes and tests.

Outputs include FreeCAD files, DXF, JSON, PNG and PDF. Parametric relationships may be lost on export. DWG and 3D formats have not been validated.

Project-authored code and documentation are available under the [MIT license](LICENSE), enabling reuse, modification and distribution, including commercial use, subject to its terms. Third-party CAD applications and MCP components retain their own licenses. The installed QCAD Professional edition and hosted use require separate review. Input drawings and generated derivatives are not automatically MIT-licensed; redistribution depends on ownership, confidentiality and source rights.

## Local Verification

With Python and the CAD prerequisites configured, start with diagnostics and synthetic checks:

```powershell
python .\scripts\cad_agent.py doctor --check-qcad
python .\scripts\cad_agent.py smoke --gui --timeout 60
python -m unittest discover -s tests -p "test_*.py" -v
python .\scripts\incremental_edit.py smoke work\edit-smoke-qcad --method qcad
```

The edit smoke builds a synthetic candidate and applies two chained native edits (`qcad`, `qcad-native`, `freecad-direct`, `freecad-neka` or `freecad-robust`); the output directory must not exist. Set `CAD_AGENT_NATIVE_TESTS=1` to include a QCAD-backed worker-loop test.

The campaign worker accepts `revision_mode` (`drafter_choice` by default, or `full_regeneration` for the previous loop) and `max_attempts` (1-4) in its configuration. `--seed-route DIR` copies a finished route's analysis, receipts and validated CAD into a new directory and continues from them without changing the source, so different drafters or revision modes can start from identical candidates:

```powershell
python .\scripts\quality_campaign.py worker <case>\freecad-neka --method freecad-neka --config <config.json> --seed-route <finished-route>
```

The worker expects the source view at `<case>\source\view.png` and `page.png`.

`scripts\mode_comparison.py` runs a paired comparison. For each finished, unaccepted seed route it runs a `drafter_choice` arm and a `full_regeneration` arm from identical seeded copies, with the seed's configuration and the same `max_attempts`. Arms run one at a time and alternate order between seeds. Each validated output is then measured as follows:

- **Overlay:** the reopened native geometry (FreeCAD `Document.xml` sketches, or QCAD readback) is drawn in red over the source view, using the pipeline's own pixel transform with no fitted alignment.
- **Deterministic ink metrics:**
  - ink precision is the share of CAD line pixels within 3 px of source ink;
  - ink recall is the share of source ink near CAD lines.
- **Overlay judge:** a stateless model call scores adherence and coverage. It sees only the source and the overlay, without arm, scores or history.
- **Report:** `report.md` and `report.html` tabulate the start candidate and each arm's best new candidate, with token usage and images.

This is relative evidence, not metrology or human approval.

```powershell
python .\scripts\mode_comparison.py all work\mode-comparison-<id> --seed-route <finished-route> [--seed-route <another>] --max-attempts 2
```

To rerun one arm after a fix without discarding the original arm, add an extra arm with its own code state and note, then rerun:

```powershell
python .\scripts\mode_comparison.py add-arm work\mode-comparison-<id> --label <drawing-backend> --mode drafter_choice --name drafter_choice-rerun --note "<reason>"
python .\scripts\mode_comparison.py all work\mode-comparison-<id>
```

To measure how much the overlay judge varies, run it again on unchanged outputs. The report then adds a repeatability table:

```powershell
python .\scripts\mode_comparison.py judge-repeat work\mode-comparison-<id> --row <row-id> --count 2
python .\scripts\mode_comparison.py report work\mode-comparison-<id>
```

To compare one drafter model with another from the same seed, add arms that take only the drafter deployment and model version from another configuration. The evaluator, limits and attempt budget stay those of the template arm:

```powershell
python .\scripts\mode_comparison.py add-arm work\mode-comparison-<id> --label <drawing-backend> --mode full_regeneration --name sol-full_regeneration --drafter-config <sol-route>\config.json --note "<reason>"
```

`viewer` (also run by `all`) writes `viewer.html` beside the report. It is a full-window page showing the original view with one toggleable vector layer per route output. Each layer is the route's best new candidate, read back from the saved native document. The page supports zoom, pan, isolating a single layer and an adjustable original opacity:

```powershell
python .\scripts\mode_comparison.py viewer work\mode-comparison-<id>
```

A first comparison covered three drawings with one route per arm. The drafter chose edits on two of them. It found no consistent quality difference between the modes: gaps between arms were within the judge's repeat variation. Results and caveats are in the [experiment guide](docs/public/experiments.md#matched-comparison-edit-versus-regeneration).

`scripts\matrix_comparison.py` crosses drawings, CAD backends (FreeCAD through the Neka MCP, and native QCAD), drafter models and the two revision strategies. For each drawing, backend and model it works as follows:

- One base route starts from the raw source and runs analysis, a first generation and evaluation (`--base-attempts`, default 1).
- Both strategy arms copy that base and add the same attempts (`--arm-attempts`, default 2).
- Each arm's final output is the best evaluated candidate of the whole route. Route costs include the shared base.

The evaluator and overlay judge use one deployment for every route. FreeCAD has no hatch entity, so its drafter is told not to draw hatching, and its evaluator and the judge are told not to penalize the omission. This rule is enforced through prompts only.

```powershell
python .\scripts\matrix_comparison.py plan work\matrix-<id> --source <case>\source [--source <another>] --model astra=<astra-config.json> --model sol=<sol-config.json>
python .\scripts\matrix_comparison.py all work\matrix-<id>
```

`all` runs pending routes sequentially, then overlays, judge, report and viewer. The viewer has one page per drawing:

- one colored layer per backend, model and strategy;
- dashed shared-base layers, off by default;
- tag filters to isolate a backend, model or strategy.

When a route fails on the network or service (connection reset, read timeout, HTTP 5xx), `retry-failed` preserves it and any arm seeded from it as `*.transport-failed-N`, records the event in `retries.json`, and lets `all` rerun it once.

Model requests are streamed and use TCP keepalive. Earlier non-streaming requests that took more than about five minutes were often dropped.

The first matrix covered drawings 06, 03 and 10: 24 outputs, one route per cell.
- **Strategy:** overall a tie, 5 of 12 accepted each. With the Astra drafter, edit-capable arms were accepted 4 of 6 times against 3 of 6, and scored 86.0 against 83.8 on average. Edits also used about 12% fewer output tokens.
- **Drafter:** Astra did better than Sol on every aggregate.
- **Backend:** FreeCAD was accepted more often than QCAD, but QCAD is also judged on hatching, which FreeCAD omits.

`drafter_choice` therefore stays the default revision mode. With one route per cell these are indications, not rankings. Results, deviations and caveats are in the [experiment guide](docs/public/experiments.md#matrix-backend-drafter-model-and-strategy).

`build_public_site.py --copy-matrix-comparison work\matrix-<id>` publishes a matrix to the site. It copies:
- the viewer, with relative image paths and public model names;
- the inputs;
- the featured edit-capable outputs: render, overlay and native file;
- an aggregate manifest.

It refuses to publish if local paths remain or if a featured output was not an accepted, reopened edit.

See the [public experiment guide](docs/public/experiments.md) for prerequisites, configuration and scope. Model experiments require authorized inference configuration and can incur charges. Originals and prior revisions are preserved; CAD runs use isolated profiles, progress receipts and deadlines. Automatic mid-route crash recovery remains incomplete.

## Next Milestone

Improve the evaluator by calibrating it against known defects. Repeat the backend, drafter and strategy matrix with several routes per cell, more drawings and human review. Implement checkpoint recovery. Model requests dominate processing time; CAD execution is a small part of the measured total.

This public release contains code, documentation, supplied drawings authorized for publication, selected input/output examples and aggregate metrics. The separate private-originals folder, configurations and raw run artifacts remain local. Remote CAD hosting remains a roadmap, not a deployed service.