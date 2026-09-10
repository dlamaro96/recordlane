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
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "localhost", "testserver", "api"]
    )
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret_file: str | None = None
    oidc_discovery_url: str | None = None
    oidc_authorization_url: str | None = None
    oidc_token_url: str | None = None
    oidc_jwks_url: str | None = None
    oidc_end_session_url: str | None = None
    oidc_auto_provision: bool = False
    session_secret: str | None = None
    session_previous_secret: str | None = None
    session_ttl_seconds: int = 28_800
    scim_token_file: str | None = None
    master_key_file: str | None = None
    bootstrap_token_file: str | None = None
    outbound_enabled: bool = False
    publication_url: str | None = None
    publication_consumer_key: str = "default"
    publication_receipt_url: str | None = None
    webhook_secret: str | None = None
    max_import_records: int = 100_000
    max_request_bytes: int = 10_485_760
    otlp_endpoint: str | None = None
    telemetry_service_name: str = "recordlane-api"
    metrics_token_file: str | None = None
    ai_enabled: bool = False
    ai_provider: str = "local"
    ai_endpoint: str = "https://api.openai.com/v1/responses"
    ai_allowed_hosts: list[str] = Field(default_factory=lambda: ["api.openai.com"])
    ai_model: str | None = None
    ai_api_key_file: str | None = None
    ai_timeout_seconds: float = 20.0
    ai_max_input_chars: int = 20_000
    ai_max_output_tokens: int = 1_200
    vault_url: str | None = None
    vault_allowed_hosts: list[str] = Field(default_factory=list)
    vault_token_file: str | None = None
    vault_namespace: str | None = None
    vault_allow_private: bool = False

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
            if not self.oidc_issuer or not self.oidc_audience or not self.oidc_client_id:
                errors.append("OIDC issuer, audience, and browser client ID are required")
            if not self.session_secret or len(self.session_secret) < 32:
                errors.append("a 32+ character session secret is required")
            if not self.master_key_file:
                errors.append("an external master key file is required")
            if not self.scim_token_file:
                errors.append("an external SCIM bearer token file is required")
            if not self.metrics_token_file:
                errors.append("an external metrics bearer token file is required")
            if self.allowed_origins == ["*"]:
                errors.append("wildcard CORS is forbidden")
            if not self.allowed_hosts or "*" in self.allowed_hosts:
                errors.append("explicit trusted hosts are required")
            if self.outbound_enabled and (
                not self.publication_url or not self.publication_url.startswith("https://")
            ):
                errors.append("production publication requires an HTTPS destination")
            if self.ai_enabled and self.ai_provider not in {"local", "openai_responses"}:
                errors.append("AI provider must be local or openai_responses")
            if self.ai_enabled and self.ai_provider == "openai_responses":
                if not self.ai_model:
                    errors.append("hosted AI requires an explicit model")
                if not self.ai_api_key_file:
                    errors.append("hosted AI requires an API key file")
            if errors:
                raise ValueError("production preflight failed: " + "; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
