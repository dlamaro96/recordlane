# SPDX-License-Identifier: Apache-2.0
"""S3, Azure Blob, and GCS exchange through scoped pre-authorized object URLs."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from urllib.parse import urlparse

import httpx

PROVIDERS = {"s3", "azure_blob", "gcs"}


class ObjectExchange:
    def __init__(self, provider: str, allowed_hosts: set[str]):
        if provider not in PROVIDERS:
            raise ValueError("unsupported object provider")
        self.provider = provider
        self.allowed_hosts = allowed_hosts

    def _validate(self, url: str) -> None:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname not in self.allowed_hosts
            or parsed.username
            or parsed.password
        ):
            raise ValueError("object URL is outside the administrator allowlist")

    def download(self, url: str, client: httpx.Client | None = None) -> Iterator[bytes]:
        self._validate(url)
        owned = client is None
        active = client or httpx.Client(timeout=60.0, follow_redirects=False, verify=True)
        try:
            with active.stream("GET", url) as response:
                response.raise_for_status()
                yield from response.iter_bytes(64 * 1024)
        finally:
            if owned:
                active.close()

    def upload(
        self, url: str, chunks: Iterable[bytes], client: httpx.Client | None = None
    ) -> dict[str, str | int | None]:
        self._validate(url)
        owned = client is None
        active = client or httpx.Client(timeout=60.0, follow_redirects=False, verify=True)
        digest = hashlib.sha256()
        size = 0

        def body() -> Iterator[bytes]:
            nonlocal size
            for chunk in chunks:
                digest.update(chunk)
                size += len(chunk)
                yield chunk

        try:
            response = active.put(url, content=body())
            response.raise_for_status()
            return {
                "provider": self.provider,
                "bytes": size,
                "sha256": digest.hexdigest(),
                "etag": response.headers.get("etag"),
                "generation": response.headers.get("x-goog-generation"),
            }
        finally:
            if owned:
                active.close()
