"""Every model call in PESTO lands here.

The pipeline hands over a prompt and a model spec and gets back text and token
counts. How the call is made, and to whom, is the business of a provider adapter
(pesto.services.providers); this module only picks the adapter from the spec and
records the cost. The signatures below are the ones the rest of PESTO has always
used, and a bare model name still means Anthropic.
"""
from typing import Any, Dict, Optional

from . import providers
from .providers import LLMOverloadedError, MissingAPIKeyError  # noqa: F401  (re-exported)

DEFAULT_MODEL = "claude-haiku-4-5"


def reset_clients():
    """Drop the cached API clients, so the next call reads its key again."""
    providers.reset_clients()


def call_llm_with_usage(prompt: str, model: str = DEFAULT_MODEL,
                        temperature: float = 0.0,
                        agent_name: Optional[str] = None,
                        max_tokens: Optional[int] = None) -> Dict[str, Any]:
    """One call. Returns the text and the token counts.

    `agent_name` is accepted for the callers that pass it and is not used.
    """
    provider, provider_model = providers.resolve(model)
    result = provider.complete(provider_model, prompt, temperature,
                               max_tokens=max_tokens or 4096)
    from ..cost import record
    record(model, result.input_tokens, result.output_tokens)
    return result.as_dict()


def call_llm(prompt: str, model: str = DEFAULT_MODEL,
             temperature: float = 0.0, agent_name: Optional[str] = None) -> str:
    """One call, returning only the text."""
    return call_llm_with_usage(prompt, model, temperature, agent_name)["text"]
