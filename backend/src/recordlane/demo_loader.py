# SPDX-License-Identifier: Apache-2.0
import time

import httpx


def main() -> None:
    api = "http://api:8000/api/v1"
    source = "http://demo-source:8081/v1/suppliers"
    headers = {
        "X-Recordlane-Role": "integration_operator",
        "X-Recordlane-User": "demo.loader",
        "X-Recordlane-Workspace": "demo",
    }
    with httpx.Client(timeout=10.0) as client:
        for _attempt in range(30):
            try:
                if client.get("http://api:8000/health/ready").is_success:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Recordlane API did not become ready")
        cursor = None
        while True:
            page = (
                client.get(source, params={"cursor": cursor} if cursor is not None else {})
                .raise_for_status()
                .json()
            )
            records = [
                {
                    "local_id": item.pop("id"),
                    "version": str(item.pop("version")),
                    "values": item,
                    "verification": {"tax_id": True},
                }
                for item in page["items"]
            ]
            if records:
                response = client.post(
                    f"{api}/sources/vendor-http/ingest",
                    headers=headers,
                    json={
                        "domain": "supplier",
                        "records": records,
                        "run_id": "demo-http-snapshot-v1",
                        "extraction_mode": "full",
                        "page_cursor": str(cursor) if cursor is not None else None,
                        "next_cursor": (
                            str(page["next_cursor"]) if page["next_cursor"] is not None else None
                        ),
                        "snapshot_position": "synthetic-v1",
                        "complete_snapshot": page["snapshot_complete"],
                        "source_complete": page["snapshot_complete"],
                    },
                )
                response.raise_for_status()
            cursor = page["next_cursor"]
            if cursor is None:
                break


if __name__ == "__main__":
    main()
