# Contributing

Recordlane accepts contributions under Apache-2.0 with Developer Certificate
of Origin 1.1 sign-off. A sign-off must be supplied by the contributor; tooling
never forges one. Start with `./recordlane doctor`, follow the README development
commands, add behavior-focused tests, and update `REQUIREMENTS.yaml` evidence.

Architecture changes need an ADR. Schema changes need a forward migration and
restore-based recovery notes. Connector changes must update the capability
manifest and validation status. Pull requests must describe security impact,
data migration, tests, and UI screenshots where relevant.

