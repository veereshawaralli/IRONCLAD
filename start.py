"""Cross-platform local launcher: python start.py (Windows: py -3.12 start.py)."""

import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(args: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def main() -> None:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("Install Node.js 22 LTS, reopen the terminal, and retry.")
    python = (
        ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    if not python.exists():
        run([sys.executable, "-m", "venv", str(ROOT / ".venv")])
    run([str(python), "-m", "pip", "install", "-e", ".[dev,production]"])
    # npm.cmd is a trusted local Node installation. Shell is used only for that
    # fixed executable and fixed arguments on Windows, never for user input.
    for command in ("ci", "run build"):
        if os.name == "nt":
            subprocess.run(
                f'"{npm}" {command}', cwd=ROOT / "web", shell=True, check=True
            )
        else:
            run([npm, *command.split()], ROOT / "web")
    state = ROOT / ".ironclad"
    state.mkdir(exist_ok=True)
    env = os.environ.copy()
    if (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip().startswith("IRONCLAD_") and value.strip():
                env[key.strip()] = value.strip().strip("\"'")
    if not env.get("IRONCLAD_ADMIN_TOKEN"):
        token_file = state / "admin-token"
        if not token_file.exists():
            token_file.write_text(secrets.token_urlsafe(32))
            token_file.chmod(0o600)
        env["IRONCLAD_ADMIN_TOKEN"] = token_file.read_text().strip()
    print("IRONCLAD: http://localhost:8000", flush=True)
    print("Local access token:", env["IRONCLAD_ADMIN_TOKEN"], flush=True)
    print("Keep this terminal open. Ctrl+C stops the application.", flush=True)
    with (state / "worker.log").open("a") as log:
        worker = subprocess.Popen(
            [str(python), "-m", "ironclad.worker"],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
        )
        server = subprocess.Popen(
            [
                str(python),
                "-m",
                "uvicorn",
                "ironclad.api:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=ROOT,
            env=env,
        )
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError(
                        "Server stopped; inspect the terminal error above."
                    )
                try:
                    with urllib.request.urlopen(
                        "http://127.0.0.1:8000/openapi.json", timeout=1
                    ):
                        pass
                    webbrowser.open("http://localhost:8000")
                    break
                except OSError:
                    time.sleep(0.1)
            server.wait()
        except KeyboardInterrupt:
            pass
        finally:
            for process in (server, worker):
                if process.poll() is None:
                    process.terminate()
            for process in (server, worker):
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from None
