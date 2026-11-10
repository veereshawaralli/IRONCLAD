"""Draft-only GitHub publication, scoped to the configured repository."""

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .schema import Proposal


class GitHub:
    def __init__(self) -> None:
        self.repo = os.environ["IRONCLAD_GITHUB_REPO"]
        self.token = os.environ["IRONCLAD_GITHUB_TOKEN"]
        self.failures = 0
        self.blocked_until = 0.0

    def request(
        self, method: str, path: str, body: dict[str, object] | None = None
    ) -> Any:
        if time.monotonic() < self.blocked_until:
            raise ValueError("GitHub circuit breaker open")
        # Only reads are retried automatically. POST outcomes can be ambiguous.
        for attempt in range(3 if method == "GET" else 1):
            req = urllib.request.Request(
                "https://api.github.com/repos/" + self.repo + path,
                method=method,
                data=json.dumps(body).encode() if body is not None else None,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "IRONCLAD",
                },
            )
            req.add_unredirected_header("Authorization", "Bearer " + self.token)
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.load(response)
                self.failures = 0
                return result
            except urllib.error.HTTPError as exc:
                self.failures += 1
                if self.failures >= 3:
                    self.blocked_until = time.monotonic() + 60
                if exc.code in {403, 429}:
                    raise ValueError(
                        "GitHub rate limit or permission failure; retry after checking installation access"
                    ) from None
                if method != "GET" or exc.code < 500 or attempt == 2:
                    raise ValueError("GitHub HTTP " + str(exc.code)) from None
                time.sleep(0.2 * (2**attempt))
        raise ValueError("GitHub request exhausted")

    def publish(
        self,
        rid: str,
        proposal: Proposal,
        hashes: dict[str, str],
        report: dict[str, object],
    ) -> str:
        branch = "ironclad/repair-" + rid
        owner = self.repo.split("/")[0]
        existing = self.request("GET", "/pulls?state=all&head=" + owner + ":" + branch)
        if existing:
            return str(existing[0]["html_url"])
        metadata = self.request("GET", "")
        base = metadata["default_branch"]
        head = self.request("GET", "/git/ref/heads/" + base)["object"]["sha"]
        tree = self.request("GET", "/git/commits/" + head)["tree"]["sha"]
        from pathlib import PurePosixPath

        prefix = PurePosixPath(os.environ.get("IRONCLAD_REPO_SUBDIR", ""))
        if prefix.is_absolute() or ".." in prefix.parts:
            raise ValueError("Unsafe repository subdirectory")
        texts: dict[str, str] = {}
        for edit in proposal.edits:
            if edit.path not in texts:
                from urllib.parse import quote

                remote = self.request(
                    "GET",
                    "/contents/"
                    + quote((prefix / edit.path).as_posix(), safe="/")
                    + "?ref="
                    + head,
                )
                raw = base64.b64decode(remote["content"])
                if hashlib.sha256(raw).hexdigest() != hashes.get(edit.path):
                    raise ValueError(
                        "Repository changed since diagnosis; submit a fresh incident"
                    )
                texts[edit.path] = raw.decode()
            if texts[edit.path].count(edit.old) != 1:
                raise ValueError("Remote edit no longer matches exactly once")
            texts[edit.path] = texts[edit.path].replace(edit.old, edit.new, 1)
        new_tree = self.request(
            "POST",
            "/git/trees",
            {
                "base_tree": tree,
                "tree": [
                    {
                        "path": (prefix / p).as_posix(),
                        "mode": "100644",
                        "type": "blob",
                        "content": text,
                    }
                    for p, text in texts.items()
                ],
            },
        )["sha"]
        marker = "fix: " + proposal.summary + " [ironclad:" + rid + "]"
        # A previous ambiguous attempt may already have created the repair branch.
        try:
            prior = self.request("GET", "/git/ref/heads/" + branch)
        except ValueError as exc:
            if str(exc) != "GitHub HTTP 404":
                raise
            prior = None
        if prior:
            prior_commit = self.request("GET", "/git/commits/" + prior["object"]["sha"])
            if (
                prior_commit["message"] != marker
                or prior_commit["tree"]["sha"] != new_tree
            ):
                raise ValueError("Repair branch collision; refusing to overwrite")
        else:
            commit = self.request(
                "POST",
                "/git/commits",
                {"message": marker, "tree": new_tree, "parents": [head]},
            )["sha"]
            self.request(
                "POST", "/git/refs", {"ref": "refs/heads/" + branch, "sha": commit}
            )
        pr = self.request(
            "POST",
            "/pulls",
            {
                "title": str(report["title"]),
                "body": str(report["body"])
                + "\n\nIncident: "
                + rid
                + "\nHuman review required. No auto-merge.",
                "head": branch,
                "base": base,
                "draft": True,
            },
        )
        return str(pr["html_url"])
