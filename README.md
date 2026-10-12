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
  -> bounded corrections, rebuilt and reevaluated
  -> editable draft, evidence and human review
```

The model returns structured data, not executable code. Geometry checks verify the saved file. Visual evaluation checks the interpretation and requests corrections. Outputs still require technical review; unreadable dimensions remain unconfirmed.

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

Open the site's [input/output examples](https://faustinopalma.github.io/visual-engineering-cad-agent/examples.html) for side-by-side views and downloadable synthetic CAD files.

- [Synthetic parametric construction](site/assets/freecad-synthetic.png) demonstrates solver-driven FreeCAD geometry and saved-file checks, not scan recognition.
- [Native hatch with an internal hole](site/assets/qcad-hatch.png) demonstrates a QCAD hatch whose pattern, area, loops and dedicated layer survive DXF reopening.
- [Experiment findings](docs/public/experiments.md) explain independent generation, matched bridge execution and evaluator limitations.

The [documentation site](https://faustinopalma.github.io/visual-engineering-cad-agent/) presents the architecture and aggregate findings. Private scan-derived comparisons are deliberately excluded from this public release. Separate campaigns and internal evaluator scores are not controlled rankings of backend quality.

## Reusable Concepts and Formats

The same pipeline could be adapted to rough sketches. Start by changing the prompt and evaluation rules; new geometry or symbols may also require schema changes and tests.

Outputs include FreeCAD files, DXF, JSON, PNG and PDF. Parametric relationships may be lost on export. DWG and 3D formats have not been validated.

Project-authored code and documentation are available under the [MIT license](LICENSE), enabling reuse, modification and distribution, including commercial use, subject to its terms. Third-party CAD applications and MCP components retain their own licenses. The installed QCAD Professional edition and hosted use require separate review. Input drawings and generated derivatives are not automatically MIT-licensed; redistribution depends on ownership, confidentiality and source rights.

## Local Verification

With Python and the CAD prerequisites configured, start with diagnostics and synthetic checks:

```powershell
python .\scripts\cad_agent.py doctor --check-qcad
python .\scripts\cad_agent.py smoke --gui --timeout 60
python -m unittest discover -s tests -p test_public_contract.py -v
```

See the [public experiment guide](docs/public/experiments.md) for prerequisites, configuration and scope. Model experiments require authorized inference configuration and can incur charges. Originals and prior revisions are preserved; CAD runs use isolated profiles, progress receipts and deadlines. Automatic mid-route crash recovery remains incomplete.

## Next Milestone

Improve the evaluator, correct individual components and implement checkpoint recovery. Model requests dominate processing time; CAD execution is a small part of the measured total.

This public release contains reusable code, documentation, synthetic visuals and aggregate metrics. Original drawings, private configuration, scan-derived images and raw run artifacts remain local. Review confidentiality and source rights before adding further examples. Remote CAD hosting remains a roadmap, not a deployed service.