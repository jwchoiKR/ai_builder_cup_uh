"""Cloud Storage buckets for the rebuilt onboarding (product and regulation PDFs, reads, approvals, releases), and an
in-memory bucket for tests. Nothing is kept on the container's disk."""
from __future__ import annotations

import mimetypes
from functools import lru_cache
from typing import Protocol


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
            # upload_from_string defaults to text/plain, which made PDFs open as garbled text
            blob.upload_from_string(data, content_type=mimetypes.guess_type(key)[0] or "application/octet-stream",
                                    if_generation_match=0 if create_only else None)
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


@lru_cache
def bucket_for(name: str, project: str | None = None) -> Bucket:
    """The bucket by name, one client per process (tests replace this to get a MemoryBucket)."""
    return GcsBucket(name, project)
