"""Claude, through the Anthropic API.

This is the call PESTO has always made, moved here unchanged: the same request,
the same retries, the same reading of the answer. tests/anthropic_requests.py
holds it to that. The key is read in pesto.credentials and given to the official
client, which sends it to api.anthropic.com only.

One thing can be added to that call, and only when it is asked for: a model spec
may end in `@LEVEL` (`claude-opus-5@medium`), which sends the API's `effort`
(`output_config.effort`), the control Anthropic documents for how much a model
reasons. A spec without it sends no effort, so every request made before this
existed is still the request that is made, and the model runs at the API's own
default for it. A level is part of the canonical spec, so it is part of every
fingerprint and cache key.
"""
import inspect
import time

import anthropic
import requests

from ...config import LLM_INITIAL_DELAY, LLM_MAX_RETRIES
from .base import (LLMOverloadedError, LLMResult, Provider, STOP_REFUSAL)

VERBOSE_MODE = False

# The 1.x SDK dropped `temperature` from messages.create, while the API still
# takes it for the models that accept one; it then goes in the request body.
_SDK_TAKES_TEMPERATURE = "temperature" in inspect.signature(
    anthropic.resources.messages.Messages.create).parameters


# Models the API has refused a temperature for during this process.
_REFUSES_TEMPERATURE = set()

# The levels of `output_config.effort` (Anthropic's effort documentation). There
# is no level for "no reasoning": thinking is switched off by a different
# parameter, on some models only, so PESTO does not pretend one level covers it.
EFFORTS = ("low", "medium", "high", "xhigh", "max")

# Thinking is generated, billed and counted against max_tokens before the answer
# ends. With an effort set, the cap is the caller's max_tokens plus this room, so
# that a model asked to think more is not cut off before it answers. A ceiling,
# not a spend. Without an effort nothing is added: that request is unchanged.
THINKING_HEADROOM = {"low": 4_000, "medium": 8_000, "high": 16_000,
                     "xhigh": 32_000, "max": 64_000}

# Models the API answers "does not support the effort parameter" for (a 400,
# seen live on claude-haiku-4-5), by id and by the alias PESTO's arms use for it.
# PESTO's default arm reads with Opus and bands with this model, so a run-wide
# level has to know to leave it alone.
NO_EFFORT = ("claude-haiku-4-5", "haiku")

_SDK_TAKES_OUTPUT_CONFIG = "output_config" in inspect.signature(
    anthropic.resources.messages.Messages.create).parameters


def parse_model(model):
    """`claude-opus-5@high` -> ("claude-opus-5", "high"); no `@` -> (model, None).

    Raises ValueError for a level Claude has no such setting for."""
    model_id, _, option = (model or "").partition("@")
    model_id, option = model_id.strip(), option.strip().lower()
    if not model_id:
        raise ValueError("a model spec needs a model id, e.g. claude-opus-5")
    if "@" in (model or "") and not option:
        raise ValueError(f"{model!r} has an `@` and no reasoning level after it; "
                         f"use one of {', '.join(EFFORTS)}")
    if option == "none":
        raise ValueError(f"{model_id} has no reasoning-off level: Claude's effort "
                         f"runs {', '.join(EFFORTS)}")
    if option and model_id in NO_EFFORT:
        raise ValueError(f"{model_id} takes no reasoning level: the API refuses "
                         f"`effort` for it")
    if option and option not in EFFORTS:
        raise ValueError(f"reasoning level {option!r} is not one of "
                         f"{', '.join(EFFORTS)} for {model_id}")
    return model_id, (option or None)


class AnthropicProvider(Provider):
    name = "anthropic"
    label = "Anthropic"
    key_env = "ANTHROPIC_API_KEY"
    key_url = "console.anthropic.com"
    key_example = "sk-ant-..."
    host = "api.anthropic.com"
    sdk = "anthropic"

    def build_client(self, key):
        return anthropic.Anthropic(api_key=key)

    def takes_level(self, model):
        return parse_model(model)[0] not in NO_EFFORT

    def validate_model(self, model):
        parse_model(model)      # the id itself is the API's to judge, as always

    def canonical_model(self, model):
        """A bare spec stays itself, so every key made before levels existed
        still matches; a level is spelled out, lower-cased."""
        model_id, effort = parse_model(model)
        return f"{model_id}@{effort}" if effort else model_id

    def check_key(self, key):
        """True if Anthropic accepts the key. Lists models: costs nothing."""
        try:
            r = requests.get("https://api.anthropic.com/v1/models",
                             headers={"x-api-key": key,
                                      "anthropic-version": "2023-06-01"},
                             timeout=20)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def complete(self, model, prompt, temperature, max_tokens=4096):
        spec = model
        model, effort = parse_model(spec)
        if effort:
            max_tokens += THINKING_HEADROOM[effort]
        client_ = self.client()
        delay = LLM_INITIAL_DELAY

        # Opus from 4.x on rejects the temperature parameter with a 400, so those
        # calls run at the provider default. Two identical Opus runs can therefore
        # answer differently; that is sampling, not drift.
        # The API can also stop taking it for a model that did (claude-haiku-4-5
        # refuses it today), so a model that answers "temperature: Extra inputs
        # are not permitted" is remembered and run at the provider default.
        omit_temperature = (model.startswith("claude-opus-")
                            or model in _REFUSES_TEMPERATURE)

        for attempt in range(LLM_MAX_RETRIES):
            try:
                if VERBOSE_MODE:
                    print(f"INFO: Anthropic API, model {model}, "
                          f"attempt {attempt + 1}/{LLM_MAX_RETRIES}")
                kwargs = dict(model=model, max_tokens=max_tokens,
                              messages=[{"role": "user", "content": prompt}])
                if not omit_temperature:
                    if _SDK_TAKES_TEMPERATURE:
                        kwargs["temperature"] = temperature
                    else:
                        kwargs["extra_body"] = {"temperature": temperature}
                if effort:
                    if _SDK_TAKES_OUTPUT_CONFIG:
                        kwargs["output_config"] = {"effort": effort}
                    else:
                        kwargs["extra_body"] = {**kwargs.get("extra_body", {}),
                                                "output_config": {"effort": effort}}
                # The SDK refuses a long non-streamed request (a large max_tokens
                # can run past ten minutes), so those are streamed and collected.
                if max_tokens > 8192:
                    with client_.messages.stream(**kwargs) as stream:
                        message = stream.get_final_message()
                else:
                    message = client_.messages.create(**kwargs)
                usage = getattr(message, "usage", None)
                input_tokens = getattr(usage, "input_tokens", 0) or 0
                output_tokens = getattr(usage, "output_tokens", 0) or 0
                # Opus 5 thinks before it answers, so the first content block can be
                # a thinking block with no text. Text blocks are picked by type.
                spoken = "".join(getattr(b, "text", "") for b in message.content
                                 if getattr(b, "type", "text") == "text")
                # A safety classifier can end the turn with no content, and PubMed
                # corpora reach it. Reported, so a refusal is not read as a parse bug.
                stop_reason = getattr(message, "stop_reason", None)
                if stop_reason == STOP_REFUSAL:
                    print(f"WARNING: {model} refused to answer "
                          f"({input_tokens} input tokens)")
                # Anthropic's own words for stopping are PESTO's (end_turn,
                # max_tokens, refusal), so they pass through as they are.
                return LLMResult(text=spoken, input_tokens=input_tokens,
                                 output_tokens=output_tokens,
                                 stop_reason=stop_reason)
            except anthropic.APIStatusError as e:
                if e.status_code in (429, 500, 503, 529):
                    if attempt < LLM_MAX_RETRIES - 1:
                        print(f"WARNING: Anthropic API returned {e.status_code}. "
                              f"Retrying in {delay}s...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        raise LLMOverloadedError(
                            f"Anthropic API call failed after {LLM_MAX_RETRIES} "
                            f"attempts. Last error: {e}")
                elif (e.status_code == 400 and not omit_temperature
                      and "temperature" in str(e).lower()):
                    _REFUSES_TEMPERATURE.add(model)
                    print(f"WARNING: {model} no longer accepts `temperature`; "
                          f"its calls now run at the API default, so repeated "
                          f"runs can differ.")
                    return self.complete(spec, prompt, temperature,
                                         max_tokens - (THINKING_HEADROOM[effort]
                                                       if effort else 0))
                elif (e.status_code == 400 and effort
                      and "effort" in str(e).lower()):
                    # Not dropped and not retried without it: a run that asked
                    # for a level and got none would record one it did not have.
                    raise RuntimeError(
                        f"{model} does not accept a reasoning level "
                        f"(@{effort}): {e}") from e
                else:
                    raise

        return LLMResult(text=None)
