"""Package-local compatibility shim for the canonical API key registry.

This imports from the root-level api_keys.py module.
"""

import sys
from pathlib import Path

# Add parent directory to path to access root api_keys.py
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

try:
    from api_keys import *  # noqa: F401,F403
except ModuleNotFoundError:
    # Fallback: define constants inline if root api_keys.py not found
    ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"
    OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
    OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
    NVIDIA_NIM_API_KEY_ENV = "NVIDIA_NIM_API_KEY"
    OLLAMA_API_KEY_ENV = "OLLAMA_API_KEY"
    GROQ_API_KEY_ENV = "GROQ_API_KEY"
    CEREBRAS_API_KEY_ENV = "CEREBRAS_API_KEY"
    SILICONFLOW_API_KEY_ENV = "SILICONFLOW_API_KEY"
    TOGETHER_API_KEY_ENV = "TOGETHER_API_KEY"
    FIREWORKS_API_KEY_ENV = "FIREWORKS_API_KEY"
    GOOGLE_AI_API_KEY_ENV = "GOOGLE_AI_API_KEY"
    SAMBANOVA_API_KEY_ENV = "SAMBANOVA_API_KEY"
    MISTRAL_API_KEY_ENV = "MISTRAL_API_KEY"
    CHUTES_API_KEY_ENV = "CHUTES_API_KEY"
