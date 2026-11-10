import ast
import difflib
import hashlib
import re
from pathlib import Path, PurePosixPath

from .schema import Evidence, Proposal

DENIED = {
    "migrations",
    "infra",
    ".github",
    ".git",
    "secrets",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
}


def safe_file(root: Path, name: str) -> Path:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Unsafe repository path")
    if any(part in DENIED or part.startswith(".") for part in path.parts):
        raise ValueError("Denied repository path")
    if any(
        word in path.name.lower()
        for word in ("lock", "secret", "credential", ".pem", ".key")
    ):
        raise ValueError("Sensitive or locked file")
    target = root.joinpath(*path.parts)
    if any(p.is_symlink() for p in [target, *target.parents] if p != root.parent):
        raise ValueError("Symlink traversal forbidden")
    target.resolve().relative_to(root.resolve())
    if not target.is_file() or target.stat().st_size > 100000:
        raise ValueError("Missing or oversized file")
    return target


def chunks(root: Path, limit: int) -> list[Evidence]:
    result: list[Evidence] = []
    scanned = 0
    # os.walk prunes denied trees before descent; never follow symlinks.
    import os

    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in DENIED
            and not d.startswith(".")
            and not Path(directory, d).is_symlink()
        )
        for name in sorted(names):
            if not name.endswith(".py"):
                continue
            if scanned >= 200:
                return result
            scanned += 1
            relative = Path(directory, name).relative_to(root).as_posix()
            try:
                text = safe_file(root, relative).read_text()
                tree = ast.parse(text)
            except (ValueError, OSError, UnicodeError, SyntaxError):
                continue
            lines = text.splitlines()
            for node in tree.body:
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    end = node.end_lineno or node.lineno
                    snippet = "\n".join(lines[node.lineno - 1 : end])
                    if len(snippet) <= limit:
                        result.append(
                            Evidence(
                                path=relative,
                                start_line=node.lineno,
                                end_line=end,
                                text=snippet,
                            )
                        )
    return result


def retrieve(root: Path, log: str, limit: int) -> list[Evidence]:
    words = set(re.findall(r"[a-zA-Z_]{3,}", log.lower()))
    candidates = chunks(root, limit)
    candidates.sort(
        key=lambda e: (
            -sum(w in (e.path + e.text).lower() for w in words),
            e.path,
            e.start_line,
        )
    )
    selected: list[Evidence] = []
    used = 0
    for item in candidates:
        if used + len(item.text) <= limit:
            selected.append(item)
            used += len(item.text)
        if len(selected) == 8:
            break
    if not selected:
        raise ValueError("No eligible Python function/class evidence")
    return selected


def render_patch(
    root: Path, proposal: Proposal, max_files: int
) -> tuple[str, dict[str, str]]:
    paths = [edit.path for edit in proposal.edits]
    if len(set(paths)) > max_files:
        raise ValueError("File budget exceeded")
    current: dict[str, str] = {}
    original: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for edit in proposal.edits:
        target = safe_file(root, edit.path)
        if target.suffix != ".py":
            raise ValueError("Phase one permits Python edits only")
        if edit.path not in current:
            original[edit.path] = target.read_text()
            current[edit.path] = original[edit.path]
            hashes[edit.path] = hashlib.sha256(target.read_bytes()).hexdigest()
        if current[edit.path].count(edit.old) != 1:
            raise ValueError("Edit must match exactly once")
        current[edit.path] = current[edit.path].replace(edit.old, edit.new, 1)
        ast.parse(current[edit.path])
    diff = "".join(
        "".join(
            difflib.unified_diff(
                original[p].splitlines(True),
                current[p].splitlines(True),
                fromfile="a/" + p,
                tofile="b/" + p,
            )
        )
        for p in current
    )
    if not diff:
        raise ValueError("Empty patch")
    return diff, hashes
