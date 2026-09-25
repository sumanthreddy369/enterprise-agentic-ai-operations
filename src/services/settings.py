from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite+aiosqlite:///./operations.db"
    opensearch_url: str = "http://localhost:9200"
    opensearch_username: str | None = None
    opensearch_password: SecretStr | None = None
    opensearch_required: bool = False
    api_read_key: SecretStr | None = None
    api_write_key: SecretStr | None = None
    request_timeout: float = 10.0

    environment: Literal["local", "test", "production"] = "local"
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]"]
    max_request_bytes: int = Field(default=65536, ge=1024, le=1048576)
    requests_per_minute: int = Field(default=120, ge=1, le=10000)
    max_rate_limit_clients: int = Field(default=10000, ge=1, le=100000)
    max_concurrent_requests: int = Field(default=32, ge=1, le=1000)
    body_timeout_seconds: float = Field(default=5, gt=0, le=60)
    handler_timeout_seconds: float = Field(default=30, gt=0, le=300)

    @model_validator(mode="after")
    def security_configuration(self) -> Self:
        if self.environment == "production":
            raise ValueError(
                "Production requires enterprise identity and deployment review; "
                "local role keys are insufficient"
            )
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("Explicit allowed_hosts are required")
        if self.api_read_key and self.api_write_key:
            if self.api_read_key.get_secret_value() == self.api_write_key.get_secret_value():
                raise ValueError("Reader and writer credentials must differ")
        return self
