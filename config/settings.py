"""Application-wide settings loaded from environment variables.

All values can be overridden by placing them in a `.env` file at the project
root.  Pydantic-settings handles parsing, validation, and type coercion.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Language-model provider configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    provider: Literal["openai", "anthropic"] = Field(
        default="openai", alias="LLM_PROVIDER"
    )

    # OpenAI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_agent_model: str = Field(
        default="gpt-4o-mini", alias="OPENAI_AGENT_MODEL"
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )

    # Anthropic
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_agent_model: str = Field(
        default="claude-sonnet-4-20250514", alias="ANTHROPIC_AGENT_MODEL"
    )

    @property
    def agent_model(self) -> str:
        """Return the active provider's agent model identifier."""
        return (
            self.openai_agent_model
            if self.provider == "openai"
            else self.anthropic_agent_model
        )

    @property
    def api_key(self) -> str:
        """Return the active provider's API key."""
        return (
            self.openai_api_key
            if self.provider == "openai"
            else self.anthropic_api_key
        )


class VectorStoreSettings(BaseSettings):
    """ChromaDB / vector store configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    persist_dir: str = Field(
        default="./data/chroma", alias="CHROMA_PERSIST_DIR"
    )
    collection_name: str = Field(
        default="fraud_knowledge_base", alias="CHROMA_COLLECTION_NAME"
    )
    similarity_threshold: float = Field(default=0.75)
    top_k: int = Field(default=5)
    embedding_batch_size: int = Field(default=64)


class LangSmithSettings(BaseSettings):
    """LangSmith tracing configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    enabled: bool = Field(default=False, alias="ENABLE_LANGSMITH_TRACING")
    api_key: str = Field(default="", alias="LANGCHAIN_API_KEY")
    project: str = Field(
        default="fraud-detection-prod", alias="LANGCHAIN_PROJECT"
    )
    tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")


class APISettings(BaseSettings):
    """FastAPI service configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(default="0.0.0.0", alias="APP_HOST")
    port: int = Field(default=8000, alias="APP_PORT")
    workers: int = Field(default=1, alias="APP_WORKERS")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    rate_limit_per_minute: int = Field(
        default=60, alias="RATE_LIMIT_PER_MINUTE"
    )
    rate_limit_burst: int = Field(default=10, alias="RATE_LIMIT_BURST")
    batch_max_size: int = Field(default=100)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


class LoggingSettings(BaseSettings):
    """Structured logging configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )
    format: Literal["json", "text"] = Field(
        default="json", alias="LOG_FORMAT"
    )
    log_dir: str = Field(default="./logs")


class FeatureFlags(BaseSettings):
    """Runtime feature flags."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    enable_reranking: bool = Field(default=False, alias="ENABLE_RERANKING")
    enable_prometheus: bool = Field(default=True, alias="ENABLE_PROMETHEUS")
    enable_langsmith: bool = Field(
        default=False, alias="ENABLE_LANGSMITH_TRACING"
    )


class Settings(BaseSettings):
    """Root settings object — compose all sub-settings here."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm: LLMSettings = Field(default_factory=LLMSettings)
    vector_store: VectorStoreSettings = Field(
        default_factory=VectorStoreSettings
    )
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)
    api: APISettings = Field(default_factory=APISettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    flags: FeatureFlags = Field(default_factory=FeatureFlags)

    # Agent loop guard
    max_agent_iterations: int = Field(default=10)

    @field_validator("llm", mode="before")
    @classmethod
    def _build_llm(cls, v: object) -> LLMSettings:
        if isinstance(v, LLMSettings):
            return v
        return LLMSettings()

    @field_validator("vector_store", mode="before")
    @classmethod
    def _build_vs(cls, v: object) -> VectorStoreSettings:
        if isinstance(v, VectorStoreSettings):
            return v
        return VectorStoreSettings()

    @field_validator("langsmith", mode="before")
    @classmethod
    def _build_ls(cls, v: object) -> LangSmithSettings:
        if isinstance(v, LangSmithSettings):
            return v
        return LangSmithSettings()

    @field_validator("api", mode="before")
    @classmethod
    def _build_api(cls, v: object) -> APISettings:
        if isinstance(v, APISettings):
            return v
        return APISettings()

    @field_validator("logging", mode="before")
    @classmethod
    def _build_log(cls, v: object) -> LoggingSettings:
        if isinstance(v, LoggingSettings):
            return v
        return LoggingSettings()

    @field_validator("flags", mode="before")
    @classmethod
    def _build_flags(cls, v: object) -> FeatureFlags:
        if isinstance(v, FeatureFlags):
            return v
        return FeatureFlags()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
