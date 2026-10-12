import asyncio
from contextlib import AsyncExitStack
import json
import os
from pathlib import Path
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]


async def main():
    output = Path(sys.argv[1]).resolve()
    started = time.perf_counter()
    candidate = os.environ.get("CAD_AGENT_MCP_CANDIDATE", "neka")
    def phase(name):
        (output / "worker-progress.json").write_text(json.dumps({"phase": name, "elapsed_seconds": time.perf_counter() - started}), encoding="utf-8")
    phase("starting")
    environment = dict(os.environ, CAD_AGENT_MCP_ISOLATED_PROFILE=str(output / "profile"), CAD_AGENT_MCP_ISOLATED_PORT="19885" if candidate == "robust" else "19875", PYTHONDONTWRITEBYTECODE="1")
    parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / "scripts/serve_freecad_mcp.py")], env=environment, cwd=str(ROOT))
    async with AsyncExitStack() as stack:
        errors = stack.enter_context((output / "mcp-stderr.log").open("w", encoding="utf-8"))
        reader, writer = await stack.enter_async_context(stdio_client(parameters, errlog=errors))
        session = await stack.enter_async_context(ClientSession(reader, writer))
        phase("initializing")
        await asyncio.wait_for(session.initialize(), 75)
        initialization = time.perf_counter() - started
        phase("listing_tools")
        tools = await asyncio.wait_for(session.list_tools(), 20)
        (output / "tools.json").write_text(tools.model_dump_json(indent=2), encoding="utf-8")
        code = "from pathlib import Path\nexec(compile(Path(" + repr(str(ROOT / "scripts/freecad/agent_build.FCMacro")) + ").read_text(), 'agent_build.FCMacro', 'exec'))"
        called = time.perf_counter()
        tool = "execute_python" if candidate == "robust" else "execute_code"
        arguments = {"code": code, "timeout_ms": 60000} if candidate == "robust" else {"code": code, "include_screenshot": False}
        phase("building_cad")
        response = await asyncio.wait_for(session.call_tool(tool, arguments), 75)
        phase("cad_response_received")
        metrics = {"initialize_seconds": initialization, "cad_call_seconds": time.perf_counter() - called,
                   "tool_calls": 1, "candidate": candidate, "tool_count": len(tools.tools), "schema_bytes": len(tools.model_dump_json().encode("utf-8")), "request_characters": len(code),
                   "response_characters": sum(len(item.text) for item in response.content if item.type == "text"),
                   "is_error": response.isError, "transport": "local SDK MCP call; model sees a guarded component API, not arbitrary Python tool"}
        (output / "mcp-metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        if response.isError:
            raise RuntimeError("MCP execute_code failed.")


if __name__ == "__main__":
    asyncio.run(main())