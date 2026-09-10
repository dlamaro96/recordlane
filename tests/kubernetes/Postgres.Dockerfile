# syntax=docker/dockerfile:1.7
# SPDX-License-Identifier: Apache-2.0
FROM postgres:17.6-bookworm
LABEL org.opencontainers.image.title="Recordlane acceptance PostgreSQL"
LABEL org.opencontainers.image.description="Single-platform wrapper used only by the disposable kind acceptance test"
USER postgres
