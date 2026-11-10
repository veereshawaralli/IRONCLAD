import json
import shutil
import subprocess
import sys
from pathlib import Path

from ironclad.sandbox import CHECK


def test_trusted_fixture_check_protocol(tmp_path):
    # Only the checked-in trusted fixture runs on the test host; never generated code.
    for path in Path("examples/broken_repo").glob("*.py"):
        shutil.copyfile(path, tmp_path / path.name)
    result = subprocess.run(
        [sys.executable, "-c", CHECK],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout.splitlines()[-1])
    assert data["test_code"] == 1
    assert data["failures"] == ["test_stats::test_empty"]
    assert all(data["checks"].values())
    assert "lint:" in data["output"] and "security:" in data["output"]
