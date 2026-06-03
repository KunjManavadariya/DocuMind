from __future__ import annotations

import pytest

from app import db_cli


def test_db_cli_ensure_schema_uses_env_file(tmp_path, monkeypatch, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql://user:pass@ep-example.neon.tech/documind",
                "EMBEDDING_DIMENSION=512",
            ]
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_ensure_schema(database_url: str, *, embedding_dimension: int) -> None:
        captured["database_url"] = database_url
        captured["embedding_dimension"] = embedding_dimension

    monkeypatch.setattr(db_cli, "ensure_schema", fake_ensure_schema)
    monkeypatch.setattr(
        "sys.argv",
        ["db_cli", "ensure-schema", "--env-file", str(env_file)],
    )

    db_cli.main()

    assert captured == {
        "database_url": "postgresql://user:pass@ep-example.neon.tech/documind",
        "embedding_dimension": 512,
    }
    assert "schema ready: embedding_dimension=512" in capsys.readouterr().out


def test_db_cli_ensure_schema_accepts_dimension_override(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://user:pass@ep-example.neon.tech/documind",
        encoding="utf-8",
    )
    captured = {}

    def fake_ensure_schema(database_url: str, *, embedding_dimension: int) -> None:
        captured["embedding_dimension"] = embedding_dimension

    monkeypatch.setattr(db_cli, "ensure_schema", fake_ensure_schema)
    monkeypatch.setattr(
        "sys.argv",
        [
            "db_cli",
            "ensure-schema",
            "--env-file",
            str(env_file),
            "--embedding-dimension",
            "768",
        ],
    )

    db_cli.main()

    assert captured["embedding_dimension"] == 768
