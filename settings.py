"""
Typisierte Konfiguration via Pydantic BaseSettings.
Liest .env automatisch. Fehler werden beim Start sichtbar (nicht erst beim ersten Aufruf).

Verwendung:
    from settings import cfg
    print(cfg.OWNER_NAME)
"""
from __future__ import annotations
from pathlib import Path
from typing import Annotated
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AlfredSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Dashboard ────────────────────────────────────────────────────────────
    DASHBOARD_HOST: str = "0.0.0.0"
    DASHBOARD_PORT: int = 7779

    # ── LLM ──────────────────────────────────────────────────────────────────
    OLLAMA_MODEL: str = "qwen3.5:9b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_KEEP_ALIVE: str = "0"
    AGENT_MODEL_FAST: str = "qwen3.5:9b"
    AGENT_MODEL_STRONG: str = "qwen3.5:9b"
    # Kleines, schnelles Modell für Ja/Nein-Klassifikation (z.B. Voice-Adress-Check).
    # Auf einem 24-Fälle-Testset verglichen: qwen3.5:2b (12/24), qwen2.5:3b-instruct
    # (16/24, ~1.1s), qwen3.5:4b (21/24, ~3.1s), qwen3.5:9b (21/24, ~6.0s),
    # gemma4:e2b (21/24, ~2.8s) — gemma4:e2b gewählt: gleiche Genauigkeit wie die
    # größeren Qwen-Modelle, aber am schnellsten davon.
    ADDRESS_CHECK_MODEL: str = "gemma4:e2b"
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_CHAT_MODEL: str = "claude-haiku-4-5-20251001"
    # ── Background-LLM Routing ────────────────────────────────────────────────
    # Default: qwen3.5:9b für Memory, Review, Konsolidierung
    BG_DEFAULT_MODEL: str = ""          # leer = OLLAMA_MODEL
    # Reasoning-Spezialist für Briefings, Insights, Pattern-Detection
    BG_REASONING_MODEL: str = "deepseek-r1:14b"
    # Code-Spezialist für create_skill / Skill-Factory
    BG_CODE_MODEL: str = "qwen2.5-coder:7b"
    # Vision-Modell für Foto-Analyse (Mahlzeiten)
    VISION_MODEL: str = "qwen3-vl:8b"

    # ── Telegram ─────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_ALLOWED_IDS_RAW: str = Field("", alias="TELEGRAM_ALLOWED_IDS")

    # ── Besitzer ─────────────────────────────────────────────────────────────
    OWNER_NAME: str = ""
    OWNER_EMAIL: str = ""
    OWNER_TIMEZONE: str = "Europe/Berlin"

    # ── Datenquellen ─────────────────────────────────────────────────────────
    HEALTH_API_URL: str = ""
    CALENDAR_ICS_URLS: str = ""

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://localhost:5432/alfred"

    # ── Web Push (VAPID) ─────────────────────────────────────────────────────
    VAPID_PRIVATE_KEY_PATH: str = "data/vapid_private.pem"
    VAPID_PUBLIC_KEY: str = ""
    VAPID_CLAIM_EMAIL: str = ""

    # ── Search ───────────────────────────────────────────────────────────────
    BRAVE_API_KEY: str = ""

    # ── Google Calendar ───────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_CALENDAR_ID: str = "primary"

    # ── Thermal ──────────────────────────────────────────────────────────────
    THERMAL_TARGET_CELSIUS: float = 70.0
    THERMAL_MAX_CELSIUS: float = 85.0

    # ── Idle Loop ────────────────────────────────────────────────────────────
    IDLE_MIN_SLEEP_S: int = 2
    IDLE_MAX_SLEEP_S: int = 60
    IDLE_EVAL_AFTER_S: int = 600

    # ── Proaktiv ─────────────────────────────────────────────────────────────
    PROACTIVE_WAIT_AFTER_CONV: int = 600
    PROACTIVE_INTERVAL: int = 5400

    # ── Memory ───────────────────────────────────────────────────────────────
    LZG_EMBED_MODEL: str = "qwen3-embedding:0.6b"
    LZG_TOP_K: int = 5
    KZG_MAX_TURNS: int = 20

    # ── Computed ─────────────────────────────────────────────────────────────

    @property
    def TELEGRAM_ALLOWED_IDS(self) -> set[str]:
        raw = {s.strip() for s in self.TELEGRAM_ALLOWED_IDS_RAW.split(",") if s.strip()}
        if self.TELEGRAM_CHAT_ID:
            raw.add(self.TELEGRAM_CHAT_ID)
        return raw

    @property
    def VAPID_CLAIM_EMAIL_RESOLVED(self) -> str:
        return self.VAPID_CLAIM_EMAIL or self.OWNER_EMAIL or "admin@localhost"

    # ── Validation ───────────────────────────────────────────────────────────

    @field_validator("OWNER_NAME")
    @classmethod
    def warn_owner_name(cls, v: str) -> str:
        if not v:
            import logging
            logging.getLogger("alfred.settings").warning(
                "⚠️  OWNER_NAME nicht in .env gesetzt – bitte eintragen"
            )
        return v

    @field_validator("THERMAL_TARGET_CELSIUS", "THERMAL_MAX_CELSIUS")
    @classmethod
    def celsius_range(cls, v: float) -> float:
        if not (30.0 <= v <= 120.0):
            raise ValueError(f"Temperaturwert {v}°C außerhalb sinnvollem Bereich (30–120)")
        return v

    @model_validator(mode="after")
    def thermal_order(self) -> "AlfredSettings":
        if self.THERMAL_TARGET_CELSIUS >= self.THERMAL_MAX_CELSIUS:
            raise ValueError(
                f"THERMAL_TARGET_CELSIUS ({self.THERMAL_TARGET_CELSIUS}) muss kleiner als "
                f"THERMAL_MAX_CELSIUS ({self.THERMAL_MAX_CELSIUS}) sein"
            )
        return self


cfg = AlfredSettings()
