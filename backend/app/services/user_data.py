"""Purge all per-user data (jobs, cache, uploads, outputs, glossary).

Shared by the settings "clear my data" actions and by admin user deletion.
"""
import shutil
from pathlib import Path

from ..core import job_store
from ..core.config import get_settings
from .cache import SegmentCache


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def purge_jobs_and_files(user_id: str) -> tuple[int, int]:
    """Delete job rows for the user and their input/output PDF files.

    Returns (jobs_removed, files_removed).
    """
    storage_root = get_settings().storage_path
    rows = job_store.delete_jobs_for_user(user_id)
    removed_files = 0
    for row in rows:
        for raw_path in (row.get("input_path"), row.get("output_path")):
            if not raw_path:
                continue
            path = Path(raw_path)
            try:
                resolved = path.resolve()
                if not is_inside(resolved, storage_root):
                    continue
                if resolved.is_file():
                    resolved.unlink()
                    removed_files += 1
            except OSError:
                pass
    return len(rows), removed_files


def purge_user_data(user_id: str) -> None:
    """Remove everything scoped to a user: cache, jobs/files, uploads, outputs, glossary."""
    s = get_settings()
    SegmentCache(s.cache_dir / "segments.db", user_id=user_id).clear()
    purge_jobs_and_files(user_id)
    for base in (s.uploads_dir, s.outputs_dir, s.glossary_dir):
        directory = base / user_id
        if not directory.exists():
            continue
        if is_inside(directory.resolve(), base):
            shutil.rmtree(directory, ignore_errors=True)
