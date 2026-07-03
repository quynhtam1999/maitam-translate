"""Object storage abstraction cho PDF gốc/đã dịch + glossary.

Chọn backend theo `settings.s3_bucket`:
- Rỗng -> `LocalStorage` (đọc/ghi dưới `storage/`, hành vi dev hiện tại, không đổi).
- Có `S3_BUCKET` -> `S3Storage` (S3-compatible: Cloudflare R2 / Supabase Storage / Backblaze B2).

Quy ước key: `uploads/{user}/{job}.pdf`, `outputs/{user}/{job}_vi.pdf`,
`glossary/{user}/glossary.csv`.
"""
from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class _StorageBackend:
    def put_bytes(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    def get_bytes(self, key: str) -> bytes | None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete_prefix(self, prefix: str) -> None:
        raise NotImplementedError

    def upload_file(self, key: str, local_path: Path) -> None:
        raise NotImplementedError

    def count_prefix(self, prefix: str) -> int:
        raise NotImplementedError

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        raise NotImplementedError
        yield  # pragma: no cover - làm cho hàm thành generator


class LocalStorage(_StorageBackend):
    """Đọc/ghi dưới `settings.storage_path` — giữ nguyên hành vi dev hiện tại."""

    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / key

    def put_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete_prefix(self, prefix: str) -> None:
        path = self._path(prefix)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)

    def upload_file(self, key: str, local_path: Path) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, path)

    def count_prefix(self, prefix: str) -> int:
        path = self._path(prefix)
        if not path.is_dir():
            return 0
        return sum(1 for p in path.iterdir() if p.is_file())

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        yield path


class S3Storage(_StorageBackend):
    """Client S3-compatible (boto3) — hoạt động với R2 / Supabase Storage / B2."""

    def __init__(
        self,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        region: str,
    ):
        import boto3

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            region_name=region or None,
        )

    def put_bytes(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def get_bytes(self, key: str) -> bytes | None:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.ClientError as exc:  # type: ignore[attr-defined]
            if _is_not_found(exc):
                return None
            raise
        return resp["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._client.exceptions.ClientError as exc:  # type: ignore[attr-defined]
            if _is_not_found(exc):
                return False
            raise

    def delete_prefix(self, prefix: str) -> None:
        paginator = self._client.get_paginator("list_objects_v2")
        keys = [
            {"Key": obj["Key"]}
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix)
            for obj in page.get("Contents", [])
        ]
        for i in range(0, len(keys), 1000):
            batch = keys[i : i + 1000]
            if batch:
                self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": batch})

    def upload_file(self, key: str, local_path: Path) -> None:
        self._client.upload_file(str(local_path), self._bucket, key)

    def count_prefix(self, prefix: str) -> int:
        paginator = self._client.get_paginator("list_objects_v2")
        return sum(
            len(page.get("Contents", []))
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix)
        )

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        data = self.get_bytes(key)
        if data is None:
            raise FileNotFoundError(key)
        tmp = tempfile.NamedTemporaryFile(suffix=Path(key).suffix, delete=False)
        try:
            tmp.write(data)
            tmp.close()
            yield Path(tmp.name)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


def _is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", None) or {}
    code = response.get("Error", {}).get("Code", "")
    return code in ("404", "NoSuchKey", "NotFound")


_backend: _StorageBackend | None = None


def init(settings) -> None:
    global _backend
    if settings.s3_bucket:
        _backend = S3Storage(
            endpoint_url=settings.s3_endpoint_url,
            bucket=settings.s3_bucket,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            region=settings.s3_region,
        )
    else:
        _backend = LocalStorage(settings.storage_path)


def get_storage() -> _StorageBackend:
    if _backend is None:
        raise RuntimeError("storage chưa được init()")
    return _backend


def put_bytes(key: str, data: bytes) -> None:
    get_storage().put_bytes(key, data)


def get_bytes(key: str) -> bytes | None:
    return get_storage().get_bytes(key)


def exists(key: str) -> bool:
    return get_storage().exists(key)


def delete_prefix(prefix: str) -> None:
    get_storage().delete_prefix(prefix)


def upload_file(key: str, local_path: Path) -> None:
    get_storage().upload_file(key, local_path)


def count_prefix(prefix: str) -> int:
    return get_storage().count_prefix(prefix)


def local_copy(key: str):
    return get_storage().local_copy(key)
