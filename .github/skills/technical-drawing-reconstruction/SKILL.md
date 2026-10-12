---
name: technical-drawing-reconstruction
description: 'Interpret degraded mechanical drawing scans and reconstruct reviewable 2D CAD in FreeCAD or QCAD. Use for technical drawings, orthographic views, sections, coupling nuts, chamfers, threads, scan-to-CAD reconstruction, and semantic comparison of source versus generated drawings. Separate drafting meaning, measured geometry, and human approval.'
---

# Technical Drawing Reconstruction

This is an experimental workspace procedure, not a certified drafting-standard reference or a proven recognition engine. It addresses the observed failure of copying marks while losing their mechanical meaning. Follow workspace scope and the public release's confidentiality boundaries.

## Interpretation Before Geometry

1. Open the original page and enlarged component crops. Record the source hash, page, crop coordinates and any raster transforms. Enlargement does not recover lost information.
2. Identify view type and projection relationships from the actual sheet: orthographic exterior, section, detail or end view. Do not assume first-angle or third-angle projection without evidence. Use related views to test hypotheses, not to invent invisible dimensions.
3. List candidate components before drawing edges: body, spindle, sleeve, union nut, thread, hole, fastener, chamfer. For each candidate, record visible evidence, competing interpretations, uncertainty and the decision. Distinguish contours, face boundaries, centerlines, hidden lines, hatching, dimension lines, leaders and scan artifacts.
4. Separate directly observed labels from geometric derivations and estimates. A user identifying a component does not confirm its dimensions. Do not assign standard thread sizes, nut dimensions, materials or unit systems merely because a shape is familiar.
5. State the feature hypotheses before constructing the CAD. If the available views contradict the hypothesis, resolve the contradiction or mark the feature unresolved. Do not convert an ambiguous line into geometry solely to make the drawing complete.

## Mechanical Projection Checks

- A union nut must remain recognizable as one component around its axis. Test the continuous outer envelope, boundaries between projected flats, curved transitions at chamfered ends, and connections to the sleeve or tube. Avoid arbitrary octagons with detached stripes or three capsule-like components stacked together.
- A chamfer on a rotational surface meeting a flat can produce a curved projected intersection. Do not replace every such curve with a diagonal line. A circular-arc approximation is not the exact conic projection of a calibrated 3D model; label it as an approximation.
- Do not draw all visible circular shapes as holes. Use section/end views and line conventions to distinguish a bore, boss, recess, fastener or projected contour.
- Do not turn fastener projections into body lugs merely because their marks touch. Check whether the main body remains a separate component.
- Do not close an exterior silhouette with a pointed polygon if the source shows a rounded end. Use evidence-supported native curves and preserve uncertainty in radii.
- Thread and knurl conventions convey meaning. Arbitrary stripes are not equivalent to a technical representation. Model only the supported detail level and document simplifications.
- Distinguish axes from physical edges with appropriate long/short patterns and restrained line hierarchy. Explicit segmented centerlines are allowed for this pilot, but do not claim full standards compliance.

## Deterministic CAD Construction

Keep a versioned source model with IDs, feature ownership, units, measurements and uncertainty. Use native lines, circles and arcs where supported; do not embed the source raster and call it reconstructed CAD. Native arcs require center, radius, endpoints and an intermediate point or direction so the intended sweep is unambiguous.

Preserve previous models and artifacts. Run FreeCAD and QCAD sequentially with isolated profiles, bounded timeouts and cleanup restricted to owned processes. Changing a backend must not silently change the feature interpretation.

The local agent remains an experimental reconstruction workflow, not a proven general recognition service. Begin with diagnostics and known synthetic geometry:

```powershell
python .\scripts\cad_agent.py doctor --check-qcad
python .\scripts\cad_agent.py smoke --gui --timeout 60
python -m unittest discover -s tests -p test_public_contract.py -v
```

Do not reuse the drawing-05 coordinate template as evidence of recognition on another drawing.

## Four Separate Validation Gates

1. **Execution:** the process ends, required files exist, logs are retained, and no owned CAD process remains.
2. **Geometry:** save, close and reopen actual documents; inspect native types, layers, counts and coordinates. For arcs, validate intermediate points and sweep, not just center/radius. Check solver state without blanket coordinate blocking.
3. **Meaning:** independently revisit the source after rendering. Can a reader identify the same component and plausible 3D form? Review enlarged component details, envelope continuity, faceting/chamfers, view consistency, and physical versus conventional lines. Record failures even if geometry checks passed.
4. **Approval:** retain needs_review until an operator actually approves interpretation and required dimensions. Numerical backend agreement is never semantic approval.

Compare source, previous attempt and new output on the same provisional transform for local visual review. Also inspect native backend renders. Fit-to-panel screenshots are presentation only, not dimensional comparisons. Raster overlays using the tracing transform are not independent metrology.

## Evidence and Evaluation

Report explicitly whether the error was found autonomously, pointed out by the user, or detected after additional context. Record the output changes and remaining uncertainties. Do not claim a configured reasoning budget or token cost when it was not measured.

The drawing-05 union-nut follow-up is context-assisted: the user supplied the component identification and the failure location. To evaluate this skill, use new drawings in independent sessions, matched time budgets and the same acceptance rubric, with and without the skill. Include failures and require human technical review. Until that comparison exists, usefulness is a hypothesis, not a measured reliability improvement.
