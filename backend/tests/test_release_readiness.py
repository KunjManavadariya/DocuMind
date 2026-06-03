from fastapi.testclient import TestClient

from app import main as main_module
from app.config import Settings
from app.release import evaluate_release_readiness, is_deployable


def test_local_settings_are_not_release_deployable() -> None:
    checks = evaluate_release_readiness(Settings())

    assert is_deployable(checks) is False
    failures = {check.name for check in checks if check.status == "fail"}
    assert "environment" in failures
    assert "database" in failures
    assert "object_storage" in failures
    assert "reranker" in failures
    assert "evaluation" in failures


def test_production_settings_are_release_deployable() -> None:
    checks = evaluate_release_readiness(
        Settings(
            app_env="production",
            cors_origins="https://documind.example.com",
            database_url="postgresql://user:pass@ep-example.neon.tech/documind",
            redis_url="rediss://default:token@settled-fox.upstash.io:6379/0",
            celery_broker_url="rediss://default:token@settled-fox.upstash.io:6379/1",
            celery_result_backend="rediss://default:token@settled-fox.upstash.io:6379/2",
            cache_enabled=True,
            generation_provider="gemini",
            embedding_provider="gemini",
            reranker_provider="cross-encoder",
            evaluation_provider="ragas",
            gemini_api_key="test-key",
            cloudflare_r2_endpoint_url="https://account.r2.cloudflarestorage.com",
            cloudflare_r2_access_key_id="access-key",
            cloudflare_r2_secret_access_key="secret-key",
            cloudflare_r2_bucket="documind",
            document_storage_provider="r2",
        )
    )

    assert is_deployable(checks) is True
    assert {check.status for check in checks} == {"ok"}


def test_release_readiness_rejects_template_secret_values() -> None:
    checks = evaluate_release_readiness(
        Settings(
            app_env="production",
            cors_origins="https://documind.example.com",
            database_url="postgresql://user:pass@ep-example.neon.tech/documind",
            redis_url="rediss://default:token@settled-fox.upstash.io:6379/0",
            celery_broker_url="rediss://default:token@settled-fox.upstash.io:6379/1",
            celery_result_backend="rediss://default:token@settled-fox.upstash.io:6379/2",
            cache_enabled=True,
            generation_provider="gemini",
            embedding_provider="gemini",
            reranker_provider="cross-encoder",
            evaluation_provider="ragas",
            gemini_api_key="replace_me",
            cloudflare_r2_endpoint_url="https://account.r2.cloudflarestorage.com",
            cloudflare_r2_access_key_id="replace_me",
            cloudflare_r2_secret_access_key="replace_me",
            cloudflare_r2_bucket="documind",
            document_storage_provider="r2",
        )
    )

    failures = {check.name for check in checks if check.status == "fail"}
    assert is_deployable(checks) is False
    assert "generation_provider" in failures
    assert "embedding_provider" in failures
    assert "evaluation" in failures
    assert "object_storage" in failures


def test_release_readiness_endpoint_reports_current_environment() -> None:
    client = TestClient(main_module.app)

    response = client.get("/release/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == main_module.settings.app_env
    assert isinstance(body["deployable"], bool)
    assert body["checks"]
