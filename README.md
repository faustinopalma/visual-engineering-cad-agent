# Visual Engineering CAD Agent

An experimental converter from drawing images and PDFs to editable CAD. A model reads the drawing; local FreeCAD or QCAD scripts create the file, reopen it for checks and render it for review.

**FreeCAD and QCAD both remain under development.** Local conversion and evaluation loops are implemented; dependable unattended conversion and remote jobs are not yet established. The [evolving plan](EVOLVING_CAD_AGENT_PLAN.md) records current capabilities and next decisions.

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

Open the site's [input/output examples](https://faustinopalma.github.io/visual-engineering-cad-agent/examples.html) for actual drawing reconstructions and downloadable DXF files. The home page shows the degraded assembly drawing and its reconstructed three-view CAD output.

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

See the [public experiment guide](docs/public/experiments.md) for prerequisites, configuration and scope. Model experiments require authorized inference configuration and can incur charges. Originals and prior revisions are preserved; CAD runs use isolated profiles, progress receipts and deadlines. Automatic mid-route crash recovery remains incomplete.

## Next Milestone

Improve the evaluator, measure on matched seeds whether drafter-selected edits outperform full regeneration, and implement checkpoint recovery. Model requests dominate processing time; CAD execution is a small part of the measured total.

This public release contains code, documentation, supplied drawings authorized for publication, selected input/output examples and aggregate metrics. The separate private-originals folder, configurations and raw run artifacts remain local. Remote CAD hosting remains a roadmap, not a deployed service.