"""runtime.config: load config from env vars and platform detection."""
import os
import sys
from dataclasses import dataclass


_PLATFORM_MAP = {
    "linux": "linux",
    "darwin": "darwin",
    "win32": "win32",
}


@dataclass(frozen=True)
class Config:
    webui_url: str
    container: str
    entry_cmd: str
    platform: str
    debug: bool


def load_config() -> Config:
    platform = _PLATFORM_MAP.get(sys.platform, sys.platform)
    return Config(
        webui_url=os.environ.get("A0_WEBUI_URL", "http://localhost:5080"),
        container=os.environ.get("A0_CONTAINER", "agent-zero"),
        entry_cmd=os.environ.get("A0_CLI_CMD", "a0"),
        platform=platform,
        debug=os.environ.get("A0_DEBUG") == "1",
    )
