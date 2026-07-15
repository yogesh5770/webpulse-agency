"""DB-backed site file store + a bridge to a temp working directory.

The DATABASE is the source of truth for every website's files (so IDE edits
persist across restarts on ephemeral hosts). But two things still need real
files on disk:
  - the AI agent's tool loop (it greps/edits/rms files + uses git for undo), and
  - the deploy step (zips/uploads a folder).

So we "materialize" a site from the DB into a temp dir, run the operation, then
"sync" the dir back into the DB. A git repo inside the temp dir gives us the
same one-click undo as before, and we keep the newest materialized dir per site
cached so undo has history to walk back through within a session.

Public helpers used by the app:
  list_files / read_file / write_file / create_file / delete_file / rename_file
      -> direct DB operations (what the IDE calls)
  materialize(place_id) -> workdir   (DB -> disk, git-initialized)
  sync(place_id, workdir)            (disk -> DB)
  undo(place_id)                     (git revert in the cached workdir, re-synced)
"""
import os
import re
import subprocess
import tempfile

import db

# Cache the working dir per site so undo has git history within a session.
_WORKDIRS: dict[str, str] = {}


# ---- path safety (mirror of the agent's sandbox rule) ----------------

def _safe_rel(path: str) -> str:
    """Normalize a relative path and refuse anything that escapes the site."""
    p = (path or "").replace("\\", "/").lstrip("/")
    parts = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            raise ValueError(f"Path escapes site: {path}")
        parts.append(seg)
    if not parts:
        raise ValueError("Empty path")
    return "/".join(parts)


# ---- direct DB file ops (what the IDE hits) --------------------------

def list_files(place_id: str) -> list[str]:
    return db.site_list_files(place_id)


def read_file(place_id: str, path: str) -> str:
    content = db.site_read_file(place_id, _safe_rel(path))
    if content is None:
        raise FileNotFoundError(path)
    return content


def write_file(place_id: str, path: str, content: str) -> str:
    path = _safe_rel(path)
    db.site_write_file(place_id, path, content)
    return f"Wrote {len(content)} bytes to {path}"


def create_file(place_id: str, path: str, content: str = "") -> str:
    path = _safe_rel(path)
    if db.site_read_file(place_id, path) is not None:
        return f"ERROR: {path} already exists."
    db.site_write_file(place_id, path, content)
    return f"Created {path} ({len(content)} bytes)."


def delete_file(place_id: str, path: str) -> str:
    path = _safe_rel(path)
    if db.site_read_file(place_id, path) is None:
        return f"ERROR: {path} does not exist."
    db.site_delete_file(place_id, path)
    return f"Deleted {path}."


def rename_file(place_id: str, path: str, new_path: str) -> str:
    path, new_path = _safe_rel(path), _safe_rel(new_path)
    if db.site_read_file(place_id, path) is None:
        return f"ERROR: {path} does not exist."
    if db.site_read_file(place_id, new_path) is not None:
        return f"ERROR: {new_path} already exists."
    db.site_rename_file(place_id, path, new_path)
    return f"Renamed {path} -> {new_path}."


def create_site(place_id: str, files: dict) -> None:
    """Seed a brand-new site's files in the DB (used by the generator)."""
    db.site_replace_all(place_id, {_safe_rel(p): c for p, c in files.items()})


# ---- DB <-> temp dir bridge (for agent + deploy) ---------------------

def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)


def _ensure_repo(root: str) -> None:
    if not os.path.isdir(os.path.join(root, ".git")):
        _git(root, "init")
        _git(root, "config", "user.email", "agent@local")
        _git(root, "config", "user.name", "Site Agent")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "checkpoint: baseline")


def materialize(place_id: str) -> str:
    """Write all of a site's DB files into a fresh temp dir; return its path.
    The dir is git-initialized so the agent can checkpoint/undo."""
    workdir = tempfile.mkdtemp(prefix=f"site_{place_id[:8]}_")
    files = db.site_all_files(place_id)
    for path, content in files.items():
        full = os.path.join(workdir, path)
        os.makedirs(os.path.dirname(full) or workdir, exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
    _ensure_repo(workdir)
    _WORKDIRS[place_id] = workdir
    return workdir


def _read_dir(workdir: str) -> dict:
    out = {}
    for r, _d, fs in os.walk(workdir):
        if ".git" in r:
            continue
        for fn in fs:
            full = os.path.join(r, fn)
            rel = os.path.relpath(full, workdir).replace(os.sep, "/")
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                out[rel] = f.read()
    return out


def sync(place_id: str, workdir: str) -> None:
    """Persist the working dir's files back into the DB (source of truth)."""
    db.site_replace_all(place_id, _read_dir(workdir))


def commit(place_id: str, workdir: str, message: str) -> None:
    _git(workdir, "add", "-A")
    _git(workdir, "commit", "-m", message)


def has_changes(workdir: str) -> bool:
    return bool(_git(workdir, "status", "--porcelain").stdout.strip())


def rollback(workdir: str) -> None:
    _git(workdir, "reset", "--hard", "HEAD")
    _git(workdir, "clean", "-fd")


def undo(place_id: str) -> str:
    """Step the site back one git checkpoint in its cached workdir, then sync
    the reverted state into the DB."""
    workdir = _WORKDIRS.get(place_id)
    if not workdir or not os.path.isdir(os.path.join(workdir, ".git")):
        return "No history yet -- make an edit first, then undo."
    n = _git(workdir, "rev-list", "--count", "HEAD").stdout.strip()
    if not n.isdigit() or int(n) < 2:
        return "No earlier checkpoint to undo to."
    res = _git(workdir, "reset", "--hard", "HEAD~1")
    if res.returncode != 0:
        return f"Undo failed: {res.stderr.strip()[:160]}"
    sync(place_id, workdir)
    return "Reverted to the previous checkpoint."
