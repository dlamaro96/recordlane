# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import pytest
from pydantic import ValidationError
from recordlane.settings import Settings


def test_production_rejects_demo_and_missing_identity():
    with pytest.raises(ValidationError, match="demo_mode must be disabled"):
        Settings(environment="production", demo_mode=True)


def test_production_rejects_wildcard_hosts_and_insecure_publication(tmp_path: Path):
    key = tmp_path / "master.key"
    key.write_bytes(b"x" * 32)
    scim = tmp_path / "scim.token"
    scim.write_text("test-token")
    metrics = tmp_path / "metrics.token"
    metrics.write_text("test-token")
    with pytest.raises(ValidationError, match="explicit trusted hosts"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://db/recordlane",
            oidc_issuer="https://id.example/realms/mdm",
            oidc_audience="recordlane-api",
            oidc_client_id="recordlane",
            session_secret="s" * 32,
            master_key_file=str(key),
            scim_token_file=str(scim),
            metrics_token_file=str(metrics),
            allowed_hosts=["*"],
            outbound_enabled=True,
            publication_url="http://sink.internal",
        )


def test_secure_production_shape_passes_preflight(tmp_path: Path):
    key = tmp_path / "master.key"
    key.write_bytes(b"x" * 32)
    scim = tmp_path / "scim.token"
    scim.write_text("test-token")
    metrics = tmp_path / "metrics.token"
    metrics.write_text("test-token")
    value = Settings(
        environment="production",
        demo_mode=False,
        database_url="postgresql+psycopg://db/recordlane",
        oidc_issuer="https://id.example/realms/mdm",
        oidc_audience="recordlane-api",
        oidc_client_id="recordlane",
        session_secret="s" * 32,
        master_key_file=str(key),
        scim_token_file=str(scim),
        metrics_token_file=str(metrics),
        allowed_origins=["https://mdm.example"],
        allowed_hosts=["mdm.example"],
        outbound_enabled=True,
        publication_url="https://sink.example/events",
    )
    assert not value.demo_mode and value.publication_url.startswith("https://")
