from __future__ import annotations

import json

import pytest

from app import release_cli


def test_release_cli_prints_json_and_fails_for_local_env(tmp_path, monkeypatch, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=local\n", encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        ["release_cli", "--env-file", str(env_file), "--json"],
    )

    with pytest.raises(SystemExit) as exc:
        release_cli.main()

    body = json.loads(capsys.readouterr().out)
    assert exc.value.code == 1
    assert body["deployable"] is False
    assert body["environment"] == "local"
    assert body["checks"]


def test_release_cli_succeeds_for_production_shape(tmp_path, monkeypatch, capsys) -> None:
    env_file = tmp_path / ".env.production"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "CORS_ORIGINS=https://documind.example.com",
                "DATABASE_URL=postgresql://user:pass@ep-example.neon.tech/documind",
                "REDIS_URL=rediss://default:token@settled-fox.upstash.io:6379/0",
                "CELERY_BROKER_URL=rediss://default:token@settled-fox.upstash.io:6379/1",
                "CELERY_RESULT_BACKEND=rediss://default:token@settled-fox.upstash.io:6379/2",
                "CACHE_ENABLED=true",
                "GENERATION_PROVIDER=gemini",
                "EMBEDDING_PROVIDER=gemini",
                "RERANKER_PROVIDER=cross-encoder",
                "EVALUATION_PROVIDER=ragas",
                "GEMINI_API_KEY=test-key",
                "DOCUMENT_STORAGE_PROVIDER=r2",
                "CLOUDFLARE_R2_ENDPOINT_URL=https://account.r2.cloudflarestorage.com",
                "CLOUDFLARE_R2_ACCESS_KEY_ID=access-key",
                "CLOUDFLARE_R2_SECRET_ACCESS_KEY=secret-key",
                "CLOUDFLARE_R2_BUCKET=documind",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "sys.argv",
        ["release_cli", "--env-file", str(env_file), "--json"],
    )

    with pytest.raises(SystemExit) as exc:
        release_cli.main()

    body = json.loads(capsys.readouterr().out)
    assert exc.value.code == 0
    assert body["deployable"] is True
