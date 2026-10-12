import os
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import xmlrpc.client


ROOT = Path(__file__).resolve().parents[1]
PROFILE = Path(os.environ.get("CAD_AGENT_MCP_ISOLATED_PROFILE", str(ROOT / "work/mcp-neka-profile"))).resolve()
PORT = int(os.environ.get("CAD_AGENT_MCP_ISOLATED_PORT", "9875"))
CANDIDATE = os.environ.get("CAD_AGENT_MCP_CANDIDATE", "neka")


def main():
    if CANDIDATE not in {"neka", "robust"}:
        raise ValueError("Unsupported MCP candidate.")
    addon = "FreeCADMCP" if CANDIDATE == "neka" else "FreecadRobustMCPBridge"
    source = Path("C:/code/FreecadMCP/.lab/sources") / CANDIDATE / "addon" / addon
    destination = PROFILE / "Mod" / addon
    PROFILE.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    environment = os.environ.copy()
    for directory in (PROFILE / "temp", PROFILE / "home", PROFILE / "roaming", PROFILE / "local"):
        directory.mkdir(exist_ok=True)
    environment.update(FREECAD_USER_HOME=str(PROFILE), FREECAD_USER_DATA=str(PROFILE),
                       FREECAD_USER_TEMP=str(PROFILE / "temp"), HOME=str(PROFILE / "home"),
                       USERPROFILE=str(PROFILE / "home"), APPDATA=str(PROFILE / "roaming"),
                       LOCALAPPDATA=str(PROFILE / "local"), TEMP=str(PROFILE / "temp"), TMP=str(PROFILE / "temp"),
                       FREECAD_MODE="xmlrpc", FREECAD_XMLRPC_PORT=str(PORT), FREECAD_SOCKET_HOST="127.0.0.1",
                       CAD_AGENT_MCP_PROFILE=str(PROFILE), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    with socket.socket() as port_check:
        port_check.bind(("127.0.0.1", PORT))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(60)
    environment["CAD_AGENT_READY_PORT"] = str(listener.getsockname()[1])
    command = ["C:/Program Files/FreeCAD 1.1/bin/FreeCAD.exe", "--user-cfg", str(PROFILE / "user.cfg"),
               "--system-cfg", str(PROFILE / "system.cfg"), str(ROOT / "scripts/freecad/mcp_bootstrap.FCMacro")]
    cad = None
    server = None
    try:
        with (PROFILE / "stdout.log").open("w") as stdout, (PROFILE / "stderr.log").open("w") as stderr:
            startup = subprocess.STARTUPINFO() if os.name == "nt" else None
            if startup is not None:
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = 7
            environment["CAD_AGENT_BACKGROUND"] = "1"
            cad = subprocess.Popen(command, env=environment, cwd=PROFILE, stdout=stdout, stderr=stderr, startupinfo=startup)
        connection, address = listener.accept()
        with connection:
            connection.settimeout(5)
            readiness = json.loads(connection.recv(16384).decode("utf-8"))
        if readiness.get("status") != "started":
            raise RuntimeError("Isolated FreeCAD bridge failed: " + json.dumps(readiness))
        server_code = "from freecad_mcp import server; server.main()"
        if CANDIDATE == "neka" and PORT != 9875:
            server_code = ("from freecad_mcp import server; from freecad_mcp.freecad_client import FreeCADConnection; "
                           "server.state.freecad_connection=FreeCADConnection(host='127.0.0.1',port=" + str(PORT) + "); server.main()")
        server = subprocess.Popen([sys.executable, "-c", server_code],
                                  cwd=ROOT, env=environment, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
        last_check = time.monotonic()
        while True:
            try:
                return server.wait(timeout=2)
            except subprocess.TimeoutExpired:
                if cad.poll() is not None:
                    raise RuntimeError("Owned FreeCAD process exited while MCP was still waiting.")
                if time.monotonic() - last_check >= 120:
                    print("MCP supervisor: owned FreeCAD and bridge processes still alive; operation timeout enforced by caller.", file=sys.stderr, flush=True)
                    last_check = time.monotonic()
    finally:
        listener.close()
        if server is not None and server.poll() is None:
            server.terminate()
            server.wait(timeout=10)
        if cad is not None and cad.poll() is None:
            subprocess.run(["taskkill", "/PID", str(cad.pid), "/T", "/F"], capture_output=True, timeout=15)
            cad.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())