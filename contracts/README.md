# Recordlane contracts

These versioned files are canonical for the API, domain configuration, events, and connector capability manifests. SDK and ecosystem releases pin the platform release containing them. Breaking schema changes require a new major contract path; additive changes preserve the current path.

Regenerate `openapi/openapi.json` with:

```bash
PYTHONPATH=backend/src backend/.venv/bin/python scripts/export_openapi.py
```
