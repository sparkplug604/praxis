"""Base connector contracts for read-only Praxis Reach adapters."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TypeVar

from praxis.reach.manifests import QueryManifest
from praxis.reach.models import ClientCapsule


T = TypeVar("T")


@dataclass(frozen=True)
class ConnectorResult:
    provider: str
    summary: str
    metrics: dict[str, float | int | str] = field(default_factory=dict)
    source_links: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    row_count: int = 0
    storage_level: str = "aggregate_summary"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectorCheck:
    provider: str
    status: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConnectorDiscovery:
    provider: str
    status: str
    message: str = ""
    resources: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def retry_operation(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    delay_seconds: float = 0.25,
    label: str = "connector operation",
) -> T:
    """Retry transient connector operations without hiding the final error."""

    attempts = max(1, int(attempts))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(max(0.0, delay_seconds) * attempt)
    assert last_error is not None
    raise last_error


def iter_system_configs(capsule: ClientCapsule):
    for kind, value in capsule.systems.items():
        if isinstance(value, dict):
            config = dict(value)
            if config.get("provider"):
                yield str(kind), config
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("provider"):
                    yield str(kind), dict(item)


def system_config(capsule: ClientCapsule, provider: str) -> dict[str, Any]:
    for _kind, config in iter_system_configs(capsule):
        if config.get("provider") == provider:
            return config
    return {}


def env_value(config: dict[str, Any], key: str, fallback_env: str) -> tuple[str, str]:
    env_name = str(config.get(key) or fallback_env)
    return env_name, os.environ.get(env_name, "")


def env_value_with_fallback(config: dict[str, Any], key: str, fallback_key: str, fallback_env: str) -> tuple[str, str]:
    env_name, value = env_value(config, key, fallback_env)
    if value:
        return env_name, value
    alternate_env = str(config.get(fallback_key) or "")
    if not alternate_env:
        return env_name, value
    alternate_value = os.environ.get(alternate_env, "")
    return (alternate_env, alternate_value) if alternate_value else (env_name, value)


def config_or_env(config: dict[str, Any], value_key: str, env_key: str, fallback_env: str) -> tuple[str, str, str]:
    direct = str(config.get(value_key) or "")
    if direct:
        return direct, value_key, value_key
    env_name, value = env_value(config, env_key, fallback_env)
    return value, env_name, env_key


def config_or_env_with_fallback(
    config: dict[str, Any],
    value_key: str,
    env_key: str,
    fallback_key: str,
    fallback_env: str,
) -> tuple[str, str, str]:
    direct = str(config.get(value_key) or "")
    if direct:
        return direct, value_key, value_key
    value, source, source_key = config_or_env(config, value_key, env_key, fallback_env)
    if value:
        return value, source, source_key
    alternate_env = str(config.get(fallback_key) or "")
    if not alternate_env:
        return value, source, source_key
    alternate_value = os.environ.get(alternate_env, "")
    return (alternate_value, alternate_env, fallback_key) if alternate_value else (value, source, source_key)


class Connector(Protocol):
    provider: str
    connector_version: str

    def list_resources(self, capsule: ClientCapsule) -> list[str]:
        ...

    def capabilities(self) -> dict[str, Any]:
        ...

    def introspect_schema(self, capsule: ClientCapsule) -> dict[str, Any]:
        ...

    def check_setup(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorCheck:
        ...

    def discover_resources(self, capsule: ClientCapsule, *, live: bool = False) -> ConnectorDiscovery:
        ...

    def run_query(self, capsule: ClientCapsule, manifest: QueryManifest, params: dict[str, Any]) -> ConnectorResult:
        ...
