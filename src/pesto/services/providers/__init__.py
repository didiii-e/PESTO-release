"""Model providers, and how a model spec picks one.

A model is named by a spec string:

    claude-haiku-4-5            a bare name is Anthropic (every spec written before
                                there were providers is a bare name, and stays so)
    anthropic:claude-opus-5     the same, explicit
    openai:gpt-6-luna           provider prefix, then that provider's own model id
    openai:gpt-6.1-sol@high     a provider may take options after the id

Only the prefix is read here. What follows it belongs to the provider.
"""
from collections import namedtuple

from .anthropic_provider import AnthropicProvider
from .base import (LLMOverloadedError, LLMResult, MissingAPIKeyError, Provider,
                   STOP_END, STOP_MAX_TOKENS, STOP_REFUSAL)
from .openai_provider import OpenAIProvider

DEFAULT_PROVIDER = "anthropic"

_PROVIDERS = {p.name: p for p in (AnthropicProvider(), OpenAIProvider())}

# A spec split into the provider and the part the provider understands.
Resolved = namedtuple("Resolved", "provider model")


def names():
    return sorted(_PROVIDERS)


def get(name):
    """The provider object for a provider name."""
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise ValueError(f"unknown provider {name!r}; known: {', '.join(names())}")


def resolve(spec):
    """Split a model spec into its provider and the provider's own model string.

    Raises ValueError for a prefix that is not a provider, so a typo fails
    before any call is made rather than being sent to the wrong API.
    """
    spec = (spec or "").strip()
    prefix, colon, rest = spec.partition(":")
    if colon and prefix.lower() in _PROVIDERS:
        if not rest:
            raise ValueError(f"model spec {spec!r} has no model after the provider")
        return Resolved(_PROVIDERS[prefix.lower()], rest)
    if colon:
        raise ValueError(
            f"unknown provider {prefix!r} in model spec {spec!r}; "
            f"known: {', '.join(names())}")
    return Resolved(_PROVIDERS[DEFAULT_PROVIDER], spec)


def validate(spec):
    """Check a spec without calling anything. Returns it resolved."""
    resolved = resolve(spec)
    resolved.provider.validate_model(resolved.model)
    return resolved


def canonical(spec):
    """A spec written one way only, for cache keys and records.

    `claude-haiku-4-5` stays bare and `anthropic:claude-opus-5` loses its prefix, so
    the keys of every Anthropic run made before there were providers still
    match. Other providers keep the prefix, and spell out their options:
    `openai:gpt-6-luna` is `openai:gpt-6-luna@low`.
    """
    resolved = resolve(spec)
    model = resolved.provider.canonical_model(resolved.model)
    if resolved.provider.name == DEFAULT_PROVIDER:
        return model
    return f"{resolved.provider.name}:{model}"


LEVELS = ("none", "low", "medium", "high", "max")


def with_effort(spec, level):
    """`spec` carrying the reasoning `level`, unless it already names its own.

    This is how one `--reasoning LEVEL` reaches every model of a run: each
    provider reads the `@level` its own way (OpenAI's `reasoning.effort`,
    Claude's `output_config.effort`). A level written in the spec is a more
    specific instruction than a default, so it is left alone. So is a model
    with no reasoning level to set (Claude Haiku 4.5): it runs as it always
    did, and its spec, and so its fingerprint, say so. With no level the
    spec comes back untouched, which is what keeps every run made without the
    flag identical to what it was. Whether the model can take the level is for
    `validate` to say; this only writes it.
    """
    if not level:
        return spec
    if level not in LEVELS:
        raise ValueError(f"reasoning level {level!r} is not one of {', '.join(LEVELS)}")
    resolved = resolve(spec)            # a bad provider prefix fails here
    if "@" in spec or not resolved.provider.takes_level(resolved.model):
        return spec
    return f"{spec}@{level}"


def auth_failure(exc):
    """The provider whose SDK raised this authentication error, else None."""
    if type(exc).__name__ != "AuthenticationError":
        return None
    root = type(exc).__module__.split(".")[0]
    return next((p for p in _PROVIDERS.values() if p.sdk == root), None)


def providers_for(specs):
    """The providers that a set of model specs will call, in a stable order."""
    seen = {}
    for spec in specs:
        if spec:
            provider = resolve(spec).provider
            seen[provider.name] = provider
    return [seen[name] for name in sorted(seen)]


def missing_keys(specs):
    """The providers a set of model specs needs a key for and does not have.

    Only providers that are actually called count: a run on Anthropic models
    needs no OpenAI key, and the other way round.
    """
    return [p for p in providers_for(specs) if not p.api_key()]


def reset_clients():
    for provider in _PROVIDERS.values():
        provider.reset()
