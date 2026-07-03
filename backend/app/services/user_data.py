"""Purge all per-user data (jobs, cache, uploads, outputs, glossary).

Shared by the settings "clear my data" actions and by admin user deletion.
"""
from ..core import job_store
from . import storage
from .cache import SegmentCache


def purge_jobs_and_files(user_id: str) -> tuple[int, int]:
    """Delete job rows for the user and their input/output PDF files.

    Returns (jobs_removed, files_removed).
    """
    rows = job_store.delete_jobs_for_user(user_id)
    removed_files = 0
    for row in rows:
        for key in (row.get("input_path"), row.get("output_path")):
            if not key:
                continue
            if storage.exists(key):
                storage.delete_prefix(key)
                removed_files += 1
    return len(rows), removed_files


def purge_user_data(user_id: str) -> None:
    """Remove everything scoped to a user: cache, jobs/files, uploads, outputs, glossary."""
    SegmentCache(user_id=user_id).clear()
    purge_jobs_and_files(user_id)
    for prefix in ("uploads", "outputs", "glossary"):
        storage.delete_prefix(f"{prefix}/{user_id}/")
