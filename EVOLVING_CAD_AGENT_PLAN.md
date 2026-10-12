# Evolving CAD Agent Plan

Status: October 12, 2026. The public repository and documentation site are published. Local agent experiments run; reliable unattended conversion and remote CAD jobs remain in development. FreeCAD and QCAD are both active candidates.

## Direction

Transform imperfect visual engineering information into editable CAD with traceable interpretation and explicit uncertainty. Degraded legacy drawings are the initial test case. Rough sketches are a potential extension of the same architecture, with adapted prompts, evaluation criteria and, where needed, geometry contracts.

The goal is to reconstruct components and relationships, not every raster mark. Native geometric correctness, source fidelity and engineering approval are separate requirements. Unreadable dimensions must never become invented measurements.

## Current State

| Area | Demonstrated | Next requirement |
|---|---|---|
| Local CAD | Deterministic scripts, isolated profiles, native save/reopen checks | Packaged backend contract and unattended runtime validation |
| Agent loop | Structured generation, independent visual evaluation, bounded corrections | Calibrated evaluator and component-targeted revisions |
| FreeCAD | Parametric synthetic edits, component sketches, direct and MCP execution | Better section representation; separately validated 3D extension |
| QCAD | Blocks, native polylines, layers and hatches with internal voids | Curved clipping fidelity, associativity and hosting license review |
| Corpus | Independent selected-view and whole-sheet Astra/Sol campaigns | Representative quality acceptance and fair performance comparison |
| Operations | Progressive checkpoints, request receipts, deadlines, token renewal, minimized FreeCAD startup | Mid-route recovery and verified locked-session execution |
| Publication | Public GitHub repository and Pages site with synthetic examples and aggregate metrics | Separate rights approval before publishing private drawings or derived images |

Native execution is more mature than semantic reconstruction. Some valid CAD drafts are rejected by the evaluator; some earlier evaluations accepted known contour defects. Experiments establish capabilities and expose gaps, not production readiness.

## Backend Strategy

**Continue FreeCAD.** Relationships, solver-driven edits and a future parametric 3D path remain strong reasons to adopt it. Its open-source foundation is relevant to deployment and reuse. The current scan executor is not a fully constrained engineering model. Direct execution and Neka/Robust MCP are integration options; matched bridge tests reproduce the same geometry and do not demonstrate improved interpretation. Neka remains a provisional pilot choice.

**Continue QCAD.** Native 2D drafting operations preserve intent through layers, blocks, polylines and section hatches rather than copied strokes. Closed region topology and voids can be verified independently of the model. Correct material interpretation, curved boundaries and technical conventions still require review. The installed Professional edition and future server use have licensing considerations separate from the MIT project code.

Select a backend by deliverable quality, editability, required operations, operational reliability and cost. A better preview, a faster isolated run or a larger tool inventory is not sufficient alone. No 3D scan reconstruction has yet been validated.

## Evolution Stages

### 1. Supervised Local Laboratory

Verify build, inspect, render and export on known synthetic geometry before introducing ambiguous scans. Separate matched execution tests from independent interpretation comparisons. Preserve originals, revisions and failure evidence. This stage is implemented and remains the validation environment for new operations.

### 2. Independent Local Agent

Python orchestration runs without an active IDE assistant. Remote inference proposes structured data; trusted local code performs CAD operations. A separate evaluator compares the source with the actual native rendering and requests corrections. Every corrected result is reconstructed and reevaluated; human approval remains separate.

The pilot implements this loop. Priorities are component-level corrections, evaluator calibration, a versioned contract for views/relations/measurements, and recovery from the last verified checkpoint. Current checkpoints expose saved progress but do not implement arbitrary mid-route restart.

Record inference, CAD, retry and suspension effects separately. Use provider usage and verified prices for cost estimates. Experiments can be uncapped monetarily, but deadlines and finite correction attempts remain essential. More throughput quota does not eliminate single-request latency.

### 3. Remote Conversion Jobs

Move the tested workflow to an isolated worker rather than placing CAD execution inside the model service. The proposed architecture is authenticated upload, immutable object storage, a durable job registry, a queue and a CAD worker. Results include editable files, previews, validation, uncertainty and consumption receipts.

Begin with one active CAD job per worker. Validate queue redelivery, ownership, checkpoint recovery and output persistence across restarts. Use a runtime identity rather than an administrator's personal login. Verify CAD rendering without remote desktop, hosting suitability and licenses before deployment.

No remote CAD worker, upload service or durable queue is deployed. Shared model inference, including the explicitly authorized Sol deployment and capacity changes, is not a hosted conversion service. Further infrastructure requires explicit authorization.

## Acceptance Gates

1. **Execution:** bounded operations complete and owned processes are cleaned up.
2. **Geometry:** saved native files are reopened and measured; solver and hatch topology pass where applicable.
3. **Meaning:** components, views, connectivity and drafting conventions agree with available source evidence.
4. **Approval:** a person confirms interpretation and required dimensions before engineering use.

A model score cannot replace native verification or human approval. Uncertain or rejected drafts remain labeled for review; they are not silently promoted to engineering deliverables.

## Publication and Reuse

Project-authored code and documentation use the [MIT license](LICENSE). Third-party software retains its own licenses. Source drawings, customer material and generated artifacts require separate rights/confidentiality review; MIT does not grant rights that contributors do not own.

Before GitHub publication, curate reusable code, synthetic fixtures and cleared examples. Exclude credentials, private configurations and raw operational/customer artifacts unless explicitly reviewed. Git initialization, staging and publication still require user approval.

The [site](https://faustinopalma.github.io/visual-engineering-cad-agent/) contains overview, input/output examples, architecture and experiment results. Examples use synthetic geometry and include downloads. Private drawings and scan-derived comparisons remain local.

Start with the [README](README.md) and [public experiment findings](docs/public/experiments.md). Private run artifacts and supplied drawings remain outside the public repository. The user authorized public Git initialization, commits, push and GitHub Pages publication on October 12, 2026; further remote CAD infrastructure remains subject to separate approval.