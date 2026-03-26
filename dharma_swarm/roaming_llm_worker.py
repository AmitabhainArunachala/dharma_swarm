"""Dependency-light responder for roaming mailbox workers.

This worker is designed for remote embodiments such as OpenClaw/Kimi hosts:

- reads the current mailbox task from ``ROAMING_*`` environment variables
- calls an OpenAI-compatible chat-completions endpoint using only stdlib
- prints poller-compatible JSON to stdout

The worker prefers environment variables for credentials, then falls back to
``~/.openclaw/openclaw.json`` so mobile/cloud OpenClaw instances can self-start
without a separate secrets bootstrap.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest


DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_TOKENS = 1200
DEFAULT_TEMPERATURE = 0.2

OPENCLAW_CONFIG_ENV = "ROAMING_OPENCLAW_CONFIG"

PROVIDER_ENV_KEYS: dict[str, str] = {
    "moonshot": "MOONSHOT_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
}

PROVIDER_BASE_URLS: dict[str, str] = {
    "moonshot": "https://api.moonshot.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
}

PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "moonshot": "kimi-k2.5",
    "openrouter": "moonshotai/kimi-k2.5",
    "openai": "gpt-4.1-mini",
}


def _openclaw_config_path() -> Path:
    override = os.environ.get(OPENCLAW_CONFIG_ENV, "").strip()
    if override:
        return Path(override)
    return Path.home() / ".openclaw" / "openclaw.json"


def _load_openclaw_config() -> dict[str, Any]:
    path = _openclaw_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_configured_value(value: str, *, env: dict[str, str]) -> str:
    text = str(value or "")
    if text.startswith("${") and text.endswith("}") and len(text) > 3:
        return env.get(text[2:-1], "")
    return text


def _provider_entry(provider: str, *, config: dict[str, Any]) -> dict[str, Any]:
    return dict((((config.get("models") or {}).get("providers") or {}).get(provider) or {}))


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    base_url: str
    api_key: str


def _infer_provider(*, requested_provider: str, requested_model: str, env: dict[str, str], config: dict[str, Any]) -> str:
    if requested_provider:
        return requested_provider
    model_lower = requested_model.lower()
    if "moonshot" in model_lower or model_lower.startswith("kimi"):
        return "moonshot" if _resolve_api_key("moonshot", env=env, config=config) else "openrouter"
    for candidate in ("moonshot", "openrouter", "openai"):
        if _resolve_api_key(candidate, env=env, config=config):
            return candidate
    return "openrouter"


def _resolve_api_key(provider: str, *, env: dict[str, str], config: dict[str, Any]) -> str:
    env_key = PROVIDER_ENV_KEYS.get(provider, "")
    if env_key and env.get(env_key, "").strip():
        return env[env_key].strip()
    if provider == "openrouter" and env.get("OPENAI_API_KEY", "").startswith("sk-or-"):
        return env["OPENAI_API_KEY"].strip()
    entry = _provider_entry(provider, config=config)
    env_section = dict(config.get("env") or {})
    for candidate in (
        entry.get("apiKey"),
        env_section.get(env_key),
    ):
        resolved = _resolve_configured_value(str(candidate or ""), env=env)
        if resolved:
            return resolved
    return ""


def resolve_provider_config(
    *,
    provider: str = "",
    model: str = "",
    env: dict[str, str] | None = None,
    config: dict[str, Any] | None = None,
) -> ProviderConfig:
    env_map = dict(os.environ if env is None else env)
    cfg = _load_openclaw_config() if config is None else config
    chosen_provider = _infer_provider(
        requested_provider=provider.strip(),
        requested_model=model.strip(),
        env=env_map,
        config=cfg,
    )
    entry = _provider_entry(chosen_provider, config=cfg)
    base_url = (
        env_map.get(f"{chosen_provider.upper()}_BASE_URL", "").strip()
        or _resolve_configured_value(str(entry.get("baseUrl") or ""), env=env_map)
        or PROVIDER_BASE_URLS.get(chosen_provider, "")
    ).rstrip("/")
    api_key = _resolve_api_key(chosen_provider, env=env_map, config=cfg)
    chosen_model = (
        model.strip()
        or str(((entry.get("models") or [{}])[0]).get("id") or "")
        or PROVIDER_DEFAULT_MODELS.get(chosen_provider, "")
    )
    if not api_key:
        raise RuntimeError(f"No API key available for provider '{chosen_provider}'")
    if not base_url:
        raise RuntimeError(f"No base URL available for provider '{chosen_provider}'")
    if not chosen_model:
        raise RuntimeError(f"No model resolved for provider '{chosen_provider}'")
    return ProviderConfig(
        provider=chosen_provider,
        model=chosen_model,
        base_url=base_url,
        api_key=api_key,
    )


def _extract_message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts: list[str] = []
        for item in message:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    if isinstance(message, dict):
        content = message.get("content")
        return _extract_message_text(content)
    return str(message or "")


def render_task_messages(*, callsign: str, task_id: str, summary: str, body: str) -> list[dict[str, str]]:
    system_prompt = (
        f"You are {callsign}, a roaming dharma_swarm worker. "
        "Produce a direct, useful task response in plain text. "
        "Do not emit JSON, markdown code fences, or meta commentary about the transport."
    )
    user_prompt = (
        f"Task id: {task_id}\n"
        f"Summary: {summary}\n\n"
        "Task body:\n"
        f"{body}\n\n"
        "Return only the substantive answer to the task."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def request_chat_completion(
    *,
    config: ProviderConfig,
    messages: list[dict[str, str]],
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    payload = json.dumps(
        {
            "model": config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")
    req = urlrequest.Request(
        url=f"{config.base_url}/chat/completions",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Request failed: {exc.reason}") from exc

    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("No choices returned from provider")
    message = (choices[0] or {}).get("message")
    text = _extract_message_text(message).strip()
    if not text:
        raise RuntimeError("Provider returned empty content")
    return text


def run_worker(
    *,
    callsign: str,
    provider: str = "",
    model: str = "",
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    env: dict[str, str] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    env_map = dict(os.environ if env is None else env)
    task_id = env_map.get("ROAMING_TASK_ID", "").strip()
    summary = env_map.get("ROAMING_TASK_SUMMARY", "").strip()
    body = env_map.get("ROAMING_TASK_BODY", "").strip()
    if not task_id:
        raise RuntimeError("ROAMING_TASK_ID is not set")
    provider_config = resolve_provider_config(
        provider=provider,
        model=model,
        env=env_map,
        config=config,
    )
    response_text = request_chat_completion(
        config=provider_config,
        messages=render_task_messages(
            callsign=callsign,
            task_id=task_id,
            summary=summary,
            body=body,
        ),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return {
        "summary": f"{callsign} handled {task_id}",
        "body": response_text,
        "metadata": {
            "worker_callsign": callsign,
            "provider": provider_config.provider,
            "model": provider_config.model,
            "task_id": task_id,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM-backed roaming worker.")
    parser.add_argument("--callsign", required=True)
    parser.add_argument("--provider", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_worker(
        callsign=args.callsign,
        provider=args.provider,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
