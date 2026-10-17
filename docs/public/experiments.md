# What the Experiments Establish

These are local feasibility experiments, not a validated production converter. The user authorized publication of [the supplied drawing set](../../drawings) and [selected input/output cases](../../site/examples.html). The separate private-originals folder, private configuration and raw provider responses are not distributed.

## Native Operations Before Recognition

FreeCAD's synthetic rectangle/two-circle test demonstrates a real dimension change, solver relationships and saved-file reopening. QCAD's synthetic section demonstrates a native ANSI31 hatch with two loops: material outside an internal void. Its reopened area is 443.75 provisional drawing units squared, with a dedicated HATCH layer and a closed OUTLINE polyline. This is persistence evidence, not accuracy evidence for a scan.

## Editing Saved Candidates

After an evaluation, the drafter chooses `edit_existing` or `regenerate`. An edit targets one validated candidate with component operations: replace, append, add or remove. The executor copies that candidate's native file, applies only those operations and saves the result as a new attempt. It then reopens the file and compares every untouched component with the original. FreeCAD compares sketch label, constraint count and geometry. QCAD compares block geometry signatures. The base file's hash must not change. The evaluator receives only the source and the new render, as before. `full_regeneration` keeps the previous correction loop for comparison.

Synthetic chained edits passed for QCAD, native QCAD with a hatch, direct FreeCAD and FreeCAD Neka MCP. The chain was replace, append, add and remove, followed by a second edit of the result. A worker test uses scripted model responses with real QCAD execution. A scripted edit was also applied to a copy of a real Astra-generated FreeCAD Neka candidate: 20 components and 345 entities, built by the previous loop. It replaced one component and removed another. The edited file reopened with 330 entities. Its 18 untouched components were verified, and the source candidate's hash was unchanged. These checks validate the mechanism; they are not evidence that edits produce better reconstructions.

Two live single-attempt routes continued the same seeded whole-sheet drawing-06 route: FreeCAD Neka, best prior score 80/100, and two earlier 450-edge budget failures. Both used the Astra drafter and evaluator. In both routes the drafter chose `regenerate`, reasoning that the failing proposal touched most components.

| Route | Drafter decision | Outcome | Calls | Input tokens | Output tokens | Reasoning tokens | Seconds |
|---|---|---|---:|---:|---:|---:|---:|
| First live route | Regenerate | Failed validation: 451 of 450 edges | 1 | 24,293 | 15,604 | 8,286 | 294 |
| Second live route | Regenerate | Native build of 425 entities; evaluator score 87/100, internally accepted | 2 | 26,826 | 17,451 | 8,993 | 407 |

Before the second route, the candidate history also reported each model's measured budget use. This was the only change between the two routes. Two routes cannot attribute the difference to that change. Internal acceptance is not human approval.

## Matched Comparison: Edit Versus Regeneration

`scripts/mode_comparison.py` continued three finished, unaccepted whole-sheet routes twice each. The seeds were drawing 06 (FreeCAD Neka), drawing 03 (native QCAD) and drawing 10 (FreeCAD Neka).
- **`drafter_choice` arm:** the drafter may edit a saved candidate or regenerate.
- **`full_regeneration` arm:** the previous loop.

Both arms of a drawing started from identical seed copies, with the seed's configuration (Astra drafter and evaluator, high reasoning) and a limit of two new attempts. Arms ran one at a time and alternated order between drawings.

Each validated output was measured in three ways:
- **Internal evaluator** score, from the loop itself.
- **Overlay:** the reopened native geometry is drawn over the source view, using the pipeline's own transform with no fitted alignment.
  - **Ink precision:** CAD line pixels within 3 px of source ink.
  - **Ink recall:** source ink near CAD. Recall includes text, dimensions and the title block, so it is only comparable within one drawing.
- **Overlay judge:** a stateless Astra call that sees only the source and the overlay, without arm or scores.

| Drawing / backend | Arm | Drafter decisions | Valid new / attempts | Best internal score | Judge adherence / coverage | Ink precision / recall | Calls | Input / output tokens | Seconds |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 06 FreeCAD Neka | start (seed) | - | - | 80 | 88 / 80 | 81.2% / 40.5% | - | - | - |
| 06 FreeCAD Neka | drafter_choice | regenerate (failed 450-edge budget), regenerate | 1 / 2 | 80 | 89 / 88 | 79.9% / 43.1% | 3 | 51,465 / 30,961 | 621 |
| 06 FreeCAD Neka | full_regeneration | generate, generate (failed budget) | 1 / 2 | 82 | 87 / 84 | 81.4% / 41.5% | 3 | 29,774 / 32,286 | 581 |
| 03 native QCAD | start (seed) | - | - | 81 | 89 / 85 | 79.6% / 25.6% | - | - | - |
| 03 native QCAD | drafter_choice | edit (8 replaced, 1 added, 8 preserved), edit (rejected by a validator bug) | 1 / 2 | 78 | 89 / 93 | 78.8% / 26.8% | 3 | 62,610 / 19,507 | 364 |
| 03 native QCAD | drafter_choice rerun | edit (5 replaced, 1 added, 11 preserved), edit (1 replaced, 1 appended, 15 preserved) | 2 / 2 | 92, internally accepted | 92 / 94 | 79.1% / 27.3% | 4 | 53,234 / 24,499 | 560 |
| 03 native QCAD | full_regeneration | generate, generate | 2 / 2 | 82 | 91 / 94 | 78.4% / 26.8% | 4 | 35,408 / 35,199 | 624 |
| 10 FreeCAD Neka | start (seed) | - | - | 82 | 93 / 95 | 69.2% / 23.7% | - | - | - |
| 10 FreeCAD Neka | drafter_choice | edit (2 replaced, 1 added, 19 preserved), edit (1 replaced, 1 added, 21 preserved) | 2 / 2 | 80 | 88 / 86 | 72.4% / 23.4% | 4 | 49,719 / 24,119 | 713 |
| 10 FreeCAD Neka | full_regeneration | generate, generate | 2 / 2 | 88, internally accepted | 89 / 92 | 72.3% / 24.5% | 4 | 25,540 / 30,823 | 637 |

The table reports the arm's best new candidate by internal score. Tokens and seconds cover the drafter and internal evaluator only. The overlay judge used 23 further successful calls, 44,940 input and 76,830 output tokens, plus one HTTP 500 failure with unknown usage. Dollar costs were not verified.

**The validator bug.** In the original 03 `drafter_choice` arm, the second edit was rejected as "preserved component changed". Native diagnosis showed that the untouched hatch angle had drifted by one ulp across a second DXF round trip: DXF stores angles in degrees. The check now uses the same 1e-7 tolerance as the reopen check. A native regression test reproduces the drift and still detects a real change. The arm was rerun with the fix from the same seed, and the original arm is kept in the table.

**What the data shows:**
- **When the drafter edits.** It chose edits on drawings 03 and 10, where the base candidate was valid and the defects were local. It chose regeneration on 06, where it was repairing an over-budget proposal. Every completed edit passed native preservation checks: 8 to 21 untouched components were verified after reopening.
- **No consistent quality winner.**
  - Internal evaluator: the edit arm won on 03 (92 vs 82); regeneration won on 10 (88 vs 80). On 06 both arms in fact regenerated, and they still differed by 2 points, which shows the variation between runs.
  - Overlay judge: differences between arms were at most 3 points of adherence. Repeating the judge on four identical overlays varied by up to 3 points of adherence and 8 of coverage.
  - Ink metrics: arms differed by at most 1.5 points. On 10 the judge rated the starting candidate highest, while the internal evaluator ranked it below the accepted regeneration.
- **Cost profile.** The `drafter_choice` revision prompt always includes the saved model, so it used 1.5 to 2.0 times the input tokens of full regeneration. That includes 06, where the drafter then regenerated. Where it edited (03 and 10), it produced 22–45% fewer output tokens. Elapsed time was similar.

One route per arm and drawing cannot rank the modes. The judge belongs to the same model family as the drafter and evaluator, so their errors may be correlated. The overlay is not metrology, and no output has human approval. A useful next comparison needs several routes per arm, more drawings, and either human review or an evaluator calibrated against known defects.

## Three Views, Four Methods

Twelve independent interpretations used QCAD, direct FreeCAD, Neka MCP and Robust MCP. All constructed native files passed persistence checks. The internal evaluator accepted all final candidates, including a corrected second Robust candidate. Independent visual review nevertheless found incorrectly scalloped nut envelopes with high scores. The evaluator can be overconfident; these scores are not a reliable ranking of mechanical correctness.

| Method | Calls | Total seconds, three views | Input tokens | Cached input | Output tokens |
|---|---:|---:|---:|---:|---:|
| QCAD | 9 | 1,069.59 | 21,834 | 0 | 46,695 |
| FreeCAD direct | 9 | 1,181.51 | 22,213 | 9,636 | 48,119 |
| FreeCAD Neka | 9 | 1,168.56 | 22,271 | 9,636 | 45,385 |
| FreeCAD Robust | 11 | 1,326.41 | 32,004 | 9,636 | 52,658 |

Cached input is included in input; output includes reasoning. Fixed ordering and cache effects prevent a causal cost or latency ranking. Dollar costs were not verified.

## Comparing Bridges, Not Interpretation

Neka and Robust each passed three matched trials on the same 140-entity model and trusted executor. Medians including initialization, native construction, rendering and cleanup: Neka 23.33 seconds; Robust 30.39 seconds. Fresh profiles and alternating order were used, but six trials are not a reliability certification. Robust exposed 83 tools versus Neka's 17; individual specialized tools were not behavior-tested. Identical output is expected when both execute the same model.

## Whole-Sheet Difficulty

Two independent passes across ten originals requested every readable view, using a common Astra evaluator:

| Campaign | Astra internal acceptance | Sol internal acceptance |
|---|---:|---:|
| FreeCAD Neka | 4/10 | 5/10 |
| Native QCAD with hatch regions | 4/10 | 3/10 |

Terminal results include rejected drafts and failures. Different campaigns, prompts, representations and power conditions make this unsuitable as a head-to-head backend accuracy benchmark. Native hatches do not solve incorrect material interpretation.

The QCAD campaign took 9 h 43 m 34 s wall time. Recorded model activity was 1 h 03 m analysis, 5 h 46 m generation/correction and 2 h 47 m evaluation. Successful CAD builds took only 6 m 31 s. Modern Standby events overlapped the run by roughly 29 minutes, so client-observed request latency is not cloud compute time. The bottleneck is the reasoning/correction workflow, not primarily CAD execution.

## Reproduce Safely

Install [requirements](../../requirements.txt) in your own Python environment and configure locally installed FreeCAD/QCAD. The current runners are Windows-oriented and contain installation assumptions; adapt those paths before use. MCP execution additionally needs a separately installed compatible server, interpreter and addon. External MCP source is not vendored.

```powershell
python scripts/cad_agent.py doctor --check-qcad
python scripts/cad_agent.py smoke --gui --timeout 60
python -m unittest discover -s tests -p "test_*.py" -v
```

Copy the structure of [the configuration example](../../config/astra-example.json) to your local, ignored configuration and replace placeholders. Never store secrets in it. The authenticated CLI token stays in memory. The corpus runners currently expect ten explicitly named local files and are laboratory entrypoints, not general folder services. There is no distributed queue or remote CAD worker yet.

The [evolving plan](../../EVOLVING_CAD_AGENT_PLAN.md) keeps both backends active. MIT applies to project-authored code/documentation and synthetic examples; external software and private drawings have separate rights.