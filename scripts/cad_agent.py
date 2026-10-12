import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def find_freecad(directory=None):
    if directory:
        return Path(directory).resolve() / "bin"
    command = shutil.which("FreeCADCmd") or shutil.which("FreeCADCmd.exe")
    if command:
        return Path(command).parent
    roots = [Path("C:/Program Files"), Path("C:/Program Files (x86)")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Programs")
    for root in roots:
        candidates = [root / "FreeCAD 1.1"]
        candidates.extend(sorted(root.glob("FreeCAD*"), reverse=True))
        for candidate in candidates:
            if (candidate / "bin" / "FreeCADCmd.exe").is_file():
                return candidate / "bin"
    return None


def check_qcad(directory):
    installation = Path(directory or "C:/Program Files/QCAD").resolve()
    executable = installation / "qcadcmd.com"
    report = {"status": "blocked", "installation": str(installation),
              "console": str(executable), "conversion": "not_tested"}
    if not executable.is_file() or not (installation / "qcad.exe").is_file():
        report["error"] = "QCAD GUI or console executable not found; provide --qcad-dir."
        return report
    profile = ROOT / "work" / ("qcad-doctor-" + uuid4().hex[:8])
    profile.mkdir(parents=True)
    environment = os.environ.copy()
    environment.update(APPDATA=str(profile), LOCALAPPDATA=str(profile))
    command = [str(executable), "-no-gui", "-allow-multiple-instances",
               "-config", str(profile), "-autostart",
               "scripts/Pro/Tools/DwgInfo/DwgInfo.js", "dwginfo.bat", "-h"]
    process = None
    try:
        process = subprocess.Popen(command, cwd=installation, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, errors="replace")
        stdout, stderr = process.communicate(timeout=20)
        report.update(exit_code=process.returncode, stdout=stdout.strip(),
                      stderr=stderr.strip(), pid=process.pid)
        for line in stderr.splitlines():
            if line.startswith("QCAD version"):
                report["version"] = line.removeprefix("QCAD version").strip()
        if process.returncode == 0 and "Usage:" in stdout and "dwginfo" in stdout.lower():
            report["status"] = "headless_help_passed"
        else:
            report["error"] = "QCAD did not return the expected drawing-inspection help."
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=15, check=False)
        process.communicate(timeout=10)
        report.update(status="timeout", error="QCAD diagnostics exceeded 20 seconds.")
    except OSError as error:
        report["error"] = str(error)
    (profile / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def doctor(directory, include_qcad=False, qcad_directory=None):
    binary_dir = find_freecad(directory)
    executable = binary_dir / "FreeCADCmd.exe" if binary_dir else None
    report = {
        "status": "blocked",
        "os": platform.platform(),
        "os_architecture": platform.machine(),
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "freecad": {"command": str(executable) if executable else None},
        "rendering": "not_tested",
        "git_initialized": (ROOT / ".git").exists(),
    }
    if executable and executable.is_file():
        try:
            result = subprocess.run(
                [str(executable), "--version"], capture_output=True,
                text=True, errors="replace", timeout=15,
            )
            report["freecad"].update(
                version_output=result.stdout.strip(), stderr=result.stderr.strip(),
                exit_code=result.returncode,
                gui_available=(binary_dir / "FreeCAD.exe").is_file(),
            )
            report["status"] = "detected" if result.returncode == 0 else "blocked"
        except (OSError, subprocess.TimeoutExpired) as error:
            report["freecad"]["error"] = str(error)
    else:
        report["freecad"]["error"] = "FreeCADCmd was not found; provide --freecad-dir."
    if include_qcad:
        report["qcad"] = check_qcad(qcad_directory)
    print(json.dumps(report, indent=2))
    passed = report["status"] == "detected"
    if include_qcad:
        passed = passed and report["qcad"]["status"] == "headless_help_passed"
    return 0 if passed else 2


def smoke(args):
    binary_dir = find_freecad(args.freecad_dir)
    executable = binary_dir / ("FreeCAD.exe" if args.gui else "FreeCADCmd.exe") if binary_dir else None
    if not executable or not executable.is_file():
        print(json.dumps({"status": "blocked", "error": "Required FreeCAD executable not found."}))
        return 2
    if args.timeout <= 0:
        raise ValueError("Timeout must be positive.")
    work = ROOT / "work"
    work.mkdir(exist_ok=True)
    lock = work / ".freecad.lock"
    try:
        lock_file = lock.open("x")
    except FileExistsError:
        print(json.dumps({"status": "blocked", "error": "Another run holds work/.freecad.lock; investigate before removing a stale lock."}))
        return 2
    started = time.monotonic()
    process = None
    run_dir = work / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    report = {"status": "failed", "run_dir": str(run_dir), "mode": "gui" if args.gui else "console"}
    try:
        with lock_file:
            lock_file.write(str(os.getpid()))
        run_dir.mkdir()
        profile = run_dir / "profile"
        profile.mkdir()
        environment = os.environ.copy()
        environment.update(
            CAD_AGENT_RUN_DIR=str(run_dir), CAD_AGENT_TEST_MODE=args.test_mode,
            FREECAD_USER_HOME=str(profile), APPDATA=str(profile / "roaming"),
            LOCALAPPDATA=str(profile / "local"),
        )
        for name in ("roaming", "local"):
            (profile / name).mkdir()
        command = [str(executable), "--user-cfg", str(profile / "user.cfg"),
                   "--system-cfg", str(profile / "system.cfg"),
                   str(ROOT / "scripts" / "freecad" / "smoke.FCMacro")]
        with (run_dir / "stdout.log").open("w", encoding="utf-8") as stdout, (run_dir / "stderr.log").open("w", encoding="utf-8") as stderr:
            process = subprocess.Popen(command, env=environment, cwd=run_dir, stdout=stdout, stderr=stderr)
            report["pid"] = process.pid
            try:
                report["exit_code"] = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=15, check=False)
                process.wait(timeout=10)
                report.update(status="timeout", error="FreeCAD exceeded the configured time budget.")
        result_path = run_dir / "geometry.json"
        if result_path.is_file():
            report["geometry"] = json.loads(result_path.read_text(encoding="utf-8"))
            if report["status"] != "timeout" and report.get("exit_code") == 0 and report["geometry"].get("status") == "passed":
                report["status"] = "passed"
        elif report["status"] != "timeout":
            report["error"] = "FreeCAD did not produce a geometry report; inspect process logs."
    except Exception as error:
        report.update(status="failed", error=str(error))
    finally:
        if process is not None and process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=15, check=False)
            process.wait(timeout=10)
        lock.unlink(missing_ok=True)
    report["duration_seconds"] = round(time.monotonic() - started, 3)
    if run_dir.is_dir():
        (run_dir / "run.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser(description="Phase 1 local CAD diagnostics and synthetic tests.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    diagnostic = subparsers.add_parser("doctor")
    diagnostic.add_argument("--freecad-dir", help="FreeCAD installation directory containing bin/.")
    diagnostic.add_argument("--check-qcad", action="store_true", help="Also verify QCAD's headless inspection-script help.")
    diagnostic.add_argument("--qcad-dir", help="QCAD installation directory; used with --check-qcad.")
    synthetic = subparsers.add_parser("smoke")
    synthetic.add_argument("--freecad-dir")
    synthetic.add_argument("--gui", action="store_true", help="Render through a separate GUI process.")
    synthetic.add_argument("--timeout", type=float, default=90)
    synthetic.add_argument("--test-mode", choices=["normal", "script-error", "solver-error", "timeout"], default="normal")
    args = parser.parse_args()
    return doctor(args.freecad_dir, args.check_qcad, args.qcad_dir) if args.command == "doctor" else smoke(args)


if __name__ == "__main__":
    sys.exit(main())