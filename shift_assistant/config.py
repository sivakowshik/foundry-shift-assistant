"""Settings from environment variables (or a local .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value or "<" in value:
        raise RuntimeError(f"Missing setting {name}. Copy .env.example to .env and fill it in.")
    return value


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    deployment: str
    staff_csv: str
    roster_csv: str


def data_paths() -> tuple[str, str]:
    return os.getenv("STAFF_CSV", "data/staff.csv"), os.getenv("ROSTER_CSV", "data/roster.csv")


def get_settings() -> Settings:
    staff_csv, roster_csv = data_paths()
    return Settings(
        base_url=_require("AZURE_OPENAI_BASE_URL"),
        api_key=_require("AZURE_OPENAI_API_KEY"),
        deployment=_require("AZURE_OPENAI_CHAT_DEPLOYMENT"),
        staff_csv=staff_csv,
        roster_csv=roster_csv,
    )


def make_client(s: Settings):
    """OpenAI SDK client pointed at the Azure OpenAI v1 endpoint (works for Microsoft Foundry resources)."""
    from openai import OpenAI

    return OpenAI(base_url=s.base_url, api_key=s.api_key)
