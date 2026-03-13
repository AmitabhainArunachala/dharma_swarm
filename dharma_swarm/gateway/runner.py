"""Gateway Runner — manages platform adapter lifecycle and cron ticks.

Starts all configured platform adapters, runs a background cron tick
thread, and routes incoming messages to the swarm for processing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from dharma_swarm.gateway.base import MessageEvent, PlatformAdapter

logger = logging.getLogger(__name__)

GATEWAY_CONFIG_PATH = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "gateway.yaml"

# Default cron tick interval (seconds)
CRON_TICK_INTERVAL = 60


def load_gateway_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load gateway configuration from YAML file.

    Example gateway.yaml:
        telegram:
          enabled: true
          token: ${TELEGRAM_BOT_TOKEN}
          allowed_users: []
        cron:
          enabled: true
          tick_interval: 60
    """
    path = config_path or GATEWAY_CONFIG_PATH
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        # Resolve environment variable references
        return _resolve_env_vars(config)
    except Exception:
        logger.exception("Failed to load gateway config from %s", path)
        return {}


def _resolve_env_vars(obj: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in config values."""
    if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
        env_name = obj[2:-1]
        return os.getenv(env_name, "")
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


class GatewayRunner:
    """Manages platform adapters and cron scheduling.

    Usage::

        runner = GatewayRunner()
        await runner.start()   # starts adapters + cron thread
        # ... runs until stopped
        await runner.stop()
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        message_handler: Any = None,
    ):
        self._config = config or load_gateway_config()
        self._adapters: dict[str, PlatformAdapter] = {}
        self._cron_thread: threading.Thread | None = None
        self._cron_stop = threading.Event()
        self._message_handler = message_handler
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def adapters(self) -> dict[str, PlatformAdapter]:
        return dict(self._adapters)

    async def start(self) -> None:
        """Start all configured adapters and the cron tick thread."""
        # Initialize platform adapters
        await self._start_adapters()

        # Start cron tick thread
        cron_config = self._config.get("cron", {})
        if cron_config.get("enabled", True):
            interval = cron_config.get("tick_interval", CRON_TICK_INTERVAL)
            self._start_cron_thread(interval)

        self._running = True
        logger.info("Gateway started with %d adapter(s)", len(self._adapters))

    async def stop(self) -> None:
        """Stop all adapters and the cron thread."""
        self._running = False

        # Stop cron thread
        if self._cron_thread is not None:
            self._cron_stop.set()
            self._cron_thread.join(timeout=10)
            self._cron_thread = None

        # Disconnect all adapters
        for name, adapter in self._adapters.items():
            try:
                await adapter.disconnect()
            except Exception:
                logger.exception("Error disconnecting %s", name)

        self._adapters.clear()
        logger.info("Gateway stopped")

    async def _start_adapters(self) -> None:
        """Initialize and connect configured platform adapters."""
        # Telegram
        tg_config = self._config.get("telegram", {})
        if tg_config.get("enabled", False):
            try:
                from dharma_swarm.gateway.telegram import TelegramAdapter
                adapter = TelegramAdapter(tg_config)
                if self._message_handler:
                    adapter.set_message_handler(self._message_handler)
                if await adapter.connect():
                    self._adapters["telegram"] = adapter
            except Exception:
                logger.exception("Failed to start Telegram adapter")

        # Future adapters (Discord, Slack, etc.) would be added here

    def _start_cron_thread(self, interval: int = CRON_TICK_INTERVAL) -> None:
        """Start the background cron tick thread."""
        self._cron_stop.clear()

        def _cron_loop() -> None:
            from dharma_swarm.cron_scheduler import tick
            logger.info("Cron tick thread started (interval=%ds)", interval)
            while not self._cron_stop.is_set():
                try:
                    tick(verbose=False)
                except Exception:
                    logger.exception("Cron tick error")
                self._cron_stop.wait(timeout=interval)
            logger.info("Cron tick thread stopped")

        self._cron_thread = threading.Thread(
            target=_cron_loop,
            name="dharma-cron-tick",
            daemon=True,
        )
        self._cron_thread.start()

    async def send_to_platform(
        self,
        platform: str,
        chat_id: str,
        text: str,
        thread_id: str | None = None,
    ) -> bool:
        """Send a message to a specific platform."""
        adapter = self._adapters.get(platform)
        if not adapter:
            logger.warning("Platform '%s' not connected", platform)
            return False
        result = await adapter.send(chat_id, text, thread_id=thread_id)
        return result.success
