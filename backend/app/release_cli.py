from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import dotenv_values

from app.config import Settings
from app.release import evaluate_release_readiness, is_deployable


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate DocuMind release readiness.")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file to validate. Defaults to .env.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    args = parser.parse_args()

    settings = _load_settings(args.env_file)
    checks = evaluate_release_readiness(settings)
    deployable = is_deployable(checks)

    payload = {
        "deployable": deployable,
        "environment": settings.app_env,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "message": check.message,
            }
            for check in checks
        ],
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"deployable: {str(deployable).lower()}")
        print(f"environment: {settings.app_env}")
        for check in checks:
            print(f"{check.status.upper():4} {check.name}: {check.message}")

    raise SystemExit(0 if deployable else 1)


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
