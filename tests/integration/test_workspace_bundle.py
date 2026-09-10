# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from recordlane.main import app


ADMIN = {"X-Recordlane-Role": "administrator", "X-Recordlane-User": "bundle.admin"}


def test_workspace_bundle_roundtrips_into_another_workspace(tmp_path):
    with TestClient(app) as client:
        exported = client.get("/api/v1/workspace-bundle", headers=ADMIN)
        assert exported.status_code == 200, exported.text
        bundle = exported.json()
        assert bundle["kind"] == "WorkspaceBundle"
        assert len(bundle["spec"]["domains"]) == 3
        assert len(bundle["spec"]["sources"]) == 3
        assert all(
            "password" not in str(source).lower()
            for source in bundle["spec"]["sources"]
        )
        bundle_path = tmp_path / "workspace-bundle.json"
        bundle_path.write_text(json.dumps(bundle))
        validation = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[2] / "scripts/validate_config.py"),
                str(bundle_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert validation.returncode == 0, validation.stderr
        assert "WorkspaceBundle" in validation.stdout

        workspace = client.post(
            "/api/v1/workspaces",
            headers=ADMIN,
            json={"slug": "bundle-target", "name": "Bundle Target"},
        )
        assert workspace.status_code == 201, workspace.text
        target = ADMIN | {"X-Recordlane-Workspace": "bundle-target"}
        imported = client.post(
            "/api/v1/workspace-bundle/import",
            headers=ADMIN,
            json={"bundle": bundle, "target_workspace": "bundle-target"},
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["domains"] == 3
        assert imported.json()["sources"] == 3
        assert len(client.get("/api/v1/domains", headers=target).json()) == 3
        assert len(client.get("/api/v1/sources", headers=target).json()) == 3

        second = client.post(
            "/api/v1/workspace-bundle/import",
            headers=ADMIN,
            json={"bundle": bundle, "target_workspace": "bundle-target"},
        )
        assert second.status_code == 200
        assert second.json()["unchanged"] >= 6


def test_source_configuration_rejects_inline_secret_and_unsafe_file_path():
    with TestClient(app) as client:
        operator = {
            "X-Recordlane-Role": "integration_operator",
            "X-Recordlane-User": "source.operator",
        }
        inline = client.post(
            "/api/v1/sources",
            headers=operator,
            json={
                "key": "unsafe-db",
                "name": "Unsafe database",
                "kind": "postgresql",
                "config": {"password": "must-not-be-stored"},
            },
        )
        assert inline.status_code == 422
        unsafe_path = client.post(
            "/api/v1/sources",
            headers=operator,
            json={
                "key": "unsafe-file",
                "name": "Unsafe file",
                "kind": "csv",
                "config": {"path": "/etc/passwd"},
            },
        )
        assert unsafe_path.status_code == 422
        safe = client.post(
            "/api/v1/sources",
            headers=operator,
            json={
                "key": "safe-file",
                "name": "Safe file",
                "kind": "csv",
                "config": {"path": "/data/supplier.csv", "encoding": "utf-8"},
                "capabilities": {"full_read": True, "deletions": "explicit"},
            },
        )
        assert safe.status_code == 201, safe.text
