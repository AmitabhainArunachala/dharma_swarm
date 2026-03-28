"""Shadow transition classifier aligned to tgupj/tiny-router labels.

This remains shadow-only in DGC terms: the classifier enriches ingress state
with transition labels, but it does not override the main provider router.
When the Hugging Face checkpoint is available locally, this module uses the
real `tgupj/tiny-router` artifact; otherwise it falls back to deterministic
heuristics with the same output contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


_CORRECTION_MARKERS = (
    "actually",
    "instead",
    "rather",
    "i meant",
    "make that",
    "correction",
)
_CANCELLATION_MARKERS = (
    "cancel",
    "never mind",
    "nevermind",
    "ignore that",
    "drop it",
    "stop that",
)
_CONFIRMATION_MARKERS = (
    "yes",
    "correct",
    "that's right",
    "that is right",
    "exactly",
)
_CLOSURE_MARKERS = (
    "thanks",
    "thank you",
    "all set",
    "done",
    "perfect",
    "sounds good",
)
_FOLLOW_UP_MARKERS = (
    "also",
    "one more thing",
    "follow up",
    "what about",
    "can you also",
    "next",
)
_ACT_MARKERS = (
    "set ",
    "schedule",
    "update",
    "change",
    "move",
    "send",
    "create",
    "delete",
    "fix",
    "implement",
    "remind",
)
_REVIEW_MARKERS = (
    "review",
    "should we",
    "thoughts",
    "does this make sense",
    "can you assess",
    "evaluate",
    "compare",
    "analyze",
)
_REMEMBER_MARKERS = (
    "remember",
    "i prefer",
    "always",
    "never",
    "important",
    "policy",
    "my name is",
)
_EPHEMERAL_MARKERS = (
    "thanks",
    "thank you",
    "hello",
    "hi",
    "bye",
)
_USEFUL_MARKERS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "today",
    "tomorrow",
    "reminder",
    "meeting",
    "calendar",
)
_HIGH_URGENCY_MARKERS = (
    "urgent",
    "asap",
    "immediately",
    "right now",
    "now",
    "blocking",
    "outage",
    "prod",
)

_TINY_ROUTER_REPO_ID = "tgupj/tiny-router"
_TINY_ROUTER_BACKEND_ENV = "DGC_TINY_ROUTER_BACKEND"
_TINY_ROUTER_SOURCE = "hf-tgupj-tiny-router-shadow"
_TINY_ROUTER_FILES = (
    "added_tokens.json",
    "model.pt",
    "model_config.json",
    "special_tokens_map.json",
    "spm.model",
    "temperature_scaling.json",
    "tokenizer_config.json",
)

_ACTION_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("schedule", ("schedule", "scheduled", "calendar", "meeting", "reminder")),
    ("cancel", ("cancel", "cancelled", "canceled", "abort", "stop", "drop")),
    ("complete", ("complete", "completed", "done", "finish", "finished")),
    ("notify", ("notify", "notification", "alert", "ping", "slack")),
    ("send", ("send", "sent", "email", "message", "dm", "post")),
    ("update", ("update", "updated", "change", "changed", "edit", "modify")),
    ("create", ("create", "created", "add", "added", "new", "draft")),
    ("search", ("search", "searched", "find", "lookup", "look up", "browse")),
    ("store", ("store", "stored", "save", "saved", "remember", "persist")),
    ("route", ("route", "routed", "delegate", "delegated", "assign")),
    ("clarify", ("clarify", "clarified", "question", "ask", "explain")),
    ("dismissed", ("dismiss", "dismissed", "ignore", "ignored")),
)

_OUTCOME_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("success", ("success", "succeeded", "done", "complete", "completed")),
    ("pending", ("pending", "queued", "waiting", "in_progress", "in progress")),
    ("failed", ("fail", "failed", "error", "errored", "broken")),
    ("cancelled", ("cancel", "cancelled", "canceled", "aborted", "stopped")),
)


@dataclass(frozen=True, slots=True)
class TinyRouterHeadPrediction:
    label: str
    confidence: float


@dataclass(frozen=True, slots=True)
class TinyRouterShadowInput:
    current_text: str
    previous_text: str | None = None
    previous_action: str | None = None
    previous_outcome: str | None = None
    recency_seconds: float | int | None = None


@dataclass(frozen=True, slots=True)
class TinyRouterShadowSignal:
    relation_to_previous: TinyRouterHeadPrediction
    actionability: TinyRouterHeadPrediction
    retention: TinyRouterHeadPrediction
    urgency: TinyRouterHeadPrediction
    overall_confidence: float
    source: str = "heuristic-shadow"
    shadow_mode: bool = True


@dataclass(frozen=True, slots=True)
class _TinyRouterCheckpointArtifacts:
    repo_dir: Path
    model_config: Mapping[str, Any]
    temperature_scaling: Mapping[str, float]


class _TinyRouterCheckpointRuntime:
    """Lazy loader for the real tgupj/tiny-router checkpoint."""

    def __init__(
        self,
        *,
        artifacts: _TinyRouterCheckpointArtifacts,
        device: str = "cpu",
    ) -> None:
        import torch
        from transformers import AutoConfig, AutoModel, AutoTokenizer

        model_config = dict(artifacts.model_config)
        encoder_config = AutoConfig.from_pretrained(model_config["encoder_name"])
        encoder = AutoModel.from_config(encoder_config)
        tokenizer = AutoTokenizer.from_pretrained(
            str(artifacts.repo_dir),
            use_fast=False,
            local_files_only=True,
        )

        hidden_size = int(encoder.config.hidden_size)
        action_vocab = tuple(str(item) for item in model_config.get("action_vocab", ()))
        outcome_vocab = tuple(str(item) for item in model_config.get("outcome_vocab", ()))
        label_maps = {
            key: tuple(str(item) for item in values)
            for key, values in dict(model_config.get("label_maps", {})).items()
        }
        structured_hidden_dim = int(model_config.get("structured_hidden_dim", 32))
        recency_embed_dim = int(model_config.get("recency_embed_dim", 8))
        dependency_hidden_dim = int(model_config.get("dependency_hidden_dim", 32))

        class _CheckpointModel(torch.nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.encoder = encoder
                self.attention_pool = torch.nn.Linear(hidden_size, 1)
                self.action_embedding = torch.nn.Embedding(
                    len(action_vocab),
                    structured_hidden_dim,
                )
                self.outcome_embedding = torch.nn.Embedding(
                    len(outcome_vocab),
                    structured_hidden_dim,
                )
                self.recency_projection = torch.nn.Sequential(
                    torch.nn.Linear(1, recency_embed_dim),
                    torch.nn.GELU(),
                    torch.nn.Linear(recency_embed_dim, recency_embed_dim),
                )
                self.dependency_projections = torch.nn.ModuleDict(
                    {
                        "actionability": torch.nn.Sequential(
                            torch.nn.Linear(
                                len(label_maps["relation_to_previous"]),
                                dependency_hidden_dim,
                            ),
                            torch.nn.GELU(),
                        ),
                        "retention": torch.nn.Sequential(
                            torch.nn.Linear(
                                len(label_maps["relation_to_previous"])
                                + len(label_maps["actionability"]),
                                dependency_hidden_dim,
                            ),
                            torch.nn.GELU(),
                        ),
                        "urgency": torch.nn.Sequential(
                            torch.nn.Linear(
                                len(label_maps["relation_to_previous"])
                                + len(label_maps["actionability"])
                                + len(label_maps["retention"]),
                                dependency_hidden_dim,
                            ),
                            torch.nn.GELU(),
                        ),
                    }
                )
                base_dim = hidden_size + (structured_hidden_dim * 2) + recency_embed_dim
                self.heads = torch.nn.ModuleDict(
                    {
                        "relation_to_previous": torch.nn.Linear(
                            base_dim,
                            len(label_maps["relation_to_previous"]),
                        ),
                        "actionability": torch.nn.Linear(
                            base_dim + dependency_hidden_dim,
                            len(label_maps["actionability"]),
                        ),
                        "retention": torch.nn.Linear(
                            base_dim + dependency_hidden_dim,
                            len(label_maps["retention"]),
                        ),
                        "urgency": torch.nn.Linear(
                            base_dim + dependency_hidden_dim,
                            len(label_maps["urgency"]),
                        ),
                    }
                )

            def forward(
                self,
                *,
                input_ids: torch.Tensor,
                attention_mask: torch.Tensor | None,
                token_type_ids: torch.Tensor | None,
                action_ids: torch.Tensor,
                outcome_ids: torch.Tensor,
                recency_values: torch.Tensor,
            ) -> dict[str, torch.Tensor]:
                outputs = self.encoder(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids,
                )
                hidden = outputs.last_hidden_state
                scores = self.attention_pool(hidden).squeeze(-1)
                if attention_mask is not None:
                    scores = scores.masked_fill(attention_mask == 0, -1.0e9)
                weights = torch.softmax(scores, dim=-1).unsqueeze(-1)
                pooled = torch.sum(hidden * weights, dim=1)

                action_emb = self.action_embedding(action_ids)
                outcome_emb = self.outcome_embedding(outcome_ids)
                recency_emb = self.recency_projection(recency_values)
                base = torch.cat((pooled, action_emb, outcome_emb, recency_emb), dim=-1)

                relation_logits = self.heads["relation_to_previous"](base)
                relation_probs = torch.softmax(relation_logits, dim=-1)

                action_dep = self.dependency_projections["actionability"](relation_probs)
                action_logits = self.heads["actionability"](
                    torch.cat((base, action_dep), dim=-1)
                )
                action_probs = torch.softmax(action_logits, dim=-1)

                retention_dep = self.dependency_projections["retention"](
                    torch.cat((relation_probs, action_probs), dim=-1)
                )
                retention_logits = self.heads["retention"](
                    torch.cat((base, retention_dep), dim=-1)
                )
                retention_probs = torch.softmax(retention_logits, dim=-1)

                urgency_dep = self.dependency_projections["urgency"](
                    torch.cat((relation_probs, action_probs, retention_probs), dim=-1)
                )
                urgency_logits = self.heads["urgency"](
                    torch.cat((base, urgency_dep), dim=-1)
                )
                return {
                    "relation_to_previous": relation_logits,
                    "actionability": action_logits,
                    "retention": retention_logits,
                    "urgency": urgency_logits,
                }

        state_path = artifacts.repo_dir / "model.pt"
        state_dict = torch.load(str(state_path), map_location="cpu", weights_only=False)
        model = _CheckpointModel()
        model.load_state_dict(state_dict, strict=True)
        model.eval()

        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model.to(torch.device(device))
        self._device = torch.device(device)
        self._label_maps = label_maps
        self._action_vocab = action_vocab
        self._outcome_vocab = outcome_vocab
        self._max_length = int(model_config.get("max_length", 128))
        self._recency_max = float(model_config.get("recency_max", 3600.0))
        self._temperature_scaling = {
            str(key): float(value)
            for key, value in dict(artifacts.temperature_scaling).items()
        }

    def infer(self, payload: TinyRouterShadowInput) -> TinyRouterShadowSignal:
        torch = self._torch
        encoded = self._tokenizer(
            payload.current_text,
            payload.previous_text or None,
            truncation=True,
            max_length=self._max_length,
            return_tensors="pt",
        )
        inputs = {
            key: value.to(self._device)
            for key, value in encoded.items()
            if key in {"input_ids", "attention_mask", "token_type_ids"}
        }
        inputs["action_ids"] = torch.tensor(
            [self._action_id(payload.previous_action)],
            dtype=torch.long,
            device=self._device,
        )
        inputs["outcome_ids"] = torch.tensor(
            [self._outcome_id(payload.previous_outcome)],
            dtype=torch.long,
            device=self._device,
        )
        inputs["recency_values"] = torch.tensor(
            [[self._recency_value(payload.recency_seconds)]],
            dtype=torch.float32,
            device=self._device,
        )

        with torch.no_grad():
            logits = self._model(**inputs)

        predictions = {
            head: self._predict_head(
                head,
                logits[head][0],
            )
            for head in (
                "relation_to_previous",
                "actionability",
                "retention",
                "urgency",
            )
        }
        overall = round(
            sum(prediction.confidence for prediction in predictions.values()) / 4.0,
            4,
        )
        return TinyRouterShadowSignal(
            relation_to_previous=predictions["relation_to_previous"],
            actionability=predictions["actionability"],
            retention=predictions["retention"],
            urgency=predictions["urgency"],
            overall_confidence=overall,
            source=_TINY_ROUTER_SOURCE,
        )

    def _predict_head(
        self,
        head: str,
        logits: Any,
    ) -> TinyRouterHeadPrediction:
        torch = self._torch
        temperature = max(self._temperature_scaling.get(head, 1.0), 1.0e-6)
        calibrated = torch.softmax(logits / temperature, dim=-1)
        label_idx = int(torch.argmax(calibrated).item())
        label = self._label_maps[head][label_idx]
        confidence = round(float(calibrated[label_idx].item()), 4)
        return TinyRouterHeadPrediction(label=label, confidence=confidence)

    def _action_id(self, previous_action: str | None) -> int:
        canonical = _canonicalize_previous_action(previous_action)
        try:
            return self._action_vocab.index(canonical)
        except ValueError:
            return self._action_vocab.index("other")

    def _outcome_id(self, previous_outcome: str | None) -> int:
        canonical = _canonicalize_previous_outcome(previous_outcome)
        try:
            return self._outcome_vocab.index(canonical)
        except ValueError:
            return self._outcome_vocab.index("unknown")

    def _recency_value(self, recency_seconds: float | int | None) -> float:
        value = float(recency_seconds or 0.0)
        value = min(max(value, 0.0), self._recency_max)
        return math.log1p(value)


def _normalize(text: str | None) -> str:
    return " ".join((text or "").strip().lower().split())


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _requested_backend() -> str:
    return os.environ.get(_TINY_ROUTER_BACKEND_ENV, "auto").strip().lower() or "auto"


def _canonicalize_previous_action(previous_action: str | None) -> str:
    normalized = _normalize(previous_action)
    if not normalized:
        return "none"
    for label, markers in _ACTION_HINTS:
        if _contains_any(normalized, markers):
            return label
    return "other"


def _canonicalize_previous_outcome(previous_outcome: str | None) -> str:
    normalized = _normalize(previous_outcome)
    if not normalized:
        return "unknown"
    for label, markers in _OUTCOME_HINTS:
        if _contains_any(normalized, markers):
            return label
    return "unknown"


def _load_tiny_router_artifacts(*, allow_download: bool) -> _TinyRouterCheckpointArtifacts | None:
    from huggingface_hub import snapshot_download

    try:
        repo_dir = Path(
            snapshot_download(
                repo_id=_TINY_ROUTER_REPO_ID,
                allow_patterns=list(_TINY_ROUTER_FILES),
                local_files_only=not allow_download,
            )
        )
    except Exception:
        return None

    model_config_path = repo_dir / "model_config.json"
    temperature_path = repo_dir / "temperature_scaling.json"
    if not model_config_path.exists() or not temperature_path.exists():
        return None
    model_config = json.loads(model_config_path.read_text(encoding="utf-8"))
    temperature_doc = json.loads(temperature_path.read_text(encoding="utf-8"))
    per_head = dict(temperature_doc.get("per_head", {}))
    return _TinyRouterCheckpointArtifacts(
        repo_dir=repo_dir,
        model_config=model_config,
        temperature_scaling=per_head,
    )


@lru_cache(maxsize=4)
def _materialize_tiny_router_checkpoint_runtime(
    repo_dir: str,
    model_config_json: str,
    temperature_scaling_json: str,
) -> _TinyRouterCheckpointRuntime | None:
    artifacts = _TinyRouterCheckpointArtifacts(
        repo_dir=Path(repo_dir),
        model_config=json.loads(model_config_json),
        temperature_scaling=json.loads(temperature_scaling_json),
    )
    try:
        return _TinyRouterCheckpointRuntime(artifacts=artifacts)
    except Exception:
        return None


def _load_tiny_router_checkpoint_runtime(backend: str) -> _TinyRouterCheckpointRuntime | None:
    if backend == "heuristic" or sys.version_info >= (3, 14):
        return None
    artifacts = _load_tiny_router_artifacts(allow_download=backend == "checkpoint")
    if artifacts is None:
        return None
    try:
        return _materialize_tiny_router_checkpoint_runtime(
            str(artifacts.repo_dir),
            json.dumps(dict(artifacts.model_config), sort_keys=True),
            json.dumps(dict(artifacts.temperature_scaling), sort_keys=True),
        )
    except Exception:
        # PyTorch/transformers may fail on some platforms (e.g., macOS threading issues)
        return None


def _infer_tiny_router_checkpoint(payload: TinyRouterShadowInput) -> TinyRouterShadowSignal | None:
    runtime = _load_tiny_router_checkpoint_runtime(_requested_backend())
    if runtime is None:
        return None
    try:
        return runtime.infer(payload)
    except Exception:
        return None


def _relation_label(current: str, previous: str) -> TinyRouterHeadPrediction:
    if not previous:
        return TinyRouterHeadPrediction("new", 0.72)
    if _contains_any(current, _CANCELLATION_MARKERS):
        return TinyRouterHeadPrediction("cancellation", 0.96)
    if _contains_any(current, _CORRECTION_MARKERS):
        return TinyRouterHeadPrediction("correction", 0.94)
    if _contains_any(current, _CONFIRMATION_MARKERS):
        return TinyRouterHeadPrediction("confirmation", 0.86)
    if _contains_any(current, _CLOSURE_MARKERS) and len(current.split()) <= 6:
        return TinyRouterHeadPrediction("closure", 0.84)
    if _contains_any(current, _FOLLOW_UP_MARKERS):
        return TinyRouterHeadPrediction("follow_up", 0.81)
    return TinyRouterHeadPrediction("new", 0.66)


def _actionability_label(current: str, relation: str, previous_action: str) -> TinyRouterHeadPrediction:
    if relation in {"correction", "cancellation"}:
        return TinyRouterHeadPrediction("act", 0.93)
    if _contains_any(current, _ACT_MARKERS):
        return TinyRouterHeadPrediction("act", 0.84)
    if previous_action and current:
        return TinyRouterHeadPrediction("act", 0.78)
    if _contains_any(current, _REVIEW_MARKERS) or "?" in current:
        return TinyRouterHeadPrediction("review", 0.74)
    if _contains_any(current, _CLOSURE_MARKERS) or _contains_any(current, _EPHEMERAL_MARKERS):
        return TinyRouterHeadPrediction("none", 0.78)
    return TinyRouterHeadPrediction("review", 0.56)


def _retention_label(current: str, relation: str, actionability: str) -> TinyRouterHeadPrediction:
    if _contains_any(current, _REMEMBER_MARKERS):
        return TinyRouterHeadPrediction("remember", 0.87)
    if actionability == "act" or relation in {"follow_up", "correction", "confirmation"}:
        return TinyRouterHeadPrediction("useful", 0.78)
    if _contains_any(current, _USEFUL_MARKERS):
        return TinyRouterHeadPrediction("useful", 0.72)
    if _contains_any(current, _EPHEMERAL_MARKERS) or relation == "closure":
        return TinyRouterHeadPrediction("ephemeral", 0.81)
    return TinyRouterHeadPrediction("useful", 0.58)


def _urgency_label(current: str, relation: str, actionability: str) -> TinyRouterHeadPrediction:
    if _contains_any(current, _HIGH_URGENCY_MARKERS):
        return TinyRouterHeadPrediction("high", 0.91)
    if relation in {"correction", "cancellation"} or actionability == "act":
        return TinyRouterHeadPrediction("medium", 0.76)
    if actionability == "review":
        return TinyRouterHeadPrediction("medium", 0.62)
    return TinyRouterHeadPrediction("low", 0.74)


def _infer_tiny_router_heuristic(payload: TinyRouterShadowInput) -> TinyRouterShadowSignal:
    current = _normalize(payload.current_text)
    previous = _normalize(payload.previous_text)
    previous_action = _normalize(payload.previous_action)

    relation = _relation_label(current, previous)
    actionability = _actionability_label(current, relation.label, previous_action)
    retention = _retention_label(current, relation.label, actionability.label)
    urgency = _urgency_label(current, relation.label, actionability.label)
    overall = round(
        (
            relation.confidence
            + actionability.confidence
            + retention.confidence
            + urgency.confidence
        )
        / 4.0,
        4,
    )

    return TinyRouterShadowSignal(
        relation_to_previous=relation,
        actionability=actionability,
        retention=retention,
        urgency=urgency,
        overall_confidence=overall,
    )


def infer_tiny_router_shadow(payload: TinyRouterShadowInput) -> TinyRouterShadowSignal:
    """Infer tiny-router-style transition labels using checkpoint or heuristics."""
    checkpoint_signal = _infer_tiny_router_checkpoint(payload)
    if checkpoint_signal is not None:
        return checkpoint_signal
    return _infer_tiny_router_heuristic(payload)


def _message_content(message: Mapping[str, Any]) -> str:
    return str(message.get("content", "") or "").strip()


def infer_tiny_router_shadow_from_messages(
    messages: Sequence[Mapping[str, Any]],
    *,
    previous_action: str | None = None,
    previous_outcome: str | None = None,
    recency_seconds: float | int | None = None,
) -> TinyRouterShadowSignal | None:
    """Infer labels from a chat history, preferring the latest user turn."""
    if not messages:
        return None

    current_idx = -1
    current_role = ""
    current_text = ""
    for idx in range(len(messages) - 1, -1, -1):
        role = str(messages[idx].get("role", "") or "").strip().lower()
        if role == "system":
            continue
        text = _message_content(messages[idx])
        if not text:
            continue
        current_idx = idx
        current_role = role
        current_text = text
        break

    if current_idx < 0 or not current_text:
        return None

    previous_text = ""
    if current_role == "user":
        for idx in range(current_idx - 1, -1, -1):
            role = str(messages[idx].get("role", "") or "").strip().lower()
            if role != "user":
                continue
            text = _message_content(messages[idx])
            if text:
                previous_text = text
                break
    if not previous_text:
        for idx in range(current_idx - 1, -1, -1):
            role = str(messages[idx].get("role", "") or "").strip().lower()
            if role == "system":
                continue
            text = _message_content(messages[idx])
            if text:
                previous_text = text
                break

    return infer_tiny_router_shadow(
        TinyRouterShadowInput(
            current_text=current_text,
            previous_text=previous_text or None,
            previous_action=previous_action,
            previous_outcome=previous_outcome,
            recency_seconds=recency_seconds,
        )
    )
