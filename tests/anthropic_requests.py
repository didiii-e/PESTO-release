"""The exact Anthropic behaviour of the LLM layer, checked without a network.

Every PESTO model call ends in one function. This test pins what that function
does on the Anthropic side: the arguments of the request, whether the call is
streamed, which models get no temperature, how the answer is read out of the
content blocks, what is retried and for how long, what is printed, which error
comes out, and the token counts that go to the cost record.

A fake SDK client stands in for api.anthropic.com. The recording in
tests/fixtures/anthropic_requests.json was made from the code BEFORE the layer
was split into providers, so a refactor that moves this logic has to reproduce
it to the letter.

  python3 tests/anthropic_requests.py            check against the recording
  python3 tests/anthropic_requests.py --update   record it again (deliberate)
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "fixtures", "anthropic_requests.json")
os.environ.setdefault("PESTO_PROJECT_ROOT", os.path.join(HERE, "fixtures"))

import anthropic  # noqa: E402
import httpx  # noqa: E402

from pesto import cost  # noqa: E402
from pesto import credentials  # noqa: E402
from pesto.services import llm_service  # noqa: E402

KEY = "sk-ant-test-key"


def status_error(code, message="boom"):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIStatusError(message, response=httpx.Response(code, request=req),
                                    body=None)


def text_block(text):
    return types.SimpleNamespace(type="text", text=text)


def reply(blocks, input_tokens=11, output_tokens=7, stop_reason="end_turn", usage=True):
    return types.SimpleNamespace(
        content=blocks, stop_reason=stop_reason,
        usage=(types.SimpleNamespace(input_tokens=input_tokens,
                                     output_tokens=output_tokens) if usage else None))


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class FakeMessages:
    def __init__(self, script, calls):
        self.script, self.calls = list(script), calls

    def _next(self, how, kwargs):
        self.calls.append([how, json.loads(json.dumps(kwargs))])
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def create(self, **kwargs):
        return self._next("create", kwargs)

    def stream(self, **kwargs):
        return FakeStream(self._next("stream", kwargs))


def set_sdk_flag(value):
    """Whether the installed SDK takes `temperature` as an argument. It is read
    once at import, so each shape of request is forced here."""
    for name in ("pesto.services.llm_service",
                 "pesto.services.providers.anthropic_provider"):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        if hasattr(module, "_SDK_TAKES_TEMPERATURE"):
            module._SDK_TAKES_TEMPERATURE = value


def reset_clients():
    llm_service._client = None
    hook = getattr(llm_service, "reset_clients", None)
    if hook:
        hook()


def scenario(script, *, sdk_takes_temperature=False, key=KEY, **call):
    """One call through the layer; everything observable about it."""
    calls, built, sleeps = [], [], []

    def factory(**kwargs):
        built.append({"api_key_is_the_key": kwargs.get("api_key") == KEY,
                      "other_args": sorted(k for k in kwargs if k != "api_key")})
        return types.SimpleNamespace(messages=FakeMessages(script, calls))

    real_client, real_sleep = anthropic.Anthropic, time.sleep
    old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    credentials._loaded = True          # never read a .env during the test
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key
    anthropic.Anthropic = factory
    time.sleep = sleeps.append
    set_sdk_flag(sdk_takes_temperature)
    reset_clients()
    out, said = {}, io.StringIO()
    try:
        with contextlib.redirect_stdout(said), cost.capturing() as spent:
            try:
                out["result"] = llm_service.call_llm_with_usage(**call)
            except Exception as exc:                      # noqa: BLE001
                out["raised"] = {"type": type(exc).__name__, "message": str(exc)}
        out["cost_rows"] = spent.rows
    finally:
        anthropic.Anthropic, time.sleep = real_client, real_sleep
        os.environ.pop("ANTHROPIC_API_KEY", None)
        if old_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = old_key
        reset_clients()
    out.update(calls=calls, clients_built=built, sleeps=sleeps, stdout=said.getvalue())
    return out


def record():
    haiku = "claude-haiku-4-5"
    opus = "claude-opus-5"
    ask = dict(prompt="PROMPT", temperature=0.0)
    out = {}
    for flag in (False, True):
        out[f"haiku_basic[sdk_takes_temperature={flag}]"] = scenario(
            [reply([text_block("hello")])], sdk_takes_temperature=flag, model=haiku, **ask)
    out["haiku_temperature_passed_through"] = scenario(
        [reply([text_block("x")])], model=haiku, prompt="P", temperature=0.7)
    out["default_model_when_omitted"] = scenario(
        [reply([text_block("x")])], prompt="P")
    out["opus_sends_no_temperature"] = scenario(
        [reply([text_block("x")])], model=opus, **ask)
    out["opus_sends_no_temperature[sdk_takes_temperature=True]"] = scenario(
        [reply([text_block("x")])], sdk_takes_temperature=True, model=opus, **ask)
    out["thinking_block_is_not_text"] = scenario(
        [reply([types.SimpleNamespace(type="thinking", thinking="hmm"),
                text_block("answer "), text_block("two")])], model=opus, **ask)
    out["block_without_type_counts_as_text"] = scenario(
        [reply([types.SimpleNamespace(text="plain")])], model=haiku, **ask)
    out["max_tokens_default_is_4096"] = scenario(
        [reply([text_block("x")])], model=haiku, **ask)
    out["max_tokens_at_8192_is_not_streamed"] = scenario(
        [reply([text_block("x")])], model=haiku, max_tokens=8192, **ask)
    out["max_tokens_above_8192_is_streamed"] = scenario(
        [reply([text_block("x")])], model=opus, max_tokens=20000, **ask)
    out["max_tokens_reported_as_stop_reason"] = scenario(
        [reply([text_block("cut")], stop_reason="max_tokens")],
        model=opus, max_tokens=64, **ask)
    out["refusal_is_reported"] = scenario(
        [reply([], input_tokens=900, output_tokens=0, stop_reason="refusal")],
        model=opus, **ask)
    out["usage_missing_counts_as_zero"] = scenario(
        [reply([text_block("x")], usage=False)], model=haiku, **ask)
    out["retry_429_then_answer"] = scenario(
        [status_error(429), reply([text_block("ok")])], model=haiku, **ask)
    out["retry_500_503_529_then_answer"] = scenario(
        [status_error(500), status_error(503), reply([text_block("ok")])],
        model=haiku, **ask)
    out["three_529_is_overloaded"] = scenario(
        [status_error(529, "overloaded"), status_error(529, "overloaded"),
         status_error(529, "overloaded")], model=haiku, **ask)
    out["400_is_raised_at_once"] = scenario(
        [status_error(400, "bad request")], model=haiku, **ask)
    out["401_is_raised_at_once"] = scenario(
        [status_error(401, "invalid x-api-key")], model=haiku, **ask)
    out["missing_key"] = scenario([], key=None, model=haiku, **ask)
    out["call_llm_returns_text_only"] = None
    return out


def recorded_text_only():
    """call_llm is the text-only form of the same call."""
    result = scenario([reply([text_block("just text")])], model="claude-haiku-4-5",
                      prompt="P", temperature=0.0)["result"]
    return result["text"]


def checks(now, golden):
    failed = 0
    for name in sorted(set(golden) | set(now)):
        same = now.get(name) == golden.get(name)
        failed += not same
        print(("ok    " if same else "FAIL  ") + name)
        if not same:
            print("   expected:", json.dumps(golden.get(name), sort_keys=True)[:1500])
            print("   got:     ", json.dumps(now.get(name), sort_keys=True)[:1500])
    return failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()
    now = json.loads(json.dumps(record(), sort_keys=True, default=str))
    now["call_llm_returns_text_only"] = recorded_text_only()
    if args.update:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w", encoding="utf-8") as fh:
            json.dump(now, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print(f"recorded {len(now)} scenarios in {GOLDEN}")
        return 0
    with open(GOLDEN, encoding="utf-8") as fh:
        golden = json.load(fh)
    failed = checks(now, golden)
    print(f"{len(now) - failed}/{len(now)} unchanged" if not failed
          else f"{failed} CHANGED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
