# SPDX-License-Identifier: Apache-2.0
import ipaddress
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


@dataclass(frozen=True)
class HttpPage:
    items: list[dict[str, Any]]
    next_cursor: str | int | None
    complete: bool


class PaginatedHttpConnector:
    def __init__(
        self,
        base_url: str,
        allowed_hosts: set[str],
        timeout: float = 20.0,
        max_pages: int = 10_000,
        allow_private_networks: bool = False,
    ):
        parsed = urlparse(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.hostname not in allowed_hosts
            or parsed.username
            or parsed.password
        ):
            raise ValueError("destination is not in the administrator allowlist")
        if (
            parsed.scheme != "https"
            and parsed.hostname not in {"127.0.0.1", "localhost"}
            and not allow_private_networks
        ):
            raise ValueError("unencrypted remote connector destinations are forbidden")
        self.base_url = base_url
        self.allowed_hosts = allowed_hosts
        self.timeout = timeout
        self.max_pages = max_pages
        self.allow_private_networks = allow_private_networks
        self._validate_resolution(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        )

    def _validate_resolution(self, hostname: str, port: int) -> None:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
        if not addresses:
            raise ValueError("connector destination did not resolve")
        for value in addresses:
            address = ipaddress.ip_address(value)
            if address in ipaddress.ip_network(
                "169.254.169.254/32"
            ) or address in ipaddress.ip_network("fd00:ec2::254/128"):
                raise ValueError("cloud metadata destinations are always forbidden")
            unsafe = (
                address.is_loopback
                or address.is_link_local
                or address.is_private
                or address.is_reserved
                or address.is_multicast
            )
            if unsafe and not self.allow_private_networks:
                raise ValueError(
                    "private connector destination requires explicit administrator authorization"
                )

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.hostname not in self.allowed_hosts
            or parsed.username
            or parsed.password
        ):
            raise RuntimeError("connector URL escaped the administrator allowlist")
        self._validate_resolution(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        )

    def read(self, path: str, cursor: str | int | None = None, client: httpx.Client | None = None):
        owned = client is None
        client = client or httpx.Client(timeout=self.timeout, follow_redirects=False, verify=True)
        seen: set[str] = set()
        try:
            for _ in range(self.max_pages):
                url = urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))
                self._validate_url(url)
                marker = str(cursor)
                if marker in seen:
                    raise RuntimeError("pagination loop detected")
                seen.add(marker)
                response = client.get(url, params={"cursor": cursor} if cursor is not None else {})
                response.raise_for_status()
                payload = response.json()
                page = HttpPage(
                    payload["items"],
                    payload.get("next_cursor"),
                    bool(payload.get("snapshot_complete", payload.get("next_cursor") is None)),
                )
                yield page
                if page.next_cursor is None:
                    return
                cursor = page.next_cursor
            raise RuntimeError("maximum page count exceeded")
        finally:
            if owned:
                client.close()


class ODataConnector(PaginatedHttpConnector):
    def read_odata(self, path: str, client: httpx.Client | None = None):
        owned = client is None
        client = client or httpx.Client(timeout=self.timeout, follow_redirects=False, verify=True)
        url = urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))
        seen: set[str] = set()
        try:
            for _ in range(self.max_pages):
                if url in seen:
                    raise RuntimeError("OData nextLink loop detected")
                seen.add(url)
                self._validate_url(url)
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
                next_url = payload.get("@odata.nextLink")
                yield HttpPage(payload.get("value", []), next_url, next_url is None)
                if not next_url:
                    return
                url = next_url
            raise RuntimeError("maximum page count exceeded")
        finally:
            if owned:
                client.close()
