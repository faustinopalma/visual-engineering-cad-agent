# CAD Agent Workspace Instructions

- Write all project content, code, comments, reports, and documentation in English. User conversations may be in Italian or English.
- The user authorized a public repository, commits, push and GitHub Pages on October 12, 2026, and subsequently authorized publishing `drawings/` and selected drawing input/output examples. Keep `disegni-originali/`, private configuration and raw run artifacts local. Project MIT terms do not automatically transfer ownership or license rights in supplied drawings.
- Follow `EVOLVING_CAD_AGENT_PLAN.md`. FreeCAD and QCAD remain active experimental backends; neither is a final production choice. Keep CAD execution local, sequential and deterministic. Existing inference experiments and explicitly authorized Sol deployment/capacity changes do not authorize further Azure infrastructure or permission changes. General unattended folder batch and remote CAD hosting remain deferred. Project-authored code and documentation are MIT-licensed; third-party components and drawing rights remain separate.
- FreeCAD and QCAD are already installed. Verify actual executables and versions; do not reinstall software or alter shared CAD profiles, addons, or other projects.
- Use deterministic CAD scripts and isolated run directories. Preserve supplied drawings under `drawings/` and private originals under `disegni-originali/`; do not overwrite inputs or previous run artifacts.
- Validate actual CAD geometry, solver results, and reopened saved documents. A process exit code, a screenshot, or a mock alone does not establish dimensional correctness.
- Never invent unreadable dimensions, units, human confirmation, token usage, or billing data. Distinguish confirmed, derived, and estimated measurements.
- Keep execution sequential, with bounded timeouts and process-tree cleanup restricted to processes started by this workspace.
- Do not read or log credentials. Use only necessary local dependencies; do not add frameworks or cloud packages prematurely.
- See `README.md` for runnable diagnostics, synthetic tests, verification evidence, and current limitations.