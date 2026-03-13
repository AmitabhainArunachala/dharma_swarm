"""Model routing helpers for TUI model switching, strategy, and fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import time

INDIGO = "#9C7444"
VERDIGRIS = "#62725D"
OCHRE = "#A17A47"
BENGARA = "#8C5448"
WISTERIA = "#74677D"


@dataclass(frozen=True, slots=True)
class ModelTarget:
    alias: str
    provider_id: str
    model_id: str
    label: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


MODEL_TARGETS: tuple[ModelTarget, ...] = (
    ModelTarget(
        alias="sonnet-4.5",
        provider_id="claude",
        model_id="claude-sonnet-4-5",
        label="Claude Sonnet 4.5",
        aliases=("sonnet", "sonnet 4.5", "claude sonnet 4.5"),
    ),
    ModelTarget(
        alias="sonnet-4.6",
        provider_id="claude",
        model_id="claude-sonnet-4-6",
        label="Claude Sonnet 4.6",
        aliases=("sonnet 4.6", "claude sonnet 4.6"),
    ),
    ModelTarget(
        alias="opus-4.6",
        provider_id="claude",
        model_id="claude-opus-4-6",
        label="Claude Opus 4.6",
        aliases=("opus", "opus 4.6", "claude opus 4.6"),
    ),
    ModelTarget(
        alias="haiku-4.5",
        provider_id="claude",
        model_id="claude-haiku-4-5",
        label="Claude Haiku 4.5",
        aliases=("haiku", "haiku 4.5", "claude haiku 4.5"),
    ),
    ModelTarget(
        alias="codex-5.4",
        provider_id="codex",
        model_id="gpt-5.4",
        label="Codex 5.4",
        aliases=("codex", "codex 5.4", "gpt 5 codex"),
    ),
    ModelTarget(
        alias="gemini-3",
        provider_id="openrouter",
        model_id="google/gemini-2.5-pro",
        label="Gemini 3 class (via OpenRouter)",
        aliases=("gemini", "gemini 3", "google gemini 3"),
    ),
)


_DEFAULT_TARGET = MODEL_TARGETS[0]
ROUTING_STRATEGIES: tuple[str, ...] = ("responsive", "cost", "genius")
_FALLBACK_ORDER_BY_STRATEGY: dict[str, tuple[str, ...]] = {
    "responsive": (
        "sonnet-4.5",
        "haiku-4.5",
        "sonnet-4.6",
        "codex-5.4",
        "opus-4.6",
        "gemini-3",
    ),
    "cost": (
        "haiku-4.5",
        "gemini-3",
        "sonnet-4.5",
        "codex-5.4",
        "sonnet-4.6",
        "opus-4.6",
    ),
    "genius": (
        "opus-4.6",
        "sonnet-4.6",
        "codex-5.4",
        "gemini-3",
        "sonnet-4.5",
        "haiku-4.5",
    ),
}


def _norm(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9.\-/ ]+", " ", text)
    return " ".join(text.split())


def all_targets() -> list[ModelTarget]:
    return list(MODEL_TARGETS)


def route_key(provider_id: str, model_id: str) -> str:
    return f"{provider_id}:{model_id}"


def default_target() -> ModelTarget:
    return _DEFAULT_TARGET


def resolve_strategy(text: str | None) -> str | None:
    if not text:
        return None
    q = _norm(text)
    aliases = {
        "responsive": "responsive",
        "fast": "responsive",
        "speed": "responsive",
        "balanced": "responsive",
        "cost": "cost",
        "cheap": "cost",
        "budget": "cost",
        "frugal": "cost",
        "genius": "genius",
        "quality": "genius",
        "max": "genius",
        "best": "genius",
    }
    return aliases.get(q)


def resolve_model_target(text: str) -> ModelTarget | None:
    q = _norm(text)
    if not q:
        return None
    for t in MODEL_TARGETS:
        if q == _norm(t.alias):
            return t
        if q == _norm(t.model_id):
            return t
        for a in t.aliases:
            if q == _norm(a):
                return t
    # relaxed match: "switch to opus 4.6"
    for t in MODEL_TARGETS:
        keys = (_norm(t.alias), _norm(t.model_id), *(_norm(a) for a in t.aliases))
        if any(k and k in q for k in keys):
            return t
    return None


def target_for_route(provider_id: str, model_id: str) -> ModelTarget | None:
    for target in MODEL_TARGETS:
        if target.provider_id == provider_id and target.model_id == model_id:
            return target
    return None


def target_by_index(index: int) -> ModelTarget | None:
    if index < 1 or index > len(MODEL_TARGETS):
        return None
    return MODEL_TARGETS[index - 1]


def _cooldown_remaining_seconds(
    *,
    alias: str,
    cooldown_until: dict[str, float] | None,
    now_ts: float,
) -> int:
    if not cooldown_until:
        return 0
    until = cooldown_until.get(alias, 0.0)
    if until <= 0.0:
        return 0
    remain = int(until - now_ts)
    return remain if remain > 0 else 0


def format_model_list(
    current_provider: str,
    current_model: str,
    *,
    auto_fallback: bool = True,
    strategy: str = "responsive",
    preferred_key: str | None = None,
    available_keys: set[str] | None = None,
    cooldown_until: dict[str, float] | None = None,
    model_stats_by_alias: dict[str, dict[str, float | int | str]] | None = None,
    now_ts: float | None = None,
) -> str:
    strategy = resolve_strategy(strategy) or "responsive"
    now = now_ts if now_ts is not None else time.time()
    lines = ["Available models:", ""]
    for idx, t in enumerate(MODEL_TARGETS, start=1):
        active = (
            t.provider_id == current_provider and t.model_id == current_model
        )
        key = route_key(t.provider_id, t.model_id)
        preferred = preferred_key == key
        mark = f"[{VERDIGRIS}]*[/{VERDIGRIS}]" if active else " "
        remain = _cooldown_remaining_seconds(
            alias=t.alias,
            cooldown_until=cooldown_until,
            now_ts=now,
        )
        if remain > 0:
            readiness = f"[{OCHRE}]cooldown {remain}s[/{OCHRE}]"
        elif available_keys is not None and key not in available_keys:
            readiness = f"[{BENGARA}]blocked[/{BENGARA}]"
        else:
            readiness = f"[{VERDIGRIS}]ready[/{VERDIGRIS}]"
        stats_suffix = ""
        if model_stats_by_alias:
            stats = model_stats_by_alias.get(t.alias, {})
            ok = int(stats.get("successes", 0) or 0)
            bad = int(stats.get("failures", 0) or 0)
            latency = float(stats.get("ema_latency_ms", 0.0) or 0.0)
            if ok or bad:
                if latency > 0.0:
                    stats_suffix = f" [dim]ok:{ok} fail:{bad} ~{latency:.0f}ms[/dim]"
                else:
                    stats_suffix = f" [dim]ok:{ok} fail:{bad}[/dim]"
        pref = f" [{WISTERIA}](preferred)[/{WISTERIA}]" if preferred else ""
        lines.append(
            f"{mark} [bold]{idx:02d}[/bold] [{INDIGO}]{t.alias}[/{INDIGO}] -> {t.label}"
            f"{pref} {readiness} [dim]({key})[/dim]{stats_suffix}"
        )
    lines.append("")
    lines.append(
        f"Auto-fallback: {'ON' if auto_fallback else 'OFF'} | "
        f"Strategy: {strategy}"
    )
    lines.append(
        "Usage: /model list | /model status | /model set <alias|index> | "
        "/model auto <on|off|status|responsive|cost|genius>"
    )
    lines.append("Natural language: 'switch to opus 4.6' or 'switch to codex 5.4'")
    return "\n".join(lines)


def format_model_status(
    current_provider: str,
    current_model: str,
    auto_fallback: bool,
    *,
    strategy: str = "responsive",
    preferred: ModelTarget | None = None,
    cooldown_count: int = 0,
) -> str:
    t = resolve_model_target(current_model) or resolve_model_target(
        f"{current_provider} {current_model}"
    )
    label = t.label if t else current_model
    state = "ON" if auto_fallback else "OFF"
    resolved_strategy = resolve_strategy(strategy) or "responsive"
    preferred_label = preferred.label if preferred else "unset"
    return (
        f"Current model: [{INDIGO}]{label}[/{INDIGO}]\n"
        f"Provider/model: [dim]{current_provider}:{current_model}[/dim]\n"
        f"Auto-fallback: [{OCHRE}]{state}[/{OCHRE}]\n"
        f"Strategy: [{OCHRE}]{resolved_strategy}[/{OCHRE}]\n"
        f"Preferred model: [{INDIGO}]{preferred_label}[/{INDIGO}]\n"
        f"Cooling models: [{OCHRE}]{cooldown_count}[/{OCHRE}]"
    )


def fallback_chain(
    current_provider: str,
    current_model: str,
    *,
    strategy: str = "responsive",
    allowed_aliases: set[str] | None = None,
    cooldown_until: dict[str, float] | None = None,
    now_ts: float | None = None,
) -> list[ModelTarget]:
    current = target_for_route(current_provider, current_model)
    resolved_strategy = resolve_strategy(strategy) or "responsive"
    order = _FALLBACK_ORDER_BY_STRATEGY.get(
        resolved_strategy,
        _FALLBACK_ORDER_BY_STRATEGY["responsive"],
    )
    ordered: list[ModelTarget] = []
    by_alias = {t.alias: t for t in MODEL_TARGETS}
    now = now_ts if now_ts is not None else time.time()
    for alias in order:
        t = by_alias.get(alias)
        if t is None:
            continue
        if allowed_aliases is not None and t.alias not in allowed_aliases:
            continue
        if _cooldown_remaining_seconds(
            alias=t.alias,
            cooldown_until=cooldown_until,
            now_ts=now,
        ) > 0:
            continue
        if current and t.alias == current.alias:
            continue
        ordered.append(t)
    return ordered


def detect_inline_switch_intent(text: str) -> ModelTarget | None:
    q = _norm(text)
    if not q:
        return None
    patterns = (
        "switch to ",
        "change to ",
        "use ",
        "set model to ",
        "move to ",
        "switch model to ",
        "go to ",
    )
    if any(p in q for p in patterns):
        return resolve_model_target(q)
    return None
