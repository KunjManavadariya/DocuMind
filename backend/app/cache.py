from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol
import hashlib
import json

from redis import Redis
from redis.exceptions import RedisError

from app.config import Settings


class JsonCache(Protocol):
    def get_json(self, key: str) -> Any | None:
        ...

    def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        ...

    def delete_prefix(self, prefix: str) -> int:
        ...


class NullJsonCache:
    def get_json(self, key: str) -> Any | None:
        return None

    def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        return None

    def delete_prefix(self, prefix: str) -> int:
        return 0


class RedisJsonCache:
    def __init__(self, redis_url: str) -> None:
        self.client = Redis.from_url(redis_url, decode_responses=True)

    def get_json(self, key: str) -> Any | None:
        try:
            raw = self.client.get(key)
        except RedisError:
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        try:
            self.client.set(key, json.dumps(value, sort_keys=True), ex=ttl_seconds)
        except (RedisError, TypeError, ValueError):
            return None

    def delete_prefix(self, prefix: str) -> int:
        deleted = 0
        try:
            for key in self.client.scan_iter(match=f"{prefix}*"):
                deleted += self.client.delete(key)
        except RedisError:
            return deleted
        return deleted


class InMemoryJsonCache:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    def get_json(self, key: str) -> Any | None:
        return self.items.get(key)

    def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        self.items[key] = value

    def delete_prefix(self, prefix: str) -> int:
        keys = [key for key in self.items if key.startswith(prefix)]
        for key in keys:
            del self.items[key]
        return len(keys)


def create_cache(settings: Settings) -> JsonCache:
    if not settings.cache_enabled:
        return NullJsonCache()
    return RedisJsonCache(settings.redis_url)


def stable_cache_key(namespace: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"
