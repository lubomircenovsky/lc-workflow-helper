"""Strictly scoped cleanup of CAD worker run directories."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")


def _linked(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def is_owned_run(root, path):
    root = Path(root).resolve()
    path = Path(path)
    if not _RUN_ID.fullmatch(path.name) or _linked(path) or not path.is_dir():
        return False
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    if resolved.parent != root:
        return False
    source_path = path / "source.json"
    if not source_path.is_file() or _linked(source_path):
        return False
    try:
        profile_path = path / "profile.json"
        if _linked(profile_path) or profile_path.stat().st_size > 65536:
            return False
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return False
    if not isinstance(profile, dict):
        return False
    source_hash = profile.get("source_hash")
    return (profile.get("method") == "A" and profile.get("delivery") == "EDITABLE_NGONS"
            and isinstance(profile.get("code_hash"), str)
            and re.fullmatch(r"[0-9a-f]{64}", profile["code_hash"]) is not None
            and isinstance(source_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", source_hash) is not None)


def find_owned_runs(root):
    root = Path(root).resolve()
    if not root.is_dir():
        return []
    return [path for path in sorted(root.iterdir()) if is_owned_run(root, path)]


def delete_owned_run(root, path):
    root = Path(root).resolve()
    path = Path(path)
    if not is_owned_run(root, path):
        raise ValueError(f"Refusing to delete unverified CAD run: {path}")
    target = path.resolve(strict=True)
    if target.parent != root or target == root:
        raise ValueError(f"CAD run escaped the selected Run Folder: {path}")
    shutil.rmtree(target)
