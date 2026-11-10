import base64
import hashlib

import pytest

from ironclad.github import GitHub
from ironclad.schema import Proposal


class FakeGitHub(GitHub):
    def __init__(self, changed=False):
        self.repo = "example/repo"
        self.calls = []
        self.changed = changed

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.startswith("/pulls?"):
            return []
        if path == "":
            return {"default_branch": "main"}
        if path == "/git/ref/heads/main":
            return {"object": {"sha": "head"}}
        if path == "/git/commits/head":
            return {"tree": {"sha": "base-tree"}}
        if path.startswith("/contents/"):
            return {
                "content": base64.b64encode(
                    ("changed" if self.changed else "return 1\n").encode()
                ).decode()
            }
        if path == "/git/trees":
            return {"sha": "new-tree"}
        if path.startswith("/git/ref/heads/ironclad"):
            raise ValueError("GitHub HTTP 404")
        if path == "/git/commits":
            return {"sha": "new-commit"}
        if path == "/git/refs":
            return {}
        if path == "/pulls":
            return {"html_url": "https://github.com/example/repo/pull/1"}
        raise AssertionError(path)


def data():
    return Proposal.model_validate(
        {
            "summary": "guard input",
            "edits": [
                {
                    "path": "stats.py",
                    "old": "return 1",
                    "new": "return 2",
                    "rationale": "fixture",
                }
            ],
        }
    ), {"stats.py": hashlib.sha256(b"return 1\n").hexdigest()}


def test_draft_only_no_attribution():
    github = FakeGitHub()
    proposal, hashes = data()
    github.publish(
        "run123", proposal, hashes, {"title": "fix input", "body": "Verified fixture"}
    )
    pr = next(body for method, path, body in github.calls if path == "/pulls")
    assert pr["draft"] is True
    assert all("merge" not in path for _, path, _ in github.calls)
    commit = next(body for method, path, body in github.calls if path == "/git/commits")
    assert "Co-authored-by" not in commit["message"]


def test_stale_repository_blocks_publication():
    github = FakeGitHub(True)
    proposal, hashes = data()
    with pytest.raises(ValueError, match="changed"):
        github.publish("run", proposal, hashes, {"title": "fix", "body": "test"})
    assert not any(method == "POST" for method, _, _ in github.calls)
