"""`--reasoning LEVEL`: one reasoning level for a run, passed down to OpenAI or Claude.

No network and no key. The Anthropic side runs through the fake SDK client of
tests/anthropic_requests.py, so what is checked is the request that would be sent.

What has to hold:
  * with no level, nothing changes: no `effort` is sent to Claude, no model spec
    is rewritten, no fingerprint moves (tests/anthropic_requests.py and
    tests/replay.py hold the rest of that line);
  * a level reaches every model the run calls, the arm's own defaults included,
    and a level written in a model's own spec wins over the flag;
  * Claude gets it as `output_config.effort`, with room for the thinking, and a
    refusal by the API is raised, never retried without the level;
  * a model that cannot take the level is refused before anything is fetched.

  python3 tests/reasoning_level.py
"""
from __future__ import annotations

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("PESTO_PROJECT_ROOT", os.path.join(HERE, "fixtures"))

import anthropic_requests as ar  # noqa: E402  (the fake SDK client)

from pesto import cli, config, harness  # noqa: E402
from pesto.flow import arms  # noqa: E402
from pesto.services import providers  # noqa: E402
from pesto.services.providers import anthropic_provider as ap  # noqa: E402
from pesto.services.providers import openai_provider as oa  # noqa: E402

RESULTS = []


def check(fn):
    RESULTS.append(fn)
    return fn


def raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type as e:
        return e
    raise AssertionError(f"{fn.__name__} did not raise {exc_type.__name__}")


def parse(*argv):
    return cli.build_parser().parse_args(["--gene", "G", "--phenotype", "p", *argv])


def models_of(args, arm_name="abstracts"):
    reader, worker = cli.pick_models(args.model, args.model_fast or args.model)
    return cli.fit(arms.get(arm_name), args, reader, worker).models()


def call(model, script=None, **kw):
    return ar.scenario(script or [ar.reply([ar.text_block("hi")])],
                       model=model, prompt="P", temperature=0.0, **kw)


# ============================================================ the Claude adapter
@check
def a_claude_spec_without_a_level_is_what_it_always_was():
    for spec in ("claude-opus-5", "claude-haiku-4-5", "opus5", "haiku"):
        assert ap.parse_model(spec) == (spec, None)
        assert providers.canonical(spec) == spec
    assert providers.canonical("anthropic:claude-opus-5") == "claude-opus-5"


@check
def a_level_is_part_of_the_canonical_spec():
    assert providers.canonical("claude-opus-5@High") == "claude-opus-5@high"
    assert providers.canonical("anthropic:claude-opus-5@low") == "claude-opus-5@low"
    assert providers.canonical("opus5@max") == "opus5@max"
    assert providers.canonical("claude-opus-5@high") != providers.canonical("claude-opus-5")


@check
def claude_has_no_off_level_and_bad_levels_are_refused():
    assert "no reasoning-off level" in str(raises(ValueError, providers.validate, "claude-opus-5@none"))
    assert "not one of" in str(raises(ValueError, providers.validate, "claude-opus-5@turbo"))
    assert "no reasoning level" in str(raises(ValueError, providers.validate, "claude-opus-5@"))
    for level in ap.EFFORTS:
        providers.validate(f"claude-opus-5@{level}")


@check
def no_level_sends_no_effort_and_no_extra_room():
    out = call("claude-opus-5")
    kwargs = out["calls"][0][1]
    assert "output_config" not in kwargs and "extra_body" not in kwargs
    assert kwargs["max_tokens"] == 4096 and out["calls"][0][0] == "create"


@check
def a_level_is_sent_as_effort_with_room_to_think():
    for level, room in ap.THINKING_HEADROOM.items():
        out = call(f"claude-opus-5@{level}")
        how, kwargs = out["calls"][0]
        assert kwargs["output_config"] == {"effort": level}, (level, kwargs)
        assert kwargs["model"] == "claude-opus-5"            # the id, never the `@`
        assert kwargs["max_tokens"] == 4096 + room
        assert how == ("stream" if 4096 + room > 8192 else "create")
        assert out["result"]["text"] == "hi"


@check
def the_level_travels_in_the_body_when_the_sdk_cannot_take_it():
    real = ap._SDK_TAKES_OUTPUT_CONFIG
    ap._SDK_TAKES_OUTPUT_CONFIG = False
    try:
        out = call("claude-sonnet-4-5@low", sdk_takes_temperature=False)
    finally:
        ap._SDK_TAKES_OUTPUT_CONFIG = real
    kwargs = out["calls"][0][1]
    assert "output_config" not in kwargs
    assert kwargs["extra_body"] == {"temperature": 0.0, "output_config": {"effort": "low"}}


@check
def a_refused_level_is_raised_and_never_retried_without_it():
    # a model PESTO does not know to refuse: the API's own 400 is the backstop
    out = call("claude-sonnet-4-5@high",
               [ar.status_error(400, "This model does not support the effort parameter.")])
    assert len(out["calls"]) == 1
    assert out["raised"]["type"] == "RuntimeError", out
    assert "does not accept a reasoning level (@high)" in out["raised"]["message"]


@check
def the_temperature_retry_keeps_the_level_and_the_room():
    out = call("claude-sonnet-4-5@medium",
               [ar.status_error(400, "temperature: Extra inputs are not permitted"),
                ar.reply([ar.text_block("ok")])])
    first, second = out["calls"][0][1], out["calls"][1][1]
    assert out["result"]["text"] == "ok"
    assert "temperature" in first["extra_body"] and "extra_body" not in second
    assert first["output_config"] == second["output_config"] == {"effort": "medium"}
    assert first["max_tokens"] == second["max_tokens"] == 4096 + ap.THINKING_HEADROOM["medium"]
    ap._REFUSES_TEMPERATURE.discard("claude-sonnet-4-5")


@check
def a_level_leaves_the_pricing_and_the_cost_record_under_the_spec():
    out = call("claude-opus-5@high")
    assert out["cost_rows"][0]["model"] == "claude-opus-5@high"
    assert config.price_usd("claude-opus-5@high", 1_000_000, 0) == 5.00


# ===================================================================== spec level
@check
def with_effort_writes_a_default_and_never_overrides():
    assert providers.with_effort("opus5", None) == "opus5"
    assert providers.with_effort("opus5", "high") == "opus5@high"
    assert providers.with_effort("claude-opus-5@low", "high") == "claude-opus-5@low"
    assert providers.with_effort("openai:gpt-6-luna", "high") == "openai:gpt-6-luna@high"
    assert providers.with_effort("openai:gpt-6.1-sol@medium", "max") == "openai:gpt-6.1-sol@medium"
    raises(ValueError, providers.with_effort, "mistral:x", "high")      # a bad prefix
    raises(ValueError, providers.with_effort, "opus5", "turbo")


@check
def an_alias_keeps_its_level_when_it_is_resolved():
    assert harness.resolve_model("opus5@high") == "claude-opus-5@high"
    assert harness.resolve_model("haiku") == "claude-haiku-4-5"
    assert harness.resolve_model("openai:gpt-6-luna@low") == "openai:gpt-6-luna@low"
    assert harness.MODELS == {"haiku": "claude-haiku-4-5", "opus": "claude-opus-5",
                              "opus5": "claude-opus-5"}              # fingerprints hash these


@check
def openai_takes_the_shared_levels_as_its_effort():
    for level in ("low", "medium", "high", "max"):
        spec = providers.with_effort("openai:gpt-6.1-sol", level)
        resolved = providers.resolve(spec)
        assert resolved.provider.request(resolved.model, "p", 0.0, 100)["reasoning"] == {"effort": level}
    providers.validate("openai:gpt-6-luna@none")
    assert "does not accept" in str(raises(ValueError, providers.validate, "openai:gpt-6.1-sol@none"))


# ===================================================================== the CLI
@check
def the_flag_takes_the_shared_levels_only():
    assert parse().reasoning is None
    for level in providers.LEVELS:
        assert parse("--reasoning", level).reasoning == level
    raises(SystemExit, lambda: parse("--reasoning", "xhigh"))      # provider names go after `@`


@check
def without_the_flag_every_arm_is_exactly_what_it_was():
    for name in arms.ARMS:
        arm = arms.get(name)
        assert arm.using(reasoning=None).fingerprint() == arm.fingerprint()
        assert arm.using(reasoning=None).models() == arm.models()
    assert models_of(parse()) == ["haiku", "opus5"]


@check
def a_level_reaches_every_model_the_arm_calls_and_moves_the_fingerprint():
    plain = arms.get("abstracts")
    leveled = plain.using(reasoning="low")
    # Opus takes the level; Haiku has none to take, so it is left as it was
    assert leveled.models() == ["haiku", "opus5@low"]
    assert leveled.fingerprint() != plain.fingerprint()
    assert plain.using(reasoning="low").fingerprint() == leveled.fingerprint()
    assert plain.using(reasoning="high").fingerprint() != leveled.fingerprint()
    # the trait arm and the others too: no block that can take it is left without it
    for name in arms.ARMS:
        for spec in arms.get(name).using(reasoning="medium").models():
            assert spec.endswith("@medium") or spec == "haiku", (name, spec)


@check
def a_level_in_a_models_own_spec_wins_over_the_flag():
    args = parse("--reasoning", "low", "--model", "openai:gpt-6.1-sol@high",
                 "--model-fast", "openai:gpt-6-luna")
    assert models_of(args) == ["openai:gpt-6-luna@low", "openai:gpt-6.1-sol@high"]


@check
def the_flag_goes_on_the_models_a_model_flag_names_too():
    args = parse("--reasoning", "medium", "--model", "openai:gpt-6.1-sol",
                 "--model-fast", "openai:gpt-6-luna")
    assert models_of(args) == ["openai:gpt-6-luna@medium", "openai:gpt-6.1-sol@medium"]


@check
def the_router_and_open_targets_get_the_level_too():
    plain = parse()
    assert cli.router_model_of(plain) == arms.ROUTER_MODEL
    assert cli.ot_specs(plain) == (None, None)               # the published defaults
    lv = parse("--reasoning", "high")
    assert cli.router_model_of(lv) == "opus5@high"
    assert cli.ot_specs(lv) == ("claude-haiku-4-5", "claude-opus-5@high")
    own = parse("--reasoning", "high", "--router-model", "openai:gpt-6.1-sol@medium",
                "--ot-gate-model", "openai:gpt-6-luna", "--ot-reader-model", "claude-opus-5@low")
    assert cli.router_model_of(own) == "openai:gpt-6.1-sol@medium"
    assert cli.ot_specs(own) == ("openai:gpt-6-luna@high", "claude-opus-5@low")
    # a leveled Open Targets run is never the published one, so it never shares its cache
    gate, reader = cli.ot_specs(lv)
    assert config.ot_models_version(gate, reader) != config.ot_models_version()


@check
def the_router_cost_is_shown_when_a_level_changes_it():
    from pesto.cost import capturing
    assert cli.router_cost_rows(parse(), "G", "p", []) == []
    with capturing() as spent:
        pass
    rows = [{"model": "claude-opus-5@high", "input_tokens": 10, "output_tokens": 5}]
    assert cli.router_cost_rows(parse("--reasoning", "high"), "G", "p", rows) != []


def _needed(*argv):
    args = parse(*argv)
    reader, worker = cli.pick_models(args.model, args.model_fast or args.model)

    def fitted(name):
        return cli.fit(arms.get(name), args, reader, worker)
    arm = None if args.arm == arms.AUTO else fitted(args.arm)
    return args, cli.needed_models(args, arm, fitted)


def _refusal(*argv):
    """What main() would print: needed_models, then the level check."""
    try:
        args, n = _needed(*argv)
        cli.refuse_unrunnable_levels(args, n)
    except SystemExit as exc:
        return str(exc)
    return None


OPENAI = ("--model", "openai:gpt-6.1-sol", "--model-fast", "openai:gpt-6-luna",
          "--router-model", "openai:gpt-6-luna", "--ot-gate-model", "openai:gpt-6-luna",
          "--ot-reader-model", "openai:gpt-6.1-sol")


@check
def a_model_that_cannot_take_the_level_is_refused_before_any_call():
    assert _refusal("--reasoning", "high") is None
    args, n = _needed("--reasoning", "high")
    assert "claude-opus-5@high" in n and "haiku" in n and "haiku@high" not in n
    # Claude has no off level: a clean refusal that names the flag, not a traceback
    msg = _refusal("--reasoning", "none")
    assert "--reasoning none" in msg and "no reasoning-off level" in msg, msg
    # ... also when Open Targets is skipped and only the arm's own models are checked
    msg = _refusal("--reasoning", "none", "--max-date", "2020")
    assert "--reasoning none" in msg and "no reasoning-off level" in msg, msg
    # Sol cannot be turned off either
    msg = _refusal("--reasoning", "none", *OPENAI)
    assert "gpt-6.1-sol does not accept" in msg and "--reasoning none" in msg, msg
    # each model given a level it has: runnable
    ok = [a for a in OPENAI]
    ok[ok.index("openai:gpt-6.1-sol")] = "openai:gpt-6.1-sol@low"
    ok[-1] = "openai:gpt-6.1-sol@low"
    assert _refusal("--reasoning", "none", *ok) is None
    cli.refuse_unrunnable_levels(parse(), {})                          # no flag, nothing checked


@check
def a_model_with_no_level_is_left_alone_by_the_default_and_refused_when_asked():
    # Claude Haiku 4.5: the live API answers 400 "does not support the effort parameter"
    for spec in ("claude-haiku-4-5", "haiku", "anthropic:claude-haiku-4-5"):
        assert providers.with_effort(spec, "high") == spec              # default: runs as before
        assert "takes no reasoning level" in str(
            raises(ValueError, providers.validate, spec + "@high"))     # explicit: refused
    assert not providers.resolve("claude-haiku-4-5").provider.takes_level("claude-haiku-4-5")
    assert providers.resolve("claude-opus-5").provider.takes_level("claude-opus-5")
    assert providers.resolve("openai:gpt-6-luna").provider.takes_level("gpt-6-luna")
    out = call("claude-haiku-4-5")                                       # and sends nothing new
    assert "output_config" not in out["calls"][0][1]


@check
def the_run_says_which_models_the_level_did_not_reach():
    import contextlib
    import io
    args, n = _needed("--reasoning", "high")
    said = io.StringIO()
    with contextlib.redirect_stderr(said):
        cli.note_unleveled(args, n)
    assert "does not apply to" in said.getvalue() and "haiku" in said.getvalue()
    assert "opus5" not in said.getvalue()
    said = io.StringIO()
    with contextlib.redirect_stderr(said):
        cli.note_unleveled(parse(), {"haiku": []})                       # no flag, no notice
        _, n = _needed("--reasoning", "low", *OPENAI)
        cli.note_unleveled(parse("--reasoning", "low"), n)               # all OpenAI: all reached
    assert said.getvalue() == ""


@check
def a_run_still_asks_only_for_the_keys_of_the_providers_it_calls():
    args = parse("--reasoning", "low", "--arm", "abstracts", "--model", "openai:gpt-6.1-sol",
                 "--model-fast", "openai:gpt-6-luna", "--ot-gate-model", "openai:gpt-6-luna",
                 "--ot-reader-model", "openai:gpt-6.1-sol")
    reader, worker = cli.pick_models(args.model, args.model_fast)
    arm = cli.fit(arms.get(args.arm), args, reader, worker)
    needed = cli.needed_models(args, arm, lambda n: cli.fit(arms.get(n), args, reader, worker))
    assert [p.name for p in providers.providers_for(needed)] == ["openai"]


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
