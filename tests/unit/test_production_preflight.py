# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import pytest
from pydantic import ValidationError
from recordlane.settings import Settings

def test_production_rejects_demo_and_missing_identity():
    with pytest.raises(ValidationError, match="demo_mode must be disabled"):
        Settings(environment="production",demo_mode=True)

def test_production_rejects_wildcard_hosts_and_insecure_publication(tmp_path: Path):
    key=tmp_path/"master.key"; key.write_bytes(b"x"*32)
    with pytest.raises(ValidationError, match="explicit trusted hosts"):
        Settings(environment="production",database_url="postgresql+psycopg://db/recordlane",oidc_issuer="https://id.example/realms/mdm",oidc_audience="recordlane-api",session_secret="s"*32,master_key_file=str(key),allowed_hosts=["*"],outbound_enabled=True,publication_url="http://sink.internal")

def test_secure_production_shape_passes_preflight(tmp_path: Path):
    key=tmp_path/"master.key"; key.write_bytes(b"x"*32)
    value=Settings(environment="production",demo_mode=False,database_url="postgresql+psycopg://db/recordlane",oidc_issuer="https://id.example/realms/mdm",oidc_audience="recordlane-api",session_secret="s"*32,master_key_file=str(key),allowed_origins=["https://mdm.example"],allowed_hosts=["mdm.example"],outbound_enabled=True,publication_url="https://sink.example/events")
    assert not value.demo_mode and value.publication_url.startswith("https://")
