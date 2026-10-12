# What the Experiments Establish

These are local feasibility experiments, not a validated production converter. The user authorized publication of [the supplied drawing set](../../drawings) and [selected input/output cases](../../site/examples.html). The separate private-originals folder, private configuration and raw provider responses are not distributed.

## Native Operations Before Recognition

FreeCAD's synthetic rectangle/two-circle test demonstrates a real dimension change, solver relationships and saved-file reopening. QCAD's synthetic section demonstrates a native ANSI31 hatch with two loops: material outside an internal void. Its reopened area is 443.75 provisional drawing units squared, with a dedicated HATCH layer and a closed OUTLINE polyline. This is persistence evidence, not accuracy evidence for a scan.

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
python -m unittest discover -s tests -p test_public_contract.py -v
```

Copy the structure of [the configuration example](../../config/astra-example.json) to your local, ignored configuration and replace placeholders. Never store secrets in it. The authenticated CLI token stays in memory. The corpus runners currently expect ten explicitly named local files and are laboratory entrypoints, not general folder services. There is no distributed queue or remote CAD worker yet.

The [evolving plan](../../EVOLVING_CAD_AGENT_PLAN.md) keeps both backends active. MIT applies to project-authored code/documentation and synthetic examples; external software and private drawings have separate rights.