"""Execute only in a fresh restricted Docker container; never fall back to host."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import cast

from .repository import safe_file
from .schema import Proposal, Verification

IMAGE = "ironclad-sandbox:local"
CHECK = r"""import json, pathlib, subprocess, xml.etree.ElementTree as ET
r = subprocess.run(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml=/tmp/report.xml"], capture_output=True, text=True, timeout=45)
failures = []
if pathlib.Path("/tmp/report.xml").exists():
    for case in ET.parse("/tmp/report.xml").iter("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            failures.append(case.attrib.get("classname", "") + "::" + case.attrib.get("name", ""))
checks = {}
outputs = [r.stdout+r.stderr]
for name, cmd in {"lint": ["ruff", "check", "--isolated", "--select", "E4,E7,E9,F,I", "--no-cache", "."], "types": ["mypy", "--ignore-missing-imports", "--cache-dir", "/tmp/mypy", "."], "security": ["bandit", "-q", "-r", ".", "-s", "B101"]}.items():
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    checks[name] = result.returncode == 0
    outputs.append(name + ":\n" + result.stdout + result.stderr)
print(json.dumps({"test_code": r.returncode, "failures": failures, "checks": checks, "output": "\n".join(outputs)[-16000:]}))
"""


class DockerSandbox:
    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    def snapshot(self, repo: Path, destination: Path) -> None:
        import os

        count = 0
        total = 0
        for directory, dirs, names in os.walk(repo, followlinks=False):
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d
                not in {
                    "node_modules",
                    "venv",
                    "__pycache__",
                    "infra",
                    "migrations",
                    "secrets",
                }
                and not Path(directory, d).is_symlink()
            ]
            for name in names:
                if not name.endswith(".py"):
                    continue
                rel = Path(directory, name).relative_to(repo).as_posix()
                source = safe_file(repo, rel)
                count += 1
                total += source.stat().st_size
                if count > 500 or total > 10000000:
                    raise ValueError("Sandbox snapshot exceeds file/byte cap")
                target = destination / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

    def run(self, source: Path) -> dict[str, object]:
        if not shutil.which("docker"):
            raise ValueError(
                "Docker is required for verification; host execution is forbidden"
            )
        name = "ironclad-" + __import__("uuid").uuid4().hex
        args = [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--user",
            "65534:65534",
            "--tmpfs",
            "/tmp:rw,nosuid,size=128m,mode=1777",
            "-v",
            f"{source.resolve()}:/workspace:ro",
            "-w",
            "/workspace",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            IMAGE,
            "python",
            "-c",
            CHECK,
        ]
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=self.timeout, check=False
            )
            if result.returncode:
                raise ValueError(
                    "Sandbox unavailable or timed out; inspect Docker image/runtime"
                )
            lines = result.stdout.splitlines()
            return dict(json.loads(lines[-1]))
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True,
                timeout=10,
                check=False,
            )

    def verify(self, repo: Path, proposal: Proposal) -> Verification:
        from .repository import render_patch

        render_patch(repo, proposal, 5)
        parent = Path("/tmp/ironclad-sandboxes")
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ironclad-", dir=parent) as temp:
            scratch = Path(temp)
            # temp root must be traversable by container's non-root UID.
            scratch.chmod(0o755)
            self.snapshot(repo, scratch)
            baseline = self.run(scratch)
            for edit in proposal.edits:
                path = safe_file(scratch, edit.path)
                path.write_text(path.read_text().replace(edit.old, edit.new, 1))
            patched = self.run(scratch)
        before = cast(list[str], baseline["failures"])
        after = cast(list[str], patched["failures"])
        checks = cast(dict[str, bool], patched["checks"]).copy()
        checks["baseline_reproduced"] = bool(before) and baseline["test_code"] == 1
        checks["tests"] = patched["test_code"] == 0
        checks["no_regression"] = not (set(after) - set(before))
        return Verification(
            passed=all(checks.values()),
            baseline_failures=before,
            remaining_failures=after,
            checks=checks,
            output=str(patched["output"]),
        )
