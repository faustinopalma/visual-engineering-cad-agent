# CAD Agent Workspace Instructions

- Write all project content, code, comments, reports, and documentation in English. User conversations may be in Italian or English.
- The user authorized a public repository, commits, push and GitHub Pages on October 12, 2026. Publish only the allowlisted reusable code, documentation, synthetic assets and aggregate metrics. Original drawings, scan-derived assets, private configuration and raw run artifacts stay local unless separately cleared for publication.
- Follow `EVOLVING_CAD_AGENT_PLAN.md`. FreeCAD and QCAD remain active experimental backends; neither is a final production choice. Keep CAD execution local, sequential and deterministic. Existing inference experiments and explicitly authorized Sol deployment/capacity changes do not authorize further Azure infrastructure or permission changes. General unattended folder batch and remote CAD hosting remain deferred. Project-authored code and documentation are MIT-licensed; third-party components and drawing rights remain separate.
- FreeCAD and QCAD are already installed. Verify actual executables and versions; do not reinstall software or alter shared CAD profiles, addons, or other projects.
- Use deterministic CAD scripts and isolated run directories. Preserve original drawings under `disegni/`; do not overwrite inputs or previous run artifacts.
- Validate actual CAD geometry, solver results, and reopened saved documents. A process exit code, a screenshot, or a mock alone does not establish dimensional correctness.
- Never invent unreadable dimensions, units, human confirmation, token usage, or billing data. Distinguish confirmed, derived, and estimated measurements.
- Keep execution sequential, with bounded timeouts and process-tree cleanup restricted to processes started by this workspace.
- Do not read or log credentials. Use only necessary local dependencies; do not add frameworks or cloud packages prematurely.
- See `README.md` for runnable diagnostics, synthetic tests, verification evidence, and current limitations.