"""
JIKOKU Instrumentation - Automatic span tracing for computational efficiency.

Zero-overhead when disabled. Automatic instrumentation for providers, swarm, evolution.

Usage:
    # Decorator for automatic tracing
    @jikoku_traced(category="api_call")
    async def my_function(...):
        ...

    # Context manager for explicit spans
    async with jikoku_auto_span("execute.task", "Process task"):
        ...

    # Enable/disable globally
    export JIKOKU_ENABLED=1  # Enable
    export JIKOKU_ENABLED=0  # Disable (< 1ns overhead)
"""

import os
import functools
import inspect
import logging
from contextvars import ContextVar
from contextlib import asynccontextmanager, contextmanager
from typing import Optional, Any, Callable, TypeVar
import time

from .jikoku_samaya import get_global_tracer  # type: ignore

logger = logging.getLogger(__name__)

# Feature flag - disable for zero overhead
JIKOKU_ENABLED = os.environ.get('JIKOKU_ENABLED', '1') == '1'

# Context var for nested span tracking
_current_span_id: ContextVar[Optional[str]] = ContextVar('current_span_id', default=None)

# Type hint for decorators
F = TypeVar('F', bound=Callable[..., Any])


def is_enabled() -> bool:
    """Check if JIKOKU tracing is enabled"""
    return JIKOKU_ENABLED


def set_enabled(enabled: bool):
    """Enable or disable JIKOKU tracing globally"""
    global JIKOKU_ENABLED
    JIKOKU_ENABLED = enabled


# ============================================================================
# CORE INSTRUMENTATION PRIMITIVES
# ============================================================================

@asynccontextmanager
async def jikoku_auto_span(
    category: str,
    intent: str,
    agent_id: Optional[str] = None,
    task_id: Optional[str] = None,
    **metadata
):
    """
    Automatic async span with zero-overhead when disabled.

    Usage:
        async with jikoku_auto_span("api_call", "Call Anthropic"):
            response = await anthropic.complete(...)
    """
    if not JIKOKU_ENABLED:
        # Zero overhead path - just yield
        yield None
        return

    tracer = get_global_tracer()

    # Get parent span from context
    parent_id = _current_span_id.get()
    if parent_id:
        metadata['parent_span_id'] = parent_id

    # Start span
    span_id = tracer.start(
        category=category,
        intent=intent,
        agent_id=agent_id,
        task_id=task_id,
        **metadata
    )

    # Set as current span in context
    token = _current_span_id.set(span_id)

    try:
        yield span_id
    finally:
        # End span
        tracer.end(span_id)

        # Restore previous span
        _current_span_id.reset(token)


@contextmanager
def jikoku_sync_span(
    category: str,
    intent: str,
    agent_id: Optional[str] = None,
    task_id: Optional[str] = None,
    **metadata
):
    """
    Synchronous span with zero-overhead when disabled.

    Usage:
        with jikoku_sync_span("file_op", "Write to disk"):
            with open(...) as f:
                f.write(...)
    """
    if not JIKOKU_ENABLED:
        yield None
        return

    tracer = get_global_tracer()

    # Get parent span from context
    parent_id = _current_span_id.get()
    if parent_id:
        metadata['parent_span_id'] = parent_id

    # Start span
    span_id = tracer.start(
        category=category,
        intent=intent,
        agent_id=agent_id,
        task_id=task_id,
        **metadata
    )

    # Set as current span in context
    token = _current_span_id.set(span_id)

    try:
        yield span_id
    finally:
        # End span
        tracer.end(span_id)

        # Restore previous span
        _current_span_id.reset(token)


# ============================================================================
# DECORATOR-BASED INSTRUMENTATION
# ============================================================================

def jikoku_traced(
    category: str,
    intent_template: Optional[str] = None,
    extract_metadata: Optional[Callable[..., Any]] = None
) -> Callable[[F], F]:
    """
    Decorator for automatic function/method tracing.

    Zero-overhead when disabled (< 1ns - just returns original function).

    Args:
        category: Span category (e.g., "api_call", "execute.llm_call")
        intent_template: Optional template for intent (uses function name if None)
        extract_metadata: Optional callable to extract metadata from args/kwargs

    Usage:
        @jikoku_traced(category="api_call")
        async def call_anthropic(self, messages):
            ...

        @jikoku_traced(
            category="execute.mutation",
            intent_template="Mutate {component}",
            extract_metadata=lambda args, kwargs: {'component': args[0]}
        )
        async def mutate(self, component, diff):
            ...
    """
    def decorator(func: F) -> F:
        # Zero-overhead path - if disabled, return original function
        if not JIKOKU_ENABLED:
            return func

        # Determine if async or sync
        is_async = inspect.iscoroutinefunction(func)

        # Generate intent
        func_name = func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract metadata
            metadata: dict[str, Any] = {}
            if extract_metadata:
                try:
                    metadata = extract_metadata(args, kwargs)
                except Exception:
                    logger.debug("Jikoku metadata extraction failed", exc_info=True)

            # Generate intent from template or function name
            if intent_template:
                try:
                    intent = intent_template.format(**metadata, **kwargs)
                except (KeyError, ValueError):
                    intent = func_name
            else:
                intent = func_name

            # Trace the call
            async with jikoku_auto_span(category, intent, **metadata):
                return await func(*args, **kwargs)  # type: ignore

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract metadata
            metadata: dict[str, Any] = {}
            if extract_metadata:
                try:
                    metadata = extract_metadata(args, kwargs)
                except Exception:
                    logger.debug("Jikoku metadata extraction failed", exc_info=True)

            # Generate intent from template or function name
            if intent_template:
                try:
                    intent = intent_template.format(**metadata, **kwargs)
                except (KeyError, ValueError):
                    intent = func_name
            else:
                intent = func_name

            # Trace the call
            with jikoku_sync_span(category, intent, **metadata):
                return func(*args, **kwargs)

        return async_wrapper if is_async else sync_wrapper  # type: ignore

    return decorator


# ============================================================================
# PROVIDER-SPECIFIC INSTRUMENTATION
# ============================================================================

def jikoku_traced_provider(func: F) -> F:
    """
    Specialized decorator for LLM provider calls.

    Automatically extracts:
    - Provider name (from self)
    - Model name
    - Token counts (from response)
    - Cost (from response)
    - Prompt/completion lengths

    Usage:
        class AnthropicProvider:
            @jikoku_traced_provider
            async def complete(self, request: LLMRequest) -> LLMResponse:
                ...
    """
    if not JIKOKU_ENABLED:
        return func

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Extract provider info from self (first arg)
        provider_name = "unknown"
        model_name = "unknown"

        if args:
            self_obj = args[0]
            if hasattr(self_obj, '__class__'):
                provider_name = self_obj.__class__.__name__
            if hasattr(self_obj, 'model_id'):
                model_name = self_obj.model_id
            elif hasattr(self_obj, 'model'):
                model_name = self_obj.model

        # Extract request info
        request_info = {}
        if len(args) > 1:
            request = args[1]
            if hasattr(request, 'messages'):
                request_info['message_count'] = len(request.messages)
            if hasattr(request, 'model'):
                model_name = request.model

        # Start span
        intent = f"LLM call: {provider_name} ({model_name})"

        metadata = {
            'provider': provider_name,
            'model': model_name,
            **request_info
        }

        tracer = get_global_tracer()
        parent_id = _current_span_id.get()
        if parent_id:
            metadata['parent_span_id'] = parent_id

        span_id = tracer.start(
            category="api_call",
            intent=intent,
            **metadata
        )

        token = _current_span_id.set(span_id)
        start_time = time.time()

        try:
            # Execute the call
            response = await func(*args, **kwargs)

            # Extract response metadata
            response_metadata = {}
            if hasattr(response, 'usage'):
                usage = response.usage
                if hasattr(usage, 'input_tokens'):
                    response_metadata['input_tokens'] = usage.input_tokens
                if hasattr(usage, 'output_tokens'):
                    response_metadata['output_tokens'] = usage.output_tokens
                if hasattr(usage, 'total_tokens'):
                    response_metadata['total_tokens'] = usage.total_tokens

            if hasattr(response, 'cost'):
                response_metadata['cost_usd'] = response.cost

            # End span with response metadata
            tracer.end(span_id, **response_metadata)

            return response

        except Exception as e:
            # Log error metadata
            error_metadata = {
                'error': str(e),
                'error_type': type(e).__name__,
                'duration_sec': time.time() - start_time
            }
            tracer.end(span_id, **error_metadata)
            raise

        finally:
            _current_span_id.reset(token)

    return wrapper  # type: ignore


# ============================================================================
# SWARM-SPECIFIC INSTRUMENTATION
# ============================================================================

def extract_agent_metadata(args, kwargs):
    """Extract agent metadata from spawn_agent call"""
    metadata = {}

    # Try to get name from args or kwargs
    if args and len(args) > 1:
        metadata['agent_name'] = args[1]  # First arg after self
    elif 'name' in kwargs:
        metadata['agent_name'] = kwargs['name']

    # Try to get role
    if len(args) > 2:
        role = args[2]
        if hasattr(role, 'value'):
            metadata['role'] = role.value
        else:
            metadata['role'] = str(role)
    elif 'role' in kwargs:
        role = kwargs['role']
        if hasattr(role, 'value'):
            metadata['role'] = role.value
        else:
            metadata['role'] = str(role)

    return metadata


def extract_task_metadata(args, kwargs):
    """Extract task metadata from task operations"""
    metadata = {}

    # Try to get task ID
    if args and len(args) > 1:
        task = args[1]
        if hasattr(task, 'id'):
            metadata['task_id'] = task.id
        if hasattr(task, 'type'):
            metadata['task_type'] = task.type

    return metadata


# ============================================================================
# EVOLUTION-SPECIFIC INSTRUMENTATION
# ============================================================================

def extract_evolution_metadata(args, kwargs):
    """Extract evolution cycle metadata"""
    metadata = {}

    # Try to get iteration number
    if 'iteration' in kwargs:
        metadata['iteration'] = kwargs['iteration']
    elif args and len(args) > 1:
        metadata['iteration'] = args[1]

    return metadata


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_current_span_id() -> Optional[str]:
    """Get the current span ID from context (for manual nested spans)"""
    return _current_span_id.get()


def with_span_metadata(**metadata):
    """
    Add metadata to the current span (if one is active).

    Usage:
        async with jikoku_auto_span("execute.test", "Test"):
            result = await compute()
            with_span_metadata(result_size=len(result))
    """
    if not JIKOKU_ENABLED:
        return

    span_id = _current_span_id.get()
    if span_id:
        tracer = get_global_tracer()
        # Note: tracer.end() accepts extra metadata
        # For mid-span metadata, we'd need to extend JikokuTracer
        # For now, this is a placeholder for future enhancement
        pass
