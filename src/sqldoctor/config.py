"""
@file config.py
@description Central configuration parser and models for SQL Doctor (sqld)
@module sqldoctor/config
"""

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SandboxConfig(BaseModel):
    """Configuration for PostgreSQL sandbox container."""

    model_config = ConfigDict(extra="forbid")

    image: str = Field(default="sqldoctor-pg:17", description="Docker image name")
    pg_version: int = Field(default=17, description="PostgreSQL major version")
    port: int = Field(default=54329, description="Host port to bind sandbox Postgres")
    user: str = Field(default="postgres", description="PostgreSQL superuser")
    password: str = Field(default="postgres", description="PostgreSQL password")
    database: str = Field(default="postgres", description="Default database name")
    statement_timeout_ms: int = Field(
        default=10000, description="Per-statement execution timeout in milliseconds"
    )


class AdversaryConfig(BaseModel):
    """Configuration for adversarial test case generator."""

    model_config = ConfigDict(extra="forbid")

    seed: int = Field(default=20261123, description="Deterministic PRNG seed")
    max_rows_per_table: int = Field(
        default=3, description="Maximum rows in small-scope enumeration"
    )
    fuzz_datasets: int = Field(default=200, description="Number of fuzz datasets generated")
    enumeration_cap: int = Field(
        default=5000, description="Max generated permutations for enumeration"
    )


class AgentConfig(BaseModel):
    """Configuration for LLM proposal agent."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="openai-compatible", description="LLM provider protocol")
    model: str = Field(default="gemini-2.0-flash", description="Model identifier for proposals")
    api_key: str | None = Field(
        default=None, description="API key or None to read from environment"
    )
    base_url: str | None = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        description="Base URL for OpenAI-compatible client",
    )
    max_proposals: int = Field(default=6, description="Maximum candidate proposals per run")
    max_cost_usd: float = Field(default=1.00, description="Cost cap in USD per query diagnosis")
    use_tools: bool = Field(
        default=False, description="Use native OpenAI function tools calling if supported"
    )


class BenchConfig(BaseModel):
    """Configuration for performance benchmark harness."""

    model_config = ConfigDict(extra="forbid")

    scales: list[int] = Field(default=[1000, 100000], description="Data scale row counts")
    repeats: int = Field(default=7, description="Number of execution repeats per scale")
    interleave: bool = Field(
        default=True, description="Interleave execution of original and candidate"
    )


class AppConfig(BaseModel):
    """Top-level application configuration."""

    model_config = ConfigDict(extra="forbid")

    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    adversary: AdversaryConfig = Field(default_factory=AdversaryConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    bench: BenchConfig = Field(default_factory=BenchConfig)


def load_config(config_path: Path | str = "sqld.toml") -> AppConfig:
    """Load configuration from TOML file with environment variable overrides.

    Args:
        config_path: Path to sqld.toml configuration file.

    Returns:
        Validated AppConfig instance.
    """
    path = Path(config_path)
    data: dict[str, Any] = {}

    if path.is_file():
        with open(path, "rb") as f:
            data = tomllib.load(f)

    # Load .env if present and keys not already set
    env_file = Path(".env")
    if env_file.is_file():
        try:
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("\"'")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

    # Allow environment variable overrides
    sandbox_data = data.get("sandbox", {})
    if "SQLD_PG_PORT" in os.environ:
        sandbox_data["port"] = int(os.environ["SQLD_PG_PORT"])
    if "SQLD_PG_IMAGE" in os.environ:
        sandbox_data["image"] = os.environ["SQLD_PG_IMAGE"]
    if "SQLD_STATEMENT_TIMEOUT_MS" in os.environ:
        sandbox_data["statement_timeout_ms"] = int(os.environ["SQLD_STATEMENT_TIMEOUT_MS"])
    data["sandbox"] = sandbox_data

    adversary_data = data.get("adversary", {})
    if "SQLD_SEED" in os.environ:
        adversary_data["seed"] = int(os.environ["SQLD_SEED"])
    data["adversary"] = adversary_data

    agent_data = data.get("agent", {})
    if "SQLD_AGENT_MODEL" in os.environ:
        agent_data["model"] = os.environ["SQLD_AGENT_MODEL"]
    if "GEMINI_API_KEY" in os.environ and not agent_data.get("api_key"):
        agent_data["api_key"] = os.environ["GEMINI_API_KEY"]
    elif "OPENAI_API_KEY" in os.environ and not agent_data.get("api_key"):
        agent_data["api_key"] = os.environ["OPENAI_API_KEY"]
    data["agent"] = agent_data

    return AppConfig.model_validate(data)
