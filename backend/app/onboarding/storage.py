"""Onboarding state in Cloud Storage (D-263, user option A, 10/6).

Cloud Run scales to zero and its disk is the container's, so uploads, releases, law packs and brand packs written under
ONBOARDING_DIR were gone after an idle period or a redeploy. With ONBOARDING_GCS_BUCKET set, the bucket is the source
of truth: every file onboarding persists is written to the local dir first and then through to
gs://<bucket>/onboarding/<path>; at start every JSON object (releases, packs, files.json, results) is read back into
the local dir, so the existing listings (glob) work after a cold start; an uploaded file is read back when it is first
needed. Approved artefacts are write-once: a different object under the same name is refused. Without a bucket
nothing changes (local disk only).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

PREFIX = "onboarding/"


class Immutable(RuntimeError):
    """A write-once object exists with other content."""


class Bucket(Protocol):
    def upload(self, key: str, data: bytes, *, create_only: bool) -> None: ...
    def download(self, key: str) -> bytes | None: ...
    def keys(self, prefix: str) -> list[str]: ...


class GcsBucket:
    def __init__(self, name: str, project: str | None = None) -> None:
        from google.cloud import storage

        self._bucket = storage.Client(project=project or None).bucket(name)

    def upload(self, key: str, data: bytes, *, create_only: bool) -> None:
        from google.api_core.exceptions import PreconditionFailed

        blob = self._bucket.blob(key)
        try:
            blob.upload_from_string(data, if_generation_match=0 if create_only else None)
        except PreconditionFailed:
            if blob.download_as_bytes() != data:
                raise Immutable(f"gs://{self._bucket.name}/{key} exists with other content") from None

    def download(self, key: str) -> bytes | None:
        from google.api_core.exceptions import NotFound

        try:
            return self._bucket.blob(key).download_as_bytes()
        except NotFound:
            return None

    def keys(self, prefix: str) -> list[str]:
        return [b.name for b in self._bucket.client.list_blobs(self._bucket, prefix=prefix)]


class MemoryBucket:
    """A bucket in memory (tests, local runs of the cloud path)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, key: str, data: bytes, *, create_only: bool) -> None:
        if create_only and key in self.objects and self.objects[key] != data:
            raise Immutable(f"{key} exists with other content")
        self.objects[key] = data

    def download(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))


class Mirror:
    def __init__(self, root: Path, bucket: Bucket) -> None:
        self.root = root.resolve()
        self.bucket = bucket

    def key(self, path: Path) -> str:
        return PREFIX + path.resolve().relative_to(self.root).as_posix()

    def push(self, path: Path, *, create_only: bool) -> None:
        self.bucket.upload(self.key(path), path.read_bytes(), create_only=create_only)

    def fetch(self, path: Path) -> bool:
        data = self.bucket.download(self.key(path))
        if data is None:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return True

    def hydrate(self) -> int:
        """Every JSON object into the local dir (releases, packs, files.json, results); uploads stay remote until
        needed."""
        n = 0
        for key in self.bucket.keys(PREFIX):
            if not key.endswith(".json"):
                continue
            path = self.root / key[len(PREFIX):]
            data = self.bucket.download(key)
            if data is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                n += 1
        return n


def bucket_for(name: str, project: str | None = None) -> Bucket:
    """The bucket by name (tests replace this to get a MemoryBucket)."""
    return GcsBucket(name, project)


_MIRRORS: dict[Path, Mirror] = {}


def configure(root: Path, bucket: Bucket | None) -> Mirror | None:
    """Mirror `root` to `bucket` (None: local only) and read the bucket's JSON state back."""
    root = root.resolve()
    if bucket is None:
        _MIRRORS.pop(root, None)
        return None
    m = _MIRRORS[root] = Mirror(root, bucket)
    log.info("onboarding state: %d objects read back from the bucket", m.hydrate())
    return m


def _mirror(path: Path) -> Mirror | None:
    p = path.resolve()
    return next((m for r, m in _MIRRORS.items() if p == r or r in p.parents), None)


def persisted(path: Path, *, create_only: bool = False) -> None:
    """Write a file just written under ONBOARDING_DIR through to the bucket (nothing without one)."""
    m = _mirror(path)
    if m is not None:
        m.push(path, create_only=create_only)


def ensure(path: Path) -> bool:
    """The file is on the local disk, read back from the bucket if needed."""
    if path.is_file():
        return True
    m = _mirror(path)
    return m is not None and m.fetch(path)
