"""A model the API stops accepting `temperature` for: the call is retried without
it, and the model is remembered. No network, no key.

claude-haiku-4-5 began answering a request that carries a temperature with
400 `temperature: Extra inputs are not permitted` (Opus 4 and later always did,
and is never sent one). Every Haiku call of a run, the sieve among them, failed
on it. This pins what happens now: one retry without the parameter, a warning
that says repeated runs can differ, the model remembered for the rest of the
process, and every other 400 still raised at once.

  python3 tests/anthropic_temperature.py
"""
from __future__ import annotations

import contextlib
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("PESTO_PROJECT_ROOT", os.path.join(HERE, "fixtures"))

import anthropic_requests as ar  # noqa: E402
from pesto.services.providers import anthropic_provider  # noqa: E402

RESULTS = []


def check(fn):
    RESULTS.append(fn)
    return fn


def refusals():
    """The set of models the API has refused a temperature for."""
    return anthropic_provider._REFUSES_TEMPERATURE


@contextlib.contextmanager
def fresh_refusals():
    refusals().clear()
    try:
        yield
    finally:
        refusals().clear()


def temperature_refused():
    return ar.status_error(400, "temperature: Extra inputs are not permitted")


@check
def a_model_that_refuses_temperature_is_retried_without_it_and_remembered():
    ask = dict(prompt="p", model="claude-haiku-4-5", temperature=0.0)
    with fresh_refusals():
        first = ar.scenario([temperature_refused(), ar.reply([ar.text_block("ok")])], **ask)
        assert first["result"]["text"] == "ok" and "raised" not in first, first
        sent = [c[1] for c in first["calls"]]
        assert len(sent) == 2, sent
        assert sent[0]["extra_body"] == {"temperature": 0.0}        # the request is unchanged
        assert "extra_body" not in sent[1] and "temperature" not in sent[1], sent[1]
        assert sent[0]["messages"] == sent[1]["messages"] and sent[0]["model"] == sent[1]["model"]
        assert "no longer accepts `temperature`" in first["stdout"]
        assert "claude-haiku-4-5" in refusals()
        # Remembered: the next call does not send it, so it does not fail first.
        second = ar.scenario([ar.reply([ar.text_block("again")])], **ask)
        assert [c[1].get("extra_body") for c in second["calls"]] == [None], second["calls"]
        assert "no longer accepts" not in second["stdout"]
        # And only that model: another that takes a temperature still gets one.
        other = ar.scenario([ar.reply([ar.text_block("x")])], prompt="p",
                            model="claude-sonnet-4-6", temperature=0.0)
        assert other["calls"][0][1]["extra_body"] == {"temperature": 0.0}


@check
def other_bad_requests_are_still_raised_at_once():
    with fresh_refusals():
        out = ar.scenario([ar.status_error(400, "max_tokens: too large")], prompt="p",
                          model="claude-haiku-4-5", temperature=0.0)
        assert out["raised"]["type"] == "APIStatusError" and len(out["calls"]) == 1, out
        assert not refusals()


@check
def a_refusal_that_persists_is_raised_not_looped():
    with fresh_refusals():
        # Refuses even without a temperature: the second 400 is the caller's problem.
        out = ar.scenario([temperature_refused(), temperature_refused()], prompt="p",
                          model="claude-haiku-4-5", temperature=0.0)
        assert out["raised"]["type"] == "APIStatusError" and len(out["calls"]) == 2, out


def main():
    failed = 0
    for fn in RESULTS:
        try:
            fn()
            print(f"ok    {fn.__name__}")
        except Exception:                                    # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
