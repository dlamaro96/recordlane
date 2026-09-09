# SPDX-License-Identifier: Apache-2.0
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECORDLANE_", env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./recordlane.db"
    demo_mode: bool = False
    demo_allow_reverse_proxy: bool = False
    public_url: str = "http://127.0.0.1:8000"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:5173"])
    allowed_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost", "testserver", "api"])
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    session_secret: str | None = None
    master_key_file: str | None = None
    bootstrap_token_file: str | None = None
    outbound_enabled: bool = False
    publication_url: str | None = None
    webhook_secret: str | None = None
    max_import_records: int = 100_000
    max_request_bytes: int = 10_485_760

    @model_validator(mode="after")
    def secure_production(self) -> "Settings":
        if self.environment == "production":
            errors = []
            if self.demo_mode:
                errors.append("demo_mode must be disabled")
            if self.demo_allow_reverse_proxy:
                errors.append("demo reverse-proxy trust must be disabled")
            if not self.database_url.startswith("postgresql"):
                errors.append("PostgreSQL is required")
            if not self.oidc_issuer or not self.oidc_audience:
                errors.append("OIDC issuer and audience are required")
            if not self.session_secret or len(self.session_secret) < 32:
                errors.append("a 32+ character session secret is required")
            if not self.master_key_file:
                errors.append("an external master key file is required")
            if self.allowed_origins == ["*"]:
                errors.append("wildcard CORS is forbidden")
            if not self.allowed_hosts or "*" in self.allowed_hosts:
                errors.append("explicit trusted hosts are required")
            if self.outbound_enabled and (not self.publication_url or not self.publication_url.startswith("https://")):
                errors.append("production publication requires an HTTPS destination")
            if errors:
                raise ValueError("production preflight failed: " + "; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
