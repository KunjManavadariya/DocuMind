from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import dotenv_values

from app.config import Settings
from app.db import ensure_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="DocuMind database maintenance.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure = subparsers.add_parser("ensure-schema", help="Create pgvector schema.")
    ensure.add_argument("--env-file", default=".env")
    ensure.add_argument("--embedding-dimension", type=int, default=None)

    args = parser.parse_args()
    settings = _load_settings(args.env_file)

    match args.command:
        case "ensure-schema":
            dimension = args.embedding_dimension or settings.embedding_dimension
            ensure_schema(settings.database_url, embedding_dimension=dimension)
            print(f"schema ready: embedding_dimension={dimension}")


def _load_settings(env_file: str) -> Settings:
    path = Path(env_file)
    if not path.exists():
        return Settings()

    values = {
        key.lower(): value
        for key, value in dotenv_values(path).items()
        if value is not None
    }
    return Settings(**values)


if __name__ == "__main__":
    main()
