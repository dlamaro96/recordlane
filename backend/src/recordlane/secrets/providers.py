# SPDX-License-Identifier: Apache-2.0
"""Connector-secret resolution with encrypted local storage and Vault KV v2."""

from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from recordlane.models.tables import SecretReference
from recordlane.settings import Settings


class VaultKV2Provider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        if not settings.vault_url or not settings.vault_token_file:
            raise ValueError("Vault URL and token file are required")
        parsed = urlparse(settings.vault_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname not in set(settings.vault_allowed_hosts)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Vault endpoint is not in the administrator allowlist")
        addresses = {
            row[4][0]
            for row in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or 443,
                type=socket.SOCK_STREAM,
            )
        }
        if not addresses:
            raise ValueError("Vault endpoint did not resolve")
        if not settings.vault_allow_private:
            for value in addresses:
                address = ipaddress.ip_address(value)
                if (
                    address.is_loopback
                    or address.is_link_local
                    or address.is_private
                    or address.is_reserved
                    or address.is_multicast
                ):
                    raise ValueError("private Vault endpoint requires explicit authorization")
        self.settings = settings
        self._client = client

    def resolve(self, locator: str) -> str:
        path, separator, key = locator.partition("#")
        segments = path.split("/", 1)
        if not separator or not key or len(segments) != 2:
            raise ValueError("Vault locator must be mount/path#key")
        mount, secret_path = segments
        if not mount or not secret_path or ".." in path.split("/"):
            raise ValueError("invalid Vault secret path")
        token = Path(self.settings.vault_token_file).read_text().strip()
        if not token:
            raise ValueError("Vault token file is empty")
        url = (
            self.settings.vault_url.rstrip("/")
            + "/v1/"
            + quote(mount, safe="")
            + "/data/"
            + "/".join(quote(part, safe="") for part in secret_path.split("/"))
        )
        headers = {"X-Vault-Token": token}
        if self.settings.vault_namespace:
            headers["X-Vault-Namespace"] = self.settings.vault_namespace
        owned = self._client is None
        client = self._client or httpx.Client(timeout=10.0, follow_redirects=False, verify=True)
        try:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            value = response.json()["data"]["data"][key]
            if not isinstance(value, str):
                raise ValueError("Vault secret value must be a string")
            return value
        except (httpx.HTTPError, KeyError, TypeError) as exc:
            raise RuntimeError("Vault secret could not be resolved") from exc
        finally:
            if owned:
                client.close()


class SecretResolver:
    def __init__(self, db: Session, workspace_id: str, settings: Settings):
        self.db = db
        self.workspace_id = workspace_id
        self.settings = settings

    def _fernet(self) -> Fernet:
        if not self.settings.master_key_file:
            raise RuntimeError("master key file is not configured")
        return Fernet(Path(self.settings.master_key_file).read_bytes().strip())

    def encrypt(self, value: str) -> str:
        return self._fernet().encrypt(value.encode()).decode()

    def resolve(self, reference: str) -> str:
        if reference.startswith("file:"):
            raw = reference.removeprefix("file:")
            path = Path(raw).resolve(strict=True)
            root = Path("/run/recordlane").resolve()
            if path != root and root not in path.parents:
                raise ValueError("secret file is outside /run/recordlane")
            return path.read_text().strip()
        if reference.startswith("env:"):
            if self.settings.environment == "production":
                raise ValueError("environment secret references are forbidden in production")
            import os

            name = reference.removeprefix("env:")
            if not name.startswith("RECORDLANE_"):
                raise ValueError("environment secret reference is outside Recordlane scope")
            value = os.environ.get(name)
            if value is None:
                raise RuntimeError("environment secret is unavailable")
            return value
        if not reference.startswith("secret:"):
            raise ValueError("unsupported secret reference")
        name = reference.removeprefix("secret:")
        row = self.db.scalar(
            select(SecretReference).where(
                SecretReference.workspace_id == self.workspace_id,
                SecretReference.name == name,
            )
        )
        if not row:
            raise KeyError("secret reference does not exist")
        if row.provider == "encrypted_local":
            if not row.encrypted_value:
                raise RuntimeError("encrypted secret has no value")
            try:
                return self._fernet().decrypt(row.encrypted_value.encode()).decode()
            except InvalidToken as exc:
                raise RuntimeError("secret cannot be decrypted with the configured key") from exc
        if row.provider == "vault_kv2":
            return VaultKV2Provider(self.settings).resolve(row.locator)
        raise ValueError("unsupported secret provider")
