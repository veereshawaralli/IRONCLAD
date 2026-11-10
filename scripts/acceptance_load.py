"""Run the sustained benchmark in one process/network namespace with cleanup."""

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

with tempfile.TemporaryDirectory() as temp:
    env = {
        **os.environ,
        "IRONCLAD_ADMIN_TOKEN": secrets.token_urlsafe(32),
        "IRONCLAD_DB": str(Path(temp) / "load.db"),
    }
    # Benchmark one installation without borrowing configured production services.
    env.pop("IRONCLAD_DATABASE_URL", None)
    env.pop("IRONCLAD_REDIS_URL", None)
    with (Path(temp) / "server.log").open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "ironclad.api:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8123",
                "--no-access-log",
                "--timeout-graceful-shutdown",
                "5",
            ],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("Benchmark server failed to start")
                try:
                    with urllib.request.urlopen(
                        "http://127.0.0.1:8123/openapi.json", timeout=1
                    ):
                        break
                except OSError:
                    time.sleep(0.1)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/live_load_test.py",
                    "--clients",
                    "500",
                    "--seconds",
                    "30",
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=100,
                check=True,
            )
            data = json.loads(result.stdout)
            Path("docs/live-load-test.json").write_text(
                json.dumps(data, indent=2) + "\n"
            )
            print(json.dumps(data, indent=2))
            if data["failures"] or data["p95_delivery_ms"] >= 200:
                raise RuntimeError("Live fan-out acceptance target not reached")
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
