#!/usr/bin/env bash
# Shared runtime env loader for launchd/daemon entrypoints.

if [[ -n "${DHARMA_RUNTIME_ENV_LOADED:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi
export DHARMA_RUNTIME_ENV_LOADED=1

_load_env_file() {
    local envfile="$1"
    if [[ -f "$envfile" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "$envfile"
        set +a
    fi
}

if [[ -f "$HOME/.zshrc" ]]; then
    eval "$(
        grep -E '^export ' "$HOME/.zshrc" 2>/dev/null \
            | grep -E '(API_KEY|BASE_URL|OPENROUTER|OLLAMA|GROQ|CEREBRAS|SILICONFLOW|MOONSHOT|NIM_API_KEY|NVIDIA_NIM_API_KEY)' \
            || true
    )"
fi

for envfile in "$HOME/.env" "$HOME/.dharma/.env" "$HOME/.dharma/daemon.env"; do
    _load_env_file "$envfile"
done

_load_keychain_var() {
    local var_name="$1"
    local account="$2"
    local service="$3"
    local current="${!var_name:-}"
    local value=""

    if [[ -n "$current" ]]; then
        return 0
    fi

    value="$(security find-generic-password -a "$account" -s "$service" -w 2>/dev/null || true)"
    if [[ -n "$value" ]]; then
        export "${var_name}=${value}"
    fi
}

_load_keychain_var "ANTHROPIC_API_KEY" "$USER" "anthropic-api-key"
_load_keychain_var "OPENAI_API_KEY" "$USER" "openai-api-key"
_load_keychain_var "OPENROUTER_API_KEY" "$USER" "openrouter-api-key"
_load_keychain_var "OLLAMA_API_KEY" "$USER" "ollama-api-key"
_load_keychain_var "GROQ_API_KEY" "$USER" "groq-api-key"
_load_keychain_var "NIM_API_KEY" "$USER" "nim-api-key"

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    _load_keychain_var "OPENROUTER_API_KEY" "openrouter" "openrouter-api-key"
fi

if [[ -n "${NIM_API_KEY:-}" && -z "${NVIDIA_NIM_API_KEY:-}" ]]; then
    export NVIDIA_NIM_API_KEY="$NIM_API_KEY"
fi
if [[ -n "${NVIDIA_NIM_API_KEY:-}" && -z "${NIM_API_KEY:-}" ]]; then
    export NIM_API_KEY="$NVIDIA_NIM_API_KEY"
fi
