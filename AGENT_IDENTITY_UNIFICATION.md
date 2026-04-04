# Agent Identity Unification Spec

**Sprint:** Post-bootstrap-fixes  
**Addresses:** INCONSISTENCY-02 from MODEL_ROUTING_MAP.md  
**Target file for canonical model:** `dharma_swarm/models.py`

---

## 1. Current State

Five places in the codebase independently define what an agent "is." The table below lists every field in every schema. A dash (—) means the schema has no equivalent field.

| Field | startup_crew.py (dict) | persistent_agent.py (PersistentAgent.__init__) | autonomous_agent.py (AgentIdentity dataclass) | profiles.py (AgentProfile Pydantic) | api/routers/agents.py (ontology props dict) |
|---|---|---|---|---|---|
| **name** | `name: str` | `name: str` | `name: str` | `name: str` | `props["name"]` / `props["display_name"]` |
| **role** | `role: AgentRole` (enum) | `role: AgentRole` (enum) | `role: str` (bare string) | — | `props["role"]` (bare string) |
| **provider** | `provider: ProviderType` (enum) | `provider_type: ProviderType` (enum, different key name) | `provider: str` (bare string, default `"anthropic"`) | `provider: str` (bare string, default `"CLAUDE_CODE"`) | `props["provider"]` (bare string) |
| **model** | `model: str` | `model: str` | `model: str` (default `"claude-sonnet-4-20250514"`) | `model: str` (default `"claude-code"`) | `props["model"]` (bare string) |
| **system_prompt** | `system_prompt: str` (optional key) | `system_prompt: str` | `system_prompt: str` | `system_prompt_extra: str` | — |
| **thread** | `thread: str` | — | — | `thread: str \| None` | — |
| **wake_interval** | — | `wake_interval_seconds: float` | — | — | — |
| **max_turns** | — | `max_turns: int` | `max_turns: int` (default `25`) | — | — |
| **allowed_tools** | — | — | `allowed_tools: list[str]` | `permissions: list[str]`, `denied: list[str]` | — |
| **working_directory** | — | hardcoded `~/dharma_swarm` | `working_directory: str` | — | — |
| **autonomy** | — | — | — | `autonomy: AutonomyLevel` (enum) | — |
| **max_tokens** | — | — | — | `max_tokens: int` | — |
| **temperature** | — | — | — | `temperature: float` | — |
| **context_budget** | — | — | — | `context_budget: int` | — |
| **timeout** | — | — | — | `timeout: int` | — |
| **tags** | — | — | — | `tags: list[str]` | — |
| **skill_name** | — | — | — | `skill_name: str` | — |
| **agent_slug** | — | — | — | — | `props["agent_slug"]` |
| **display_name** | — | — | — | — | `props["display_name"]` |
| **status** | — | — | — | — | `props["status"]` |
| **model_key** | — | — | — | — | `props["model_key"]` |
| **model_label** | — | — | — | — | `props["model_label"]` |

### Key inconsistencies in the current state

1. **`provider` field name differs:** `startup_crew.py` uses `"provider"`, `persistent_agent.py` uses `"provider_type"`. `persistent_agent._provider_string()` exists solely to paper over this mismatch.
2. **`role` type differs:** `startup_crew.py` and `persistent_agent.py` use `AgentRole` enum; `autonomous_agent.py` uses `str`; `profiles.py` has no role field at all; the API uses bare strings.
3. **`provider` type differs:** enum in swarm/conductor paths, bare uppercase string (`"CLAUDE_CODE"`) in `profiles.py`, bare lowercase string (`"anthropic"`) in `autonomous_agent.py`.
4. **`model` defaults differ:** `autonomous_agent.py` defaults to `"claude-sonnet-4-20250514"`, `profiles.py` defaults to `"claude-code"`, `conductors.py` hardcodes `"claude-opus-4-6"` and `"claude-sonnet-4-20250514"` directly. None of these pull from `model_hierarchy.py`.
5. **`AgentIdentity` name collision:** `autonomous_agent.py` defines its own `AgentIdentity` dataclass. `api/routers/agents.py` uses the string `"AgentIdentity"` as an ontology object type. These are unrelated to each other and to `AgentConfig` in `models.py`.

---

## 2. Unified Schema

Add the following class to `dharma_swarm/models.py`, after the existing `AgentConfig` class (line 176). Do not remove `AgentConfig` yet — remove it in the cleanup pass after all migration targets pass tests.

```python
# dharma_swarm/models.py  (add after AgentConfig)

from dharma_swarm.profiles import AutonomyLevel  # already defined there; move here in cleanup pass


class AgentIdentity(BaseModel):
    """Canonical identity for every agent in the swarm.

    This is the single source of truth for who an agent is.
    All subsystems — startup_crew, persistent_agent, autonomous_agent,
    profiles, API router — construct or derive from this model.

    Identity fields (static, set at creation):
        name            Unique agent name within the swarm.
        role            Functional role from AgentRole enum.
        provider        LLM provider from ProviderType enum.
        model           Model string. Use model_hierarchy.DEFAULT_MODELS[provider]
                        as the default; do NOT hardcode model strings here.
        system_prompt   Full system prompt for this agent.
        thread          Cognitive thread / thematic lane (e.g. "mechanistic").
        working_directory  Filesystem root the agent operates in.

    Execution config fields (tunable per instantiation):
        max_turns       Maximum ReAct loop iterations.
        allowed_tools   Tool whitelist. Empty list = all tools allowed.
        denied_tools    Tool blacklist. Checked before allowed_tools.
        wake_interval   Seconds between autonomous wake cycles (PersistentAgent).
        autonomy        How much the agent acts without human confirmation.
        max_tokens      Token budget per LLM call.
        temperature     Sampling temperature.
        context_budget  Max tokens to include from memory/context.
        timeout         Wall-clock timeout in seconds per wake cycle.

    Classification fields (used by API / ontology layer):
        skill_name      Maps to a SkillDefinition in the skill registry.
        tags            Arbitrary labels for filtering/grouping.
        display_name    Human-readable label. Derived from name if not set.
        agent_slug      URL-safe identifier. Derived from name if not set.
    """

    # ── Identity (required) ──────────────────────────────────────────────
    name: str
    role: AgentRole = AgentRole.GENERAL
    provider: ProviderType = ProviderType.CLAUDE_CODE
    model: str = ""  # Empty = resolve from model_hierarchy.DEFAULT_MODELS[provider] at runtime
    system_prompt: str = ""

    # ── Identity (optional) ─────────────────────────────────────────────
    thread: Optional[str] = None
    working_directory: str = Field(default_factory=lambda: str(Path.home()))

    # ── Execution config ────────────────────────────────────────────────
    max_turns: int = 25
    allowed_tools: list[str] = Field(default_factory=list)   # empty = all allowed
    denied_tools: list[str] = Field(default_factory=list)
    wake_interval: float = 3600.0
    autonomy: AutonomyLevel = AutonomyLevel.BALANCED
    max_tokens: int = 4096
    temperature: float = 0.7
    context_budget: int = 30_000
    timeout: int = 300

    # ── Classification ──────────────────────────────────────────────────
    skill_name: str = ""
    tags: list[str] = Field(default_factory=list)
    display_name: str = ""   # derived from name if empty
    agent_slug: str = ""     # derived from name if empty

    # ── Derived helpers ─────────────────────────────────────────────────
    def resolved_model(self) -> str:
        """Return model string, falling back to model_hierarchy default."""
        if self.model:
            return self.model
        from dharma_swarm.model_hierarchy import DEFAULT_MODELS
        return DEFAULT_MODELS.get(self.provider, "claude-code")

    def resolved_display_name(self) -> str:
        from dharma_swarm.ontology_agents import agent_display_name
        return self.display_name or agent_display_name(self.name)

    def resolved_agent_slug(self) -> str:
        from dharma_swarm.ontology_agents import agent_slug
        return self.agent_slug or agent_slug(self.name)

    def provider_string(self) -> str:
        """Return the lowercase string AutonomousAgent._call_llm() expects."""
        _MAP = {
            ProviderType.ANTHROPIC: "anthropic",
            ProviderType.CLAUDE_CODE: "anthropic",
            ProviderType.CODEX: "codex",
            ProviderType.OPENROUTER: "openrouter",
            ProviderType.OPENROUTER_FREE: "openrouter",
        }
        return _MAP.get(self.provider, "anthropic")
```

### Required imports to add at the top of `dharma_swarm/models.py`

```python
from pathlib import Path
# AutonomyLevel import — add after moving AutonomyLevel from profiles.py to models.py
# (see Migration Plan step 4). Until then, import at function scope inside AgentIdentity.
```

### `AutonomyLevel` placement decision

`AutonomyLevel` is currently defined in `profiles.py`. Move it to `models.py` in the same PR as step 4 (profiles migration). After the move, update `profiles.py` to import it from `models`:

```python
# profiles.py — replace local AutonomyLevel definition with:
from dharma_swarm.models import AutonomyLevel
```

---

## 3. Migration Plan

Execute in this order. Each step is independently mergeable.

### Step 1 — `startup_crew.py`: replace dicts with `AgentIdentity`

**File:** `dharma_swarm/startup_crew.py`

**What changes:**

1. Import `AgentIdentity` from `dharma_swarm.models`.
2. Replace every `{...}` crew dict with an `AgentIdentity(...)` constructor call.
3. In `_resolve_default_crew()`, `CYBERNETICS_CREW`, and `_crew_from_skills()`, change the return type annotation from `list[dict]` to `list[AgentIdentity]`.
4. In `spawn_default_crew()` and `spawn_cybernetics_crew()`, replace `spec["name"]`, `spec["role"]`, etc. with `spec.name`, `spec.role`, etc.
5. Remove the `_PROVIDER_MAP` and `_SKILL_ROLE_MAP` dicts — use `ProviderType(skill.provider)` and `AgentRole(skill.name)` with fallback to defaults directly in `_crew_from_skills()`.

**Before (example):**
```python
{"name": "cartographer", "role": AgentRole.CARTOGRAPHER,
 "thread": "mechanistic", "provider": ProviderType.OLLAMA, "model": _model}
```

**After:**
```python
AgentIdentity(
    name="cartographer",
    role=AgentRole.CARTOGRAPHER,
    thread="mechanistic",
    provider=ProviderType.OLLAMA,
    model=_model,
)
```

**In `spawn_default_crew()`, replace dict key access:**
```python
# Before:
provider = spec.get("provider", ProviderType.CLAUDE_CODE)
model = spec.get("model", "claude-code")
base_prompt = str(spec.get("system_prompt", "") or "").strip()

# After:
provider = spec.provider
model = spec.resolved_model()
base_prompt = spec.system_prompt.strip()
```

**`spawn_agent()` call site** — no change needed; `swarm.spawn_agent()` already takes `name`, `role`, `thread`, `provider_type`, `model`, `system_prompt` as keyword args. Pass `spec.provider` as `provider_type`.

---

### Step 2 — `persistent_agent.py`: take `AgentIdentity` in `__init__`

**File:** `dharma_swarm/persistent_agent.py`

**What changes:**

1. Replace the individual `name, role, provider_type, model, system_prompt, max_turns` parameters with a single `identity: AgentIdentity` parameter.
2. Remove `_provider_string()` helper — `AgentIdentity.provider_string()` replaces it.
3. Remove the internal `AgentIdentity(...)` construction block (lines 68–76) — the `identity` arg IS the identity.
4. Store `self.identity = identity` and derive other attributes from it.

**Before:**
```python
def __init__(
    self,
    name: str,
    role: AgentRole,
    provider_type: ProviderType,
    model: str,
    state_dir: Path | None = None,
    wake_interval_seconds: float = 3600.0,
    system_prompt: str = "",
    max_turns: int = 25,
) -> None:
    self.name = name
    self.role = role
    self.provider_type = provider_type
    self.model = model
    ...
    identity = AgentIdentity(
        name=name,
        role=role.value,          # <-- enum → string conversion (bug-prone)
        system_prompt=system_prompt,
        model=model,
        provider=_provider_string(provider_type),  # <-- enum → string (bug-prone)
        max_turns=max_turns,
        working_directory=str(Path.home() / "dharma_swarm"),
    )
    self._agent = AutonomousAgent(identity)
```

**After:**
```python
def __init__(
    self,
    identity: AgentIdentity,
    state_dir: Path | None = None,
) -> None:
    self.identity = identity
    self.name = identity.name
    self.role = identity.role
    self.provider_type = identity.provider
    self.model = identity.resolved_model()
    self.state_dir = state_dir or Path.home() / ".dharma"
    self.wake_interval = identity.wake_interval
    self.system_prompt = identity.system_prompt
    self._agent = AutonomousAgent(identity)
    ...
```

**Update `conductors.py` to construct `AgentIdentity` objects** (see Step 6).

---

### Step 3 — `autonomous_agent.py`: replace local `AgentIdentity` dataclass with unified one

**File:** `dharma_swarm/autonomous_agent.py`

**What changes:**

1. Delete the `@dataclass class AgentIdentity` definition (lines 210–224).
2. Add to the imports at the top of the file:
   ```python
   from dharma_swarm.models import AgentIdentity
   ```
3. Update `AutonomousAgent._call_llm()` to use `self.identity.provider_string()` instead of matching on `self.identity.provider` bare strings.
4. Update `AutonomousAgent.__init__()` to use `identity.resolved_model()` instead of `identity.model` directly when configuring clients.
5. Update the `allowed_tools` filtering in `AutonomousAgent.wake()` to use `identity.allowed_tools` and `identity.denied_tools` from the unified model (previously only `allowed_tools` existed).

**Critical:** `persistent_agent.py` currently passes `role=role.value` (a string) to the old `AgentIdentity` dataclass. After this step, it passes the `AgentRole` enum directly — this is correct and intended.

**Check `_call_llm()` for bare string matching:**
```python
# Before (autonomous_agent.py ~line 400):
if self.identity.provider == "anthropic":
    ...
elif self.identity.provider == "openrouter":
    ...

# After:
provider_str = self.identity.provider_string()
if provider_str == "anthropic":
    ...
elif provider_str == "openrouter":
    ...
```

---

### Step 4 — `profiles.py`: derive `AgentProfile` from `AgentIdentity`

**File:** `dharma_swarm/profiles.py`

**What changes:**

1. Move `AutonomyLevel` enum from `profiles.py` to `dharma_swarm/models.py`. Add `from dharma_swarm.models import AutonomyLevel` back in `profiles.py`.
2. Change `AgentProfile` to extend `AgentIdentity` instead of `BaseModel`:
   ```python
   from dharma_swarm.models import AgentIdentity
   
   class AgentProfile(AgentIdentity):
       """AgentIdentity extended with runtime-specific fields."""
       ...
   ```
3. Remove from `AgentProfile` all fields that now live on `AgentIdentity`: `name`, `model`, `provider`, `thread`, `system_prompt_extra` (rename to `system_prompt`), `tags`.
4. Keep the `AgentProfile`-specific fields that do NOT belong on the core identity:
   - `skill_name` — already on `AgentIdentity`; remove duplicate
   - `max_tokens` — already on `AgentIdentity`; remove duplicate  
   - `temperature` — already on `AgentIdentity`; remove duplicate
   - `context_budget` — already on `AgentIdentity`; remove duplicate
   - `timeout` — already on `AgentIdentity`; remove duplicate
   - `permissions` → rename to `allowed_tools` on `AgentIdentity` (done in Step 3)
   - `denied` → rename to `denied_tools` on `AgentIdentity` (done in Step 3)
   - `autonomy` — already on `AgentIdentity`; remove duplicate
5. After deduplication, `AgentProfile` has no unique fields and becomes a type alias:
   ```python
   # profiles.py — after full deduplication
   AgentProfile = AgentIdentity  # backward-compat alias
   ```
6. Update `ProfileManager.create_from_skill()` to construct `AgentIdentity` directly:
   ```python
   def create_from_skill(self, skill, overrides=None) -> AgentIdentity:
       from dharma_swarm.models import AgentIdentity, ProviderType, AgentRole
       try:
           provider = ProviderType(skill.provider.lower())
       except ValueError:
           provider = ProviderType.CLAUDE_CODE
       return AgentIdentity(
           name=skill.name,
           skill_name=skill.name,
           provider=provider,
           model=skill.model or "",
           autonomy=_AUTONOMY_MAP.get(skill.autonomy, AutonomyLevel.BALANCED),
           thread=skill.thread,
           system_prompt=skill.system_prompt,
           tags=skill.tags,
           **(overrides or {}),
       )
   ```

**`system_prompt_extra` → `system_prompt` note:** `AgentProfile.system_prompt_extra` was a suffix appended to a base prompt. This conflicts with `AgentIdentity.system_prompt` which holds the full prompt. Resolution: in `ProfileManager.create_from_skill()`, set `system_prompt=skill.system_prompt` directly. Callers that were appending `system_prompt_extra` should instead concatenate before constructing the identity.

---

### Step 5 — `api/routers/agents.py`: construct `AgentOut` from `AgentIdentity`

**File:** `api/routers/agents.py`

**What changes:**

1. The `_identity_to_out()` function currently parses a raw `properties` dict from an ontology object. After unification, ontology objects should store a serialized `AgentIdentity`. Change `_identity_to_out()` to:
   ```python
   def _identity_to_out(identity_obj) -> dict:
       props = identity_obj.properties
       # Deserialize to AgentIdentity if stored as dict, else use props directly
       try:
           from dharma_swarm.models import AgentIdentity
           ai = AgentIdentity(**props) if isinstance(props, dict) else props
           name = ai.name
           provider = ai.provider.value
           model = ai.resolved_model()
           role = ai.role.value
       except Exception:
           # Fallback: props dict may not match schema yet (pre-migration agents)
           name = str(props.get("name") or props.get("display_name") or identity_obj.id)
           provider = str(props.get("provider") or "")
           model = str(props.get("model") or "")
           role = str(props.get("role") or "general")
       return AgentOut(
           id=str(props.get("agent_id") or identity_obj.id),
           name=name,
           agent_slug=agent_slug(name),
           display_name=agent_display_name(name),
           role=role,
           status=str(props.get("status") or "unknown"),
           ...
       ).model_dump()
   ```
2. In `spawn_agent()` endpoint, replace the manual `AgentRole(req.role)` / `ProviderType(req.provider)` try/except blocks with:
   ```python
   from dharma_swarm.models import AgentIdentity, AgentRole, ProviderType
   identity = AgentIdentity(
       name=req.name,
       role=AgentRole(req.role) if req.role else AgentRole.GENERAL,
       provider=ProviderType(req.provider) if req.provider else ProviderType.CLAUDE_CODE,
       model=req.model or "",
   )
   agent = await swarm.spawn_agent(
       name=identity.name,
       role=identity.role,
       model=identity.resolved_model(),
       provider_type=identity.provider,
   )
   ```
3. No change to `_agent_to_out()` — `AgentState` remains separate (it's runtime state, not identity).

---

### Step 6 — `conductors.py`: use `AgentIdentity` with provider fallback

**File:** `dharma_swarm/conductors.py`

**What changes:**

1. Replace the two raw dicts `CONDUCTOR_CLAUDE_CONFIG` and `CONDUCTOR_CODEX_CONFIG` with `AgentIdentity` instances.
2. Remove the hardcoded `ProviderType.ANTHROPIC` — instead use `runtime_provider.preferred_runtime_provider_configs()` to pick the best available provider at startup, falling back through the tier hierarchy.

**Before:**
```python
CONDUCTOR_CLAUDE_CONFIG = {
    "name": "conductor_claude",
    "role": AgentRole.CONDUCTOR,
    "provider_type": ProviderType.ANTHROPIC,
    "model": "claude-opus-4-6",
    "wake_interval_seconds": 3600.0,
    "system_prompt": _CONDUCTOR_CLAUDE_PROMPT,
    "max_turns": 15,
}
```

**After:**
```python
from dharma_swarm.models import AgentIdentity, AgentRole, ProviderType
from dharma_swarm.model_hierarchy import DEFAULT_MODELS


def _resolve_conductor_provider() -> tuple[ProviderType, str]:
    """Pick the best available provider for conductors via the tier chain."""
    from dharma_swarm.runtime_provider import preferred_runtime_provider_configs
    configs = preferred_runtime_provider_configs()
    if configs:
        best = configs[0]
        return best.provider_type, best.default_model
    # Hard fallback — only reached if no API keys and no CLI binaries
    return ProviderType.CLAUDE_CODE, "claude-code"


def _make_conductor_claude() -> AgentIdentity:
    provider, model = _resolve_conductor_provider()
    return AgentIdentity(
        name="conductor_claude",
        role=AgentRole.CONDUCTOR,
        provider=provider,
        model=model,
        wake_interval=3600.0,
        system_prompt=_CONDUCTOR_CLAUDE_PROMPT,
        max_turns=15,
    )


def _make_conductor_codex() -> AgentIdentity:
    provider, model = _resolve_conductor_provider()
    return AgentIdentity(
        name="conductor_codex",
        role=AgentRole.CONDUCTOR,
        provider=provider,
        model=model,
        wake_interval=1800.0,
        system_prompt=_CONDUCTOR_CODEX_PROMPT,
        max_turns=10,
    )


CONDUCTOR_CONFIGS: list[AgentIdentity] = [_make_conductor_claude(), _make_conductor_codex()]
```

3. Update `startup_crew.spawn_conductor_crew()` to use `AgentIdentity` attributes instead of dict keys:
   ```python
   # Before:
   agent = await swarm.spawn_agent(
       name=cfg["name"],
       role=cfg["role"],
       provider_type=cfg["provider_type"],
       model=cfg["model"],
       system_prompt=cfg["system_prompt"][:500],
   )
   
   # After:
   agent = await swarm.spawn_agent(
       name=cfg.name,
       role=cfg.role,
       provider_type=cfg.provider,
       model=cfg.resolved_model(),
       system_prompt=cfg.system_prompt[:500],
   )
   ```

---

## 4. Consistency Rules

These rules apply to the entire codebase after the migration. Any code that violates them is a bug.

### Rule 1: No bare strings for enums

`AgentRole`, `ProviderType`, and `AutonomyLevel` must never appear as bare strings at construction sites. Valid: `AgentRole.SURGEON`, `ProviderType.GROQ`. Invalid: `"surgeon"`, `"groq"`, `"CLAUDE_CODE"`.

Enforcement: add a `model_validator(mode="before")` to `AgentIdentity` that coerces strings to enums:

```python
from pydantic import model_validator

@model_validator(mode="before")
@classmethod
def _coerce_enums(cls, values):
    if isinstance(values.get("role"), str):
        values["role"] = AgentRole(values["role"])
    if isinstance(values.get("provider"), str):
        try:
            values["provider"] = ProviderType(values["provider"].lower())
        except ValueError:
            # Handle uppercase legacy values like "CLAUDE_CODE"
            values["provider"] = ProviderType(values["provider"].lower().replace("_", "_"))
    if isinstance(values.get("autonomy"), str):
        from dharma_swarm.profiles import _AUTONOMY_MAP
        values["autonomy"] = _AUTONOMY_MAP.get(values["autonomy"], AutonomyLevel.BALANCED)
    return values
```

### Rule 2: Model defaults come from `model_hierarchy.py`

No file except `model_hierarchy.py` may hardcode a model string as a default value. All other files must use:
```python
from dharma_swarm.model_hierarchy import DEFAULT_MODELS
model = DEFAULT_MODELS.get(provider_type, "claude-code")
```

`AgentIdentity.model` defaults to `""` (empty string). Call `identity.resolved_model()` whenever you need the actual model string to pass to an LLM provider. This ensures `model_hierarchy.py` is always consulted.

### Rule 3: Provider resolution goes through `runtime_provider.py`

No agent may directly instantiate `AsyncAnthropic`, `AsyncOpenAI`, or any provider client by name. All provider client creation must go through:
- `runtime_provider.create_runtime_provider(provider_type, model)` for single-provider use
- `runtime_provider.preferred_runtime_provider_configs()` for fallback chains

`autonomous_agent.py`'s `_call_llm()` currently violates this by directly instantiating clients. Fix as part of INCONSISTENCY-01 (separate sprint), not this sprint. For now, `_call_llm()` may continue using direct client instantiation but must use `identity.provider_string()` to resolve the provider name.

### Rule 4: `AgentProfile` is not a separate concept

`AgentProfile` is a type alias for `AgentIdentity`. Code that needs "profile-flavored" agent config constructs an `AgentIdentity` directly. The `ProfileManager` saves and loads `AgentIdentity` objects serialized as JSON. Existing profile JSON files on disk remain compatible because `AgentIdentity` accepts all `AgentProfile` fields.

### Rule 5: `wake_interval` is an identity field, not a constructor argument

After migration, `PersistentAgent.__init__` takes only `identity: AgentIdentity` and optional `state_dir`. Wake interval is `identity.wake_interval`. Callers that need a custom interval set it on the `AgentIdentity` before passing it in.

---

## 5. Testing Strategy

One test file per migration target. All test files go in `dharma_swarm/tests/`.

### `test_agent_identity_model.py`

Covers: the unified `AgentIdentity` model in `models.py`.

```python
def test_enum_coercion():
    """Bare strings are coerced to enums."""
    identity = AgentIdentity(name="x", role="surgeon", provider="anthropic")
    assert identity.role == AgentRole.SURGEON
    assert identity.provider == ProviderType.ANTHROPIC

def test_uppercase_provider_coercion():
    """Legacy uppercase provider strings (from profiles.py) are coerced."""
    identity = AgentIdentity(name="x", provider="CLAUDE_CODE")
    assert identity.provider == ProviderType.CLAUDE_CODE

def test_resolved_model_uses_hierarchy():
    """resolved_model() falls back to model_hierarchy when model is empty."""
    identity = AgentIdentity(name="x", provider=ProviderType.GROQ)
    model = identity.resolved_model()
    from dharma_swarm.model_hierarchy import DEFAULT_MODELS
    assert model == DEFAULT_MODELS[ProviderType.GROQ]

def test_resolved_model_respects_explicit():
    """resolved_model() returns the explicit model string when set."""
    identity = AgentIdentity(name="x", model="custom-model-v1")
    assert identity.resolved_model() == "custom-model-v1"

def test_provider_string():
    """provider_string() returns the lowercase string AutonomousAgent expects."""
    assert AgentIdentity(name="x", provider=ProviderType.CLAUDE_CODE).provider_string() == "anthropic"
    assert AgentIdentity(name="x", provider=ProviderType.OPENROUTER_FREE).provider_string() == "openrouter"
    assert AgentIdentity(name="x", provider=ProviderType.CODEX).provider_string() == "codex"

def test_allowed_denied_tools_default_empty():
    identity = AgentIdentity(name="x")
    assert identity.allowed_tools == []
    assert identity.denied_tools == []
```

---

### `test_startup_crew_migration.py`

Covers: `startup_crew._resolve_default_crew()` and `spawn_default_crew()`.

```python
def test_default_crew_returns_agent_identities():
    """_resolve_default_crew() returns list of AgentIdentity, not dicts."""
    from dharma_swarm.startup_crew import _resolve_default_crew
    from dharma_swarm.models import AgentIdentity
    crew = _resolve_default_crew()
    assert all(isinstance(spec, AgentIdentity) for spec in crew)

def test_crew_identities_have_enum_roles():
    """All crew specs use AgentRole enums, not strings."""
    from dharma_swarm.startup_crew import _resolve_default_crew
    from dharma_swarm.models import AgentRole
    crew = _resolve_default_crew()
    for spec in crew:
        assert isinstance(spec.role, AgentRole)

def test_crew_identities_have_enum_providers():
    """All crew specs use ProviderType enums, not strings."""
    from dharma_swarm.startup_crew import _resolve_default_crew
    from dharma_swarm.models import ProviderType
    crew = _resolve_default_crew()
    for spec in crew:
        assert isinstance(spec.provider, ProviderType)

@pytest.mark.asyncio
async def test_spawn_default_crew_calls_swarm_with_correct_args():
    """spawn_default_crew() passes provider as provider_type kwarg."""
    mock_swarm = AsyncMock()
    mock_swarm.list_agents.return_value = []
    mock_swarm.spawn_agent.return_value = MagicMock()
    from dharma_swarm.startup_crew import spawn_default_crew
    await spawn_default_crew(mock_swarm)
    call_kwargs = mock_swarm.spawn_agent.call_args_list[0].kwargs
    assert "provider_type" in call_kwargs
    from dharma_swarm.models import ProviderType
    assert isinstance(call_kwargs["provider_type"], ProviderType)
```

---

### `test_persistent_agent_migration.py`

Covers: `PersistentAgent` taking `AgentIdentity` instead of individual fields.

```python
def test_persistent_agent_accepts_identity():
    """PersistentAgent.__init__ accepts an AgentIdentity object."""
    from dharma_swarm.models import AgentIdentity, AgentRole, ProviderType
    from dharma_swarm.persistent_agent import PersistentAgent
    identity = AgentIdentity(
        name="test_conductor",
        role=AgentRole.CONDUCTOR,
        provider=ProviderType.OLLAMA,
        model="glm-5:cloud",
        system_prompt="Test prompt.",
        max_turns=5,
    )
    agent = PersistentAgent(identity=identity)
    assert agent.name == "test_conductor"
    assert agent.role == AgentRole.CONDUCTOR

def test_persistent_agent_provider_type_attribute():
    """agent.provider_type reflects identity.provider (backward compat)."""
    from dharma_swarm.models import AgentIdentity, ProviderType
    from dharma_swarm.persistent_agent import PersistentAgent
    identity = AgentIdentity(name="x", provider=ProviderType.OPENROUTER_FREE)
    agent = PersistentAgent(identity=identity)
    assert agent.provider_type == ProviderType.OPENROUTER_FREE

def test_persistent_agent_wake_interval_from_identity():
    """wake_interval comes from AgentIdentity, not a separate constructor arg."""
    from dharma_swarm.models import AgentIdentity
    from dharma_swarm.persistent_agent import PersistentAgent
    identity = AgentIdentity(name="x", wake_interval=900.0)
    agent = PersistentAgent(identity=identity)
    assert agent.wake_interval == 900.0
```

---

### `test_autonomous_agent_migration.py`

Covers: `AutonomousAgent` using `AgentIdentity` from `models.py`, not its own dataclass.

```python
def test_autonomous_agent_uses_models_identity():
    """AgentIdentity imported in autonomous_agent comes from models, not a local dataclass."""
    import dharma_swarm.autonomous_agent as aa
    import dharma_swarm.models as m
    assert aa.AgentIdentity is m.AgentIdentity

def test_autonomous_agent_constructs_with_enum_role():
    """AutonomousAgent accepts AgentIdentity with enum role (not string)."""
    from dharma_swarm.models import AgentIdentity, AgentRole, ProviderType
    from dharma_swarm.autonomous_agent import AutonomousAgent
    identity = AgentIdentity(
        name="test_agent",
        role=AgentRole.RESEARCHER,
        provider=ProviderType.ANTHROPIC,
        system_prompt="You are a test agent.",
    )
    agent = AutonomousAgent(identity)
    assert agent.identity.role == AgentRole.RESEARCHER

def test_provider_string_used_in_call_llm():
    """_call_llm() uses identity.provider_string(), not string matching on identity.provider."""
    # This test verifies the method exists and returns the right value;
    # the actual routing is tested in integration tests.
    from dharma_swarm.models import AgentIdentity, ProviderType
    identity = AgentIdentity(name="x", provider=ProviderType.CLAUDE_CODE)
    assert identity.provider_string() == "anthropic"
```

---

### `test_profiles_migration.py`

Covers: `AgentProfile` deriving from `AgentIdentity`; `ProfileManager.create_from_skill()` returning `AgentIdentity`.

```python
def test_agent_profile_is_agent_identity():
    """AgentProfile is a subclass of (or alias for) AgentIdentity."""
    from dharma_swarm.profiles import AgentProfile
    from dharma_swarm.models import AgentIdentity
    # Either direct subclass or type alias
    assert issubclass(AgentProfile, AgentIdentity) or AgentProfile is AgentIdentity

def test_profile_manager_create_from_skill_returns_identity():
    """create_from_skill() returns an AgentIdentity."""
    from dharma_swarm.profiles import ProfileManager
    from dharma_swarm.models import AgentIdentity
    manager = ProfileManager()
    skill = SimpleNamespace(
        name="surgeon", model="", provider="CLAUDE_CODE",
        autonomy="balanced", thread="alignment",
        system_prompt="You are a surgeon.", tags=[],
    )
    profile = manager.create_from_skill(skill)
    assert isinstance(profile, AgentIdentity)

def test_profile_provider_is_enum():
    """Profiles created from skills have ProviderType enum, not string."""
    from dharma_swarm.profiles import ProfileManager
    from dharma_swarm.models import ProviderType
    manager = ProfileManager()
    skill = SimpleNamespace(
        name="x", model="", provider="OPENROUTER",
        autonomy="balanced", thread=None,
        system_prompt="", tags=[],
    )
    profile = manager.create_from_skill(skill)
    assert isinstance(profile.provider, ProviderType)
    assert profile.provider == ProviderType.OPENROUTER

def test_autonomy_level_importable_from_models():
    """AutonomyLevel can be imported from models (not only from profiles)."""
    from dharma_swarm.models import AutonomyLevel
    assert AutonomyLevel.BALANCED.value == "balanced"
```

---

### `test_agents_router_migration.py`

Covers: `api/routers/agents.py` constructing `AgentOut` from `AgentIdentity`.

```python
def test_spawn_agent_endpoint_uses_enum_validation():
    """spawn_agent() constructs AgentIdentity, catching invalid role/provider cleanly."""
    from fastapi.testclient import TestClient
    from api.main import app  # adjust import as needed
    client = TestClient(app)
    # Invalid role → should fall back to GENERAL, not 500
    resp = client.post("/api/agents/spawn", json={"name": "test_x", "role": "invalid_role"})
    assert resp.status_code == 200
    assert resp.json()["data"]["role"] == "general"

def test_identity_to_out_fallback_on_missing_fields():
    """_identity_to_out() handles pre-migration ontology objects (props without full schema)."""
    from api.routers.agents import _identity_to_out
    from types import SimpleNamespace
    identity_obj = SimpleNamespace(
        id="abc123",
        properties={"name": "old_agent", "role": "researcher", "model": "gpt-4"},
    )
    out = _identity_to_out(identity_obj)
    assert out["name"] == "old_agent"
    assert out["role"] == "researcher"
```

---

### `test_conductors_migration.py`

Covers: `conductors.py` constructing `AgentIdentity` objects, not dicts; provider resolved at runtime, not hardcoded.

```python
def test_conductor_configs_are_agent_identities():
    """CONDUCTOR_CONFIGS contains AgentIdentity objects, not dicts."""
    from dharma_swarm.conductors import CONDUCTOR_CONFIGS
    from dharma_swarm.models import AgentIdentity
    assert all(isinstance(cfg, AgentIdentity) for cfg in CONDUCTOR_CONFIGS)

def test_conductor_role_is_enum():
    """Conductor configs use AgentRole.CONDUCTOR enum."""
    from dharma_swarm.conductors import CONDUCTOR_CONFIGS
    from dharma_swarm.models import AgentRole
    for cfg in CONDUCTOR_CONFIGS:
        assert cfg.role == AgentRole.CONDUCTOR

def test_conductor_provider_not_hardcoded_anthropic(monkeypatch):
    """When ANTHROPIC_API_KEY is absent, conductors use a different provider."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Re-import to re-run _resolve_conductor_provider()
    import importlib
    import dharma_swarm.conductors as conductors_mod
    importlib.reload(conductors_mod)
    from dharma_swarm.models import ProviderType
    for cfg in conductors_mod.CONDUCTOR_CONFIGS:
        assert cfg.provider != ProviderType.ANTHROPIC

def test_conductor_model_resolves_from_hierarchy():
    """Conductor model comes from model_hierarchy, not a hardcoded string."""
    from dharma_swarm.conductors import CONDUCTOR_CONFIGS
    # Model must be resolvable — resolved_model() must not return an empty string
    for cfg in CONDUCTOR_CONFIGS:
        assert cfg.resolved_model() != ""
```

---

## Execution Order Summary

| Step | File | PR dependency |
|---|---|---|
| 1 | `dharma_swarm/models.py` — add `AgentIdentity` + move `AutonomyLevel` | None (first) |
| 2 | `dharma_swarm/autonomous_agent.py` — delete local dataclass, import from models | After step 1 |
| 3 | `dharma_swarm/persistent_agent.py` — accept `AgentIdentity` in `__init__` | After step 2 |
| 4 | `dharma_swarm/profiles.py` — derive `AgentProfile` from `AgentIdentity` | After step 1 |
| 5 | `dharma_swarm/startup_crew.py` — replace dicts with `AgentIdentity` | After step 3 |
| 6 | `dharma_swarm/conductors.py` — replace dicts with `AgentIdentity`, add provider fallback | After step 3 |
| 7 | `api/routers/agents.py` — construct `AgentOut` via `AgentIdentity` | After step 1 |

Steps 4 and 7 can be done in parallel with steps 2–3. Steps 5 and 6 must follow step 3.

---

*End of spec. No behavior changes — only schema unification and type safety.*
