"""Claude, through the Anthropic API.

This is the call PESTO has always made, moved here unchanged: the same request,
the same retries, the same reading of the answer. tests/anthropic_requests.py
holds it to that. The key is read in pesto.credentials and given to the official
client, which sends it to api.anthropic.com only.
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
                    return self.complete(model, prompt, temperature, max_tokens)
                else:
                    raise

        return LLMResult(text=None)
