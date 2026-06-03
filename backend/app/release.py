from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.config import Settings


@dataclass(frozen=True)
class ReleaseCheck:
    name: str
    status: str
    message: str


def evaluate_release_readiness(settings: Settings) -> list[ReleaseCheck]:
    return [
        _environment_check(settings),
        _cors_check(settings),
        _database_check(settings),
        _redis_check("redis", settings.redis_url),
        _redis_check("celery_broker", settings.celery_broker_url),
        _redis_check("celery_result_backend", settings.celery_result_backend),
        _cache_check(settings),
        _provider_check("generation_provider", settings.generation_provider, settings),
        _provider_check("embedding_provider", settings.embedding_provider, settings),
        _reranker_check(settings),
        _evaluation_check(settings),
        _r2_check(settings),
    ]


def is_deployable(checks: list[ReleaseCheck]) -> bool:
    return all(check.status == "ok" for check in checks)


def _environment_check(settings: Settings) -> ReleaseCheck:
    if settings.app_env.lower() in {"production", "prod"}:
        return ReleaseCheck("environment", "ok", "APP_ENV is production.")
    return ReleaseCheck(
        "environment",
        "fail",
        "APP_ENV must be production for a release deployment.",
    )


def _cors_check(settings: Settings) -> ReleaseCheck:
    origins = settings.cors_origin_list
    if not origins:
        return ReleaseCheck("cors", "fail", "At least one frontend origin must be configured.")
    local_origins = [origin for origin in origins if _is_local_url(origin)]
    if local_origins:
        return ReleaseCheck(
            "cors",
            "fail",
            "CORS_ORIGINS includes localhost-style origins; use the public HTTPS origin.",
        )
    return ReleaseCheck("cors", "ok", "CORS_ORIGINS points at public frontend origins.")


def _database_check(settings: Settings) -> ReleaseCheck:
    if _is_local_url(settings.database_url):
        return ReleaseCheck(
            "database",
            "fail",
            "DATABASE_URL points at a local or Docker Postgres host; use Neon for release.",
        )
    return ReleaseCheck("database", "ok", "DATABASE_URL is not local.")


def _redis_check(name: str, url: str) -> ReleaseCheck:
    if _is_local_url(url):
        return ReleaseCheck(
            name,
            "fail",
            f"{name.upper()} points at a local or Docker Redis host; use Upstash for release.",
        )
    return ReleaseCheck(name, "ok", f"{name.upper()} is not local.")


def _cache_check(settings: Settings) -> ReleaseCheck:
    if settings.cache_enabled:
        return ReleaseCheck("cache", "ok", "CACHE_ENABLED is true.")
    return ReleaseCheck("cache", "fail", "CACHE_ENABLED must be true for release.")


def _provider_check(name: str, provider: str, settings: Settings) -> ReleaseCheck:
    match provider:
        case "gemini":
            if _is_real_secret(settings.gemini_api_key):
                return ReleaseCheck(name, "ok", f"{name.upper()} uses Gemini with an API key.")
            return ReleaseCheck(name, "fail", f"{name.upper()}=gemini requires GEMINI_API_KEY.")
        case "local":
            return ReleaseCheck(
                name,
                "fail",
                f"{name.upper()}=local is for deterministic development, not release.",
            )
        case unsupported:
            return ReleaseCheck(name, "fail", f"Unsupported {name}: {unsupported}.")


def _reranker_check(settings: Settings) -> ReleaseCheck:
    if settings.reranker_provider == "cross-encoder":
        return ReleaseCheck(
            "reranker",
            "ok",
            f"RERANKER_PROVIDER uses {settings.reranker_model}.",
        )
    return ReleaseCheck(
        "reranker",
        "fail",
        "RERANKER_PROVIDER must be cross-encoder for release.",
    )


def _evaluation_check(settings: Settings) -> ReleaseCheck:
    if settings.evaluation_provider == "ragas" and _is_real_secret(settings.gemini_api_key):
        return ReleaseCheck(
            "evaluation",
            "ok",
            f"EVALUATION_PROVIDER uses RAGAS with {settings.ragas_llm_model}.",
        )
    if settings.evaluation_provider == "ragas":
        return ReleaseCheck(
            "evaluation",
            "fail",
            "EVALUATION_PROVIDER=ragas requires GEMINI_API_KEY.",
        )
    return ReleaseCheck(
        "evaluation",
        "fail",
        "EVALUATION_PROVIDER must be ragas for release.",
    )


def _r2_check(settings: Settings) -> ReleaseCheck:
    if settings.document_storage_provider != "r2":
        return ReleaseCheck(
            "object_storage",
            "fail",
            "DOCUMENT_STORAGE_PROVIDER must be r2 for release.",
        )

    missing = [
        key
        for key, value in {
            "CLOUDFLARE_R2_ENDPOINT_URL": settings.cloudflare_r2_endpoint_url,
            "CLOUDFLARE_R2_ACCESS_KEY_ID": settings.cloudflare_r2_access_key_id,
            "CLOUDFLARE_R2_SECRET_ACCESS_KEY": settings.cloudflare_r2_secret_access_key,
            "CLOUDFLARE_R2_BUCKET": settings.cloudflare_r2_bucket,
        }.items()
        if not _is_real_secret(value)
    ]
    if missing:
        return ReleaseCheck(
            "object_storage",
            "fail",
            "Missing Cloudflare R2 settings: " + ", ".join(missing) + ".",
        )
    return ReleaseCheck("object_storage", "ok", "Cloudflare R2 settings are present.")


def _is_local_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = parsed.hostname or value
    return hostname in {"localhost", "127.0.0.1", "::1", "postgres", "redis"}


def _is_real_secret(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip().lower()
    return normalized not in {
        "replace_me",
        "your_key",
        "your_google_ai_studio_key",
        "your_access_key",
        "your_secret_key",
        "your_r2_endpoint",
    }
