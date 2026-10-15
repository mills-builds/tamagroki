"""Configuration, read from environment variables (optionally from relay/.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader (KEY=VALUE lines). Real env vars win."""
    p = Path(os.getenv("TAMAGROKI_ENV_FILE", Path(__file__).resolve().parent.parent / ".env"))
    if not p.is_file():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Config:
    # Set XAI_API_KEY: export XAI_API_KEY=... in your shell or put it in relay/.env (gitignored).
    xai_api_key: str = ""
    xai_url: str = "wss://api.x.ai/v1/realtime?model=grok-voice-latest"
    xai_voice: str = "eve"
    bot_name: str = "Tamagroki"
    host: str = "0.0.0.0"
    port: int = 8765
    public_ws_url: str = ""          # what the OTA endpoint tells the device; auto if empty
    device_token: str = ""           # optional shared secret the device must present
    idle_close_s: float = 15.0       # end the conversation after this much quiet (only counts while waiting on the user)
    greet_on_wake: bool = False
    extra_instructions: str = ""
    enable_web_search: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv()
        return cls(
            xai_api_key=os.getenv("XAI_API_KEY", ""),
            xai_url=os.getenv("XAI_REALTIME_URL", cls.xai_url),
            xai_voice=os.getenv("XAI_VOICE", cls.xai_voice),
            bot_name=os.getenv("TAMAGROKI_NAME", cls.bot_name),
            host=os.getenv("RELAY_HOST", "0.0.0.0"),
            port=int(os.getenv("RELAY_PORT", "8765")),
            public_ws_url=os.getenv("RELAY_PUBLIC_WS_URL", ""),
            device_token=os.getenv("RELAY_DEVICE_TOKEN", ""),
            idle_close_s=_f("TAMAGROKI_IDLE_CLOSE_S", 15.0),
            greet_on_wake=os.getenv("TAMAGROKI_GREET_ON_WAKE", "0") == "1",
            extra_instructions=os.getenv("TAMAGROKI_EXTRA_INSTRUCTIONS", ""),
            enable_web_search=os.getenv("TAMAGROKI_WEB_SEARCH", "1") == "1",
        )

    def instructions(self) -> str:
        return (
            f"You are {self.bot_name}, a small lavender-purple desk cube with two black pill eyes, "
            "a friendly voice assistant powered by Grok. "
            "You talk out loud through a tiny speaker, so keep replies short, warm and conversational: "
            "one to three spoken sentences, no lists, no markdown, no URLs.\n"
            "Answer questions yourself; you have no access to the user's files or accounts.\n"
            "If the user interrupts you, stop and listen."
            + ("\n" + self.extra_instructions if self.extra_instructions else "")
        )
