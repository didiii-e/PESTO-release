"""GPT, through the OpenAI Responses API.

Written against the current API reference (platform.openai.com/docs), not
against what an older SDK happens to expose: `client.responses.create` with
`reasoning.effort` and `max_output_tokens`. The key is read in pesto.credentials
and given to the official client, which sends it to api.openai.com only.

Model specs look like `openai:gpt-6-luna` or `openai:gpt-6.1-sol@high`; the part
after `@` is the reasoning effort. It is always sent explicitly, because the API
default differs by model and a result should not depend on it. It is part of the
model string, so it is part of every fingerprint and cache key built from it.

These models are candidates to be evaluated. Nothing here says they match the
Claude models PESTO was validated with.
"""
import time
from dataclasses import dataclass

import requests

from ...config import LLM_INITIAL_DELAY, LLM_MAX_RETRIES
from .base import (LLMOverloadedError, LLMResult, Provider, STOP_END,
                   STOP_MAX_TOKENS, STOP_REFUSAL)

VERBOSE_MODE = False

EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")

# Statuses worth another try: the request did not fail on its merits.
_RETRY_STATUS = (408, 409, 429, 500, 502, 503, 504)

MIN_SDK = "2.47"   # first release that types the `max` reasoning effort


@dataclass(frozen=True)
class Profile:
    """What PESTO knows about one OpenAI model."""
    default_effort: str     # used when the spec names none
    efforts: tuple          # the efforts the model accepts (OpenAI model pages)
    max_output: int = 128_000


# The models being evaluated. Add a model here to give it a default effort;
# any other model can still be used by naming its effort in the spec.
PROFILES = {
    # Fast, high-volume role: low reasoning for latency.
    "gpt-6-luna": Profile("low", ("none", "low", "medium", "high", "xhigh", "max")),
    # Judgment-heavy role: moderate reasoning. Does not accept `none`.
    "gpt-6.1-sol": Profile("medium", ("low", "medium", "high", "xhigh", "max")),
}

# Reasoning tokens are generated, billed, and counted against max_output_tokens
# before the first visible token. Without room for them a call can end "incomplete"
# with no answer at all, so the cap is the caller's max_tokens plus this headroom.
# It is a ceiling, not a spend: only tokens actually generated are billed.
THINKING_HEADROOM = {"none": 0, "low": 8_000, "medium": 16_000,
                     "high": 32_000, "xhigh": 64_000, "max": 96_000}


def parse_model(model):
    """`gpt-6.1-sol@high` -> ("gpt-6.1-sol", "high"). Raises ValueError."""
    model_id, _, option = (model or "").partition("@")
    model_id, option = model_id.strip(), option.strip().lower()
    if not model_id:
        raise ValueError("an OpenAI model spec needs a model id, e.g. openai:gpt-6-luna")
    profile = PROFILES.get(model_id)
    if profile is None:
        if not option:
            raise ValueError(
                f"openai:{model_id} has no built-in profile, so its reasoning effort "
                f"must be given explicitly, e.g. openai:{model_id}@medium "
                f"(known models: {', '.join(sorted(PROFILES))})")
        if option not in EFFORTS:
            raise ValueError(f"reasoning effort {option!r} is not one of "
                             f"{', '.join(EFFORTS)}")
        return model_id, option
    effort = option or profile.default_effort
    if effort not in profile.efforts:
        raise ValueError(
            f"{model_id} does not accept reasoning effort {effort!r}; "
            f"it accepts {', '.join(profile.efforts)}")
    return model_id, effort


def _retry_after(error):
    """Seconds the server asked us to wait, if it said so (capped)."""
    try:
        return min(float(error.response.headers.get("retry-after", "")), 60.0)
    except (AttributeError, TypeError, ValueError):
        return 0.0


class OpenAIProvider(Provider):
    name = "openai"
    label = "OpenAI"
    key_env = "OPENAI_API_KEY"
    key_url = "platform.openai.com/api-keys"
    key_example = "sk-..."
    host = "api.openai.com"
    sdk = "openai"

    # ---- the SDK is an optional extra: imported when first needed --------
    @staticmethod
    def _sdk():
        try:
            import openai
        except ImportError:
            raise RuntimeError(
                "OpenAI models need the openai package: "
                f"pip install 'pesto-genetics[openai]'  (openai>={MIN_SDK})")
        return openai

    def build_client(self, key):
        openai = self._sdk()
        # One retry policy, ours: the SDK's own retries would multiply with it.
        client = openai.OpenAI(api_key=key, max_retries=0)
        if not hasattr(client, "responses"):
            raise RuntimeError(
                f"openai {getattr(openai, '__version__', '?')} has no Responses "
                f"API; install openai>={MIN_SDK}")
        return client

    def validate_model(self, model):
        parse_model(model)

    def canonical_model(self, model):
        model_id, effort = parse_model(model)
        return f"{model_id}@{effort}"

    def check_key(self, key):
        """True if OpenAI accepts the key. Lists models: costs nothing."""
        try:
            r = requests.get("https://api.openai.com/v1/models",
                             headers={"Authorization": f"Bearer {key}"}, timeout=20)
            return r.status_code == 200
        except requests.RequestException:
            return False

    # ---- one call ---------------------------------------------------------
    def request(self, model, prompt, temperature, max_tokens):
        """The arguments of responses.create for this call."""
        model_id, effort = parse_model(model)
        profile = PROFILES.get(model_id)
        ceiling = profile.max_output if profile else 128_000
        kwargs = dict(
            model=model_id,
            input=[{"role": "user", "content": prompt}],
            reasoning={"effort": effort},
            max_output_tokens=min(max_tokens + THINKING_HEADROOM[effort], ceiling),
            # A single-turn call has nothing to continue: do not keep it server-side.
            store=False,
        )
        # With any reasoning the API takes no sampling parameters (it rejects them);
        # only `none` leaves temperature meaningful.
        if effort == "none":
            kwargs["temperature"] = temperature
        return kwargs

    def complete(self, model, prompt, temperature, max_tokens=4096):
        openai = self._sdk()
        client_ = self.client()
        kwargs = self.request(model, prompt, temperature, max_tokens)
        label = f"openai:{model}"
        delay = LLM_INITIAL_DELAY
        last = None

        for attempt in range(LLM_MAX_RETRIES):
            wait = delay
            try:
                if VERBOSE_MODE:
                    print(f"INFO: OpenAI API, model {model}, "
                          f"attempt {attempt + 1}/{LLM_MAX_RETRIES}")
                response = client_.responses.create(**kwargs)
                if getattr(response, "status", None) == "failed":
                    last = _describe_failure(response)
                else:
                    return self.read(response, label)
            except openai.APIStatusError as e:
                if e.status_code not in _RETRY_STATUS:
                    raise
                # Out of credit is not a busy server: waiting will not fix it.
                if getattr(e, "code", None) == "insufficient_quota":
                    raise
                last = e
                wait = max(delay, _retry_after(e))
            except openai.APIConnectionError as e:   # includes timeouts
                last = e

            if attempt < LLM_MAX_RETRIES - 1:
                print(f"WARNING: OpenAI API call failed ({last}). "
                      f"Retrying in {wait:g}s...")
                time.sleep(wait)
                delay *= 2
        raise LLMOverloadedError(
            f"OpenAI API call failed after {LLM_MAX_RETRIES} attempts. "
            f"Last error: {last}")

    def read(self, response, label):
        """A Responses API response, as an LLMResult."""
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        reasoning_tokens = getattr(getattr(usage, "output_tokens_details", None),
                                   "reasoning_tokens", 0) or 0
        text = getattr(response, "output_text", None) or ""

        refused = any(getattr(part, "type", None) == "refusal"
                      for item in (getattr(response, "output", None) or ())
                      if getattr(item, "type", None) == "message"
                      for part in (getattr(item, "content", None) or ()))

        status = getattr(response, "status", None)
        if status == "incomplete":
            reason = getattr(getattr(response, "incomplete_details", None),
                             "reason", None)
            if reason == "max_output_tokens":
                stop = STOP_MAX_TOKENS
            elif reason == "content_filter":
                stop = STOP_REFUSAL
            else:
                stop = f"incomplete:{reason}"
        elif refused:
            stop = STOP_REFUSAL
        elif status in ("completed", None):
            stop = STOP_END
        else:
            stop = str(status)

        if stop == STOP_REFUSAL:
            print(f"WARNING: {label} refused to answer ({input_tokens} input tokens)")
        return LLMResult(text=text, input_tokens=input_tokens,
                         output_tokens=output_tokens, stop_reason=stop,
                         reasoning_tokens=reasoning_tokens)


def _describe_failure(response):
    error = getattr(response, "error", None)
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    return f"response failed ({code}): {message}" if (code or message) \
        else "response failed"
