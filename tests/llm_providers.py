"""The provider layer: how a model spec picks a provider, which keys a run needs,
and the OpenAI adapter. No network, no key: the OpenAI client is a stand-in that
returns real SDK response objects (built from openai.types.responses.Response),
so what the adapter reads is the shape the live API returns.

  python3 tests/llm_providers.py                run everything
  python3 tests/llm_providers.py --group specs  run one group (specs, keys, openai)

tests/anthropic_requests.py is the other half: it pins the Anthropic side.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import subprocess
import sys
import time
import traceback
import types

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("PESTO_PROJECT_ROOT", os.path.join(HERE, "fixtures"))

import httpx  # noqa: E402

from pesto import cost, credentials  # noqa: E402
from pesto.services import llm_service, providers  # noqa: E402
from pesto.services.providers import openai_provider as oa  # noqa: E402

RESULTS = []


def check(group):
    def wrap(fn):
        fn.group = group
        RESULTS.append(fn)
        return fn
    return wrap


def raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type as e:
        return e
    raise AssertionError(f"{fn.__name__} did not raise {exc_type.__name__}")


@contextlib.contextmanager
def keys(**env):
    """Set exactly these API keys (None removes one); never read a .env."""
    names = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
    old = {n: os.environ.pop(n, None) for n in names}
    credentials._loaded = True
    for n, v in env.items():
        if v:
            os.environ[n] = v
    try:
        yield
    finally:
        for n in names:
            os.environ.pop(n, None)
            if old[n] is not None:
                os.environ[n] = old[n]
        providers.reset_clients()


# ===================================================================== specs
@check("specs")
def bare_names_are_anthropic_and_unchanged():
    for spec in ("haiku", "opus5", "claude-haiku-4-5", "claude-opus-5"):
        r = providers.resolve(spec)
        assert r.provider.name == "anthropic" and r.model == spec, (spec, r)


@check("specs")
def explicit_prefixes():
    r = providers.resolve("anthropic:claude-opus-5")
    assert (r.provider.name, r.model) == ("anthropic", "claude-opus-5")
    r = providers.resolve("openai:gpt-6-luna")
    assert (r.provider.name, r.model) == ("openai", "gpt-6-luna")
    r = providers.resolve("openai:gpt-6.1-sol@high")
    assert (r.provider.name, r.model) == ("openai", "gpt-6.1-sol@high")
    assert providers.resolve("OpenAI:gpt-6-luna").provider.name == "openai"


@check("specs")
def bad_specs_fail_before_any_call():
    e = raises(ValueError, providers.resolve, "gemini:gemini-3")
    assert "unknown provider" in str(e) and "openai" in str(e), e
    raises(ValueError, providers.resolve, "openai:")


@check("specs")
def openai_models_and_their_efforts():
    assert oa.parse_model("gpt-6-luna") == ("gpt-6-luna", "low")        # fast role
    assert oa.parse_model("gpt-6.1-sol") == ("gpt-6.1-sol", "medium")   # judgment role
    assert oa.parse_model("gpt-6.1-sol@HIGH") == ("gpt-6.1-sol", "high")
    assert oa.parse_model("gpt-6-luna@none") == ("gpt-6-luna", "none")
    e = raises(ValueError, oa.parse_model, "gpt-6.1-sol@none")   # Sol has no `none`
    assert "does not accept" in str(e), e
    raises(ValueError, oa.parse_model, "gpt-6-luna@turbo")
    e = raises(ValueError, oa.parse_model, "gpt-6-astra")        # no profile, no effort
    assert "explicitly" in str(e), e
    assert oa.parse_model("gpt-6-astra@medium") == ("gpt-6-astra", "medium")
    raises(ValueError, oa.parse_model, "")


@check("specs")
def validate_checks_without_calling():
    providers.validate("openai:gpt-6-luna")
    providers.validate("haiku")
    raises(ValueError, providers.validate, "openai:gpt-6.1-sol@none")
    raises(ValueError, providers.validate, "nope:x")


# ===================================================================== keys
@check("keys")
def a_run_needs_only_the_keys_of_the_providers_it_calls():
    with keys(ANTHROPIC_API_KEY="a"):
        assert providers.missing_keys(["haiku", "claude-opus-5"]) == []
        miss = providers.missing_keys(["haiku", "openai:gpt-6-luna"])
        assert [p.name for p in miss] == ["openai"], miss
    with keys(OPENAI_API_KEY="o"):
        # genuinely OpenAI-only: no Anthropic key required
        assert providers.missing_keys(
            ["openai:gpt-6-luna", "openai:gpt-6.1-sol", None, ""]) == []
        assert [p.name for p in providers.missing_keys(["haiku"])] == ["anthropic"]
    with keys():
        names = [p.name for p in providers.missing_keys(
            ["haiku", "openai:gpt-6-luna", "anthropic:claude-opus-5"])]
        assert names == ["anthropic", "openai"], names


@check("keys")
def one_providers_key_never_stands_in_for_the_others():
    with keys(ANTHROPIC_API_KEY="a"):
        assert credentials.anthropic_api_key() == "a"
        assert credentials.openai_api_key() is None
    with keys(OPENAI_API_KEY="o"):
        assert credentials.openai_api_key() == "o"
        assert credentials.anthropic_api_key() is None


@check("keys")
def missing_key_message_names_the_right_provider():
    with keys():
        e = raises(providers.MissingAPIKeyError,
                   providers.get("openai").client)
        assert str(e) == ("OPENAI_API_KEY is not set. Get a key at "
                          "platform.openai.com/api-keys, then: "
                          "export OPENAI_API_KEY=sk-..."), e
        e = raises(providers.MissingAPIKeyError, providers.get("anthropic").client)
        assert "ANTHROPIC_API_KEY" in str(e) and "OPENAI" not in str(e), e


@check("keys")
def openai_is_an_optional_dependency():
    code = ("import sys; import pesto.services.llm_service; "
            "sys.exit(1 if 'openai' in sys.modules else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, "importing the LLM layer imported openai"
    # and a missing package is explained, not a bare ImportError
    saved = sys.modules.get("openai")
    sys.modules["openai"] = None
    try:
        e = raises(RuntimeError, oa.OpenAIProvider._sdk)
        assert "pesto-genetics[openai]" in str(e), e
    finally:
        if saved is None:
            sys.modules.pop("openai", None)
        else:
            sys.modules["openai"] = saved


# ============================================================= OpenAI adapter
class Skip(Exception):
    """A test that cannot run here, said out loud rather than failed."""


def _import_openai():
    """The SDK and its Response type, or a Skip saying what to install. The
    adapter tests build real SDK response objects, so they need the floor
    version that pyproject asks for, not whatever an old install has."""
    try:
        import openai
        from openai.types.responses import Response
    except ImportError as exc:
        raise Skip(f'needs the OpenAI SDK: pip install "openai>=2.47" ({exc})')
    return openai, Response


def response(status="completed", text="hi there", input_tokens=10, output_tokens=50,
             reasoning_tokens=40, incomplete=None, refusal=None, error=None):
    _, Response = _import_openai()
    output = [{"type": "reasoning", "id": "rs_1", "summary": []}]
    if refusal is not None:
        output.append({"type": "message", "id": "m1", "role": "assistant",
                       "status": "completed",
                       "content": [{"type": "refusal", "refusal": refusal}]})
    elif text is not None:
        output.append({"type": "message", "id": "m1", "role": "assistant",
                       "status": "completed",
                       "content": [{"type": "output_text", "text": text,
                                    "annotations": []}]})
    body = dict(id="resp_1", created_at=0.0, model="gpt-6-luna", object="response",
                output=output, parallel_tool_calls=True, tool_choice="auto",
                tools=[], status=status,
                usage={"input_tokens": input_tokens,
                       "input_tokens_details": {"cached_tokens": 0,
                                                "cache_write_tokens": 0},
                       "output_tokens": output_tokens,
                       "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
                       "total_tokens": input_tokens + output_tokens})
    if incomplete:
        body["incomplete_details"] = {"reason": incomplete}
    if error:
        body["error"] = {"code": error[0], "message": error[1]}
    return Response.model_validate(body)


def api_error(code, message="boom", error_code=None, headers=None):
    openai, _ = _import_openai()
    req = httpx.Request("POST", "https://api.openai.com/v1/responses")
    resp = httpx.Response(code, request=req, headers=headers or {})
    body = {"message": message, "type": error_code or "error", "code": error_code}
    cls = {401: openai.AuthenticationError, 429: openai.RateLimitError,
           400: openai.BadRequestError}.get(
        code, openai.InternalServerError if code >= 500 else openai.APIStatusError)
    return cls(message, response=resp, body=body)


def connection_error():
    openai, _ = _import_openai()
    return openai.APIConnectionError(
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"))


class FakeOpenAI:
    """Stands in for api.openai.com: what was sent, and what was built."""

    def __init__(self, script):
        self.sent, self.built, self.sleeps = [], [], []
        self.script = script if callable(script) else list(script)

    def reply(self, kwargs):
        item = (self.script(kwargs) if callable(self.script)
                else self.script.pop(0))
        if isinstance(item, Exception):
            raise item
        return item


@contextlib.contextmanager
def fake_openai(script):
    """Every OpenAI call is answered from `script`: a list of responses and
    errors in order, or a function of the request. No sleeping, no network."""
    openai, _ = _import_openai()
    fake = FakeOpenAI(script)

    def create(**kwargs):
        fake.sent.append(kwargs)
        return fake.reply(kwargs)

    def factory(**kwargs):
        fake.built.append(kwargs)
        return types.SimpleNamespace(responses=types.SimpleNamespace(create=create))

    real_client, real_sleep = openai.OpenAI, time.sleep
    openai.OpenAI, time.sleep = factory, fake.sleeps.append
    try:
        yield fake
    finally:
        openai.OpenAI, time.sleep = real_client, real_sleep
        providers.reset_clients()


class Run:
    """One call through the OpenAI adapter with a scripted stand-in client."""

    def __init__(self, script, key="sk-test", call=None, via_facade=False):
        out = io.StringIO()
        with fake_openai(script) as fake, keys(OPENAI_API_KEY=key), \
                contextlib.redirect_stdout(out), cost.capturing() as spent:
            try:
                if via_facade:
                    self.result = llm_service.call_llm_with_usage(**(call or {}))
                else:
                    self.result = providers.get("openai").complete(**(call or {}))
                self.error = None
            except Exception as e:                          # noqa: BLE001
                self.result, self.error = None, e
        self.sent, self.built, self.sleeps = fake.sent, fake.built, fake.sleeps
        self.cost_rows = spent.rows
        self.stdout = out.getvalue()


def ask(model="gpt-6-luna", max_tokens=4096, temperature=0.0):
    return dict(model=model, prompt="PROMPT", temperature=temperature,
                max_tokens=max_tokens)


@check("openai")
def request_uses_the_responses_api_with_explicit_effort():
    run = Run([response()], call=ask("gpt-6-luna"))
    assert run.error is None, run.error
    assert run.sent == [dict(
        model="gpt-6-luna", input=[{"role": "user", "content": "PROMPT"}],
        reasoning={"effort": "low"}, max_output_tokens=4096 + 8_000, store=False)], run.sent
    assert run.built == [{"api_key": "sk-test", "max_retries": 0}], run.built
    sol = Run([response()], call=ask("gpt-6.1-sol")).sent[0]
    assert sol["reasoning"] == {"effort": "medium"}
    assert sol["max_output_tokens"] == 4096 + 16_000


@check("openai")
def effort_is_configurable_through_the_spec():
    sent = Run([response()], call=ask("gpt-6.1-sol@high")).sent[0]
    assert sent["reasoning"] == {"effort": "high"} and sent["model"] == "gpt-6.1-sol"
    assert sent["max_output_tokens"] == 4096 + 32_000


@check("openai")
def sampling_parameters_only_without_reasoning():
    for model in ("gpt-6-luna", "gpt-6.1-sol", "gpt-6.1-sol@high"):
        sent = Run([response()], call=ask(model, temperature=0.0)).sent[0]
        assert "temperature" not in sent and "top_p" not in sent, (model, sent)
    sent = Run([response()], call=ask("gpt-6-luna@none", temperature=0.0)).sent[0]
    assert sent["reasoning"] == {"effort": "none"} and sent["temperature"] == 0.0
    assert sent["max_output_tokens"] == 4096


@check("openai")
def output_cap_never_exceeds_the_model_limit():
    sent = Run([response()], call=ask("gpt-6-luna", max_tokens=200_000)).sent[0]
    assert sent["max_output_tokens"] == 128_000


@check("openai")
def completed_answer_is_normalised():
    run = Run([response(text="<a>1</a>", input_tokens=123, output_tokens=456,
                        reasoning_tokens=300)], call=ask())
    assert run.result.text == "<a>1</a>"
    assert (run.result.input_tokens, run.result.output_tokens) == (123, 456)
    assert run.result.reasoning_tokens == 300      # information only
    assert run.result.stop_reason == "end_turn"
    assert run.result.as_dict() == {"text": "<a>1</a>", "input_tokens": 123,
                                    "output_tokens": 456, "stop_reason": "end_turn",
                                    "flex": False}


@check("openai")
def length_cutoff_is_reported_in_pestos_words():
    run = Run([response(status="incomplete", incomplete="max_output_tokens",
                        text="<a>par")], call=ask())
    assert run.result.stop_reason == "max_tokens" and run.result.text == "<a>par"
    # reasoning ate the whole budget: no visible text, still a clean cutoff
    run = Run([response(status="incomplete", incomplete="max_output_tokens",
                        text=None)], call=ask())
    assert run.result.stop_reason == "max_tokens" and run.result.text == ""


@check("openai")
def refusals_are_reported_not_parsed():
    run = Run([response(refusal="I can't help", text=None)], call=ask())
    assert run.result.stop_reason == "refusal" and run.result.text == ""
    assert "refused to answer" in run.stdout, run.stdout
    run = Run([response(status="incomplete", incomplete="content_filter",
                        text=None)], call=ask())
    assert run.result.stop_reason == "refusal"
    # A reason this SDK's types do not know yet is passed on, not guessed at.
    odd = response(status="incomplete", incomplete="content_filter")
    odd.incomplete_details.reason = "max_messages"
    run = Run([odd], call=ask())
    assert run.result.stop_reason == "incomplete:max_messages"


@check("openai")
def transient_errors_are_retried_with_backoff():
    run = Run([api_error(429), response()], call=ask())
    assert run.error is None and run.sleeps == [2] and len(run.sent) == 2
    run = Run([api_error(500), api_error(503), response()], call=ask())
    assert run.error is None and run.sleeps == [2, 4]
    run = Run([connection_error(), response()], call=ask())
    assert run.error is None and run.sleeps == [2]
    run = Run([response(status="failed", text=None,
                        error=("server_error", "oops")), response()], call=ask())
    assert run.error is None and run.sleeps == [2]


@check("openai")
def retry_after_is_honoured():
    run = Run([api_error(429, headers={"retry-after": "7"}), response()], call=ask())
    assert run.sleeps == [7.0], run.sleeps


@check("openai")
def persistent_failure_is_reported_as_overloaded():
    run = Run([api_error(503, "busy")] * 3, call=ask())
    assert isinstance(run.error, providers.LLMOverloadedError), run.error
    assert "OpenAI API call failed after 3 attempts" in str(run.error)
    assert run.sleeps == [2, 4]


@check("openai")
def errors_that_waiting_cannot_fix_are_raised_at_once():
    openai, _ = _import_openai()
    for err, cls in ((api_error(401, "bad key"), openai.AuthenticationError),
                     (api_error(400, "bad request"), openai.BadRequestError),
                     (api_error(429, "out of credit", error_code="insufficient_quota"),
                      openai.RateLimitError)):
        run = Run([err, response()], call=ask())
        assert isinstance(run.error, cls) and run.sleeps == [] and len(run.sent) == 1, \
            (cls, run.error, run.sleeps)


@check("openai")
def client_is_built_once_and_key_is_required():
    run = Run([response(), response()], call=ask())
    assert len(run.built) == 1
    with keys():
        e = raises(providers.MissingAPIKeyError, providers.get("openai").complete,
                   **ask())
        assert "OPENAI_API_KEY" in str(e)


@check("openai")
def facade_routes_by_spec_and_records_cost_under_the_spec():
    run = Run([response(text="routed", input_tokens=1000, output_tokens=500)],
              call=dict(prompt="P", model="openai:gpt-6-luna"), via_facade=True)
    assert run.error is None, run.error
    assert run.result["text"] == "routed" and run.result["stop_reason"] == "end_turn"
    assert run.cost_rows == [{"model": "openai:gpt-6-luna",
                              "input_tokens": 1000, "output_tokens": 500}]
    run = Run([], call=dict(prompt="P", model="openai:gpt-6.1-sol@none"),
              via_facade=True)
    assert isinstance(run.error, ValueError) and run.sent == []


# ============================================================== open targets
from pesto import config, ot_matcher, open_targets  # noqa: E402

PUBLISHED = f"tagged_shortlist:{config.OT_ENCODER}:{config.OT_TOP_K}"


def _versions(**models):
    return (config.ot_agent_version(**models), config.ot_match_version(**models))


@check("ot")
def the_published_models_leave_every_cache_key_untouched():
    agent, match = _versions()
    assert agent.startswith(PUBLISHED) and "gate=" not in agent and "read=" not in agent, agent
    assert match == agent + ":gate", match
    # The published models, however they are spelled, are the same key.
    assert _versions(gate_model="claude-haiku-4-5",
                     reader_model="anthropic:claude-opus-5") == (agent, match)
    assert config.ot_models_version() == ""


@check("ot")
def different_models_never_share_a_key():
    cases = {
        "published": {},
        "reader sol": dict(reader_model="openai:gpt-6.1-sol"),
        "reader sol high": dict(reader_model="openai:gpt-6.1-sol@high"),
        "gate luna": dict(gate_model="openai:gpt-6-luna"),
        "gate luna medium": dict(gate_model="openai:gpt-6-luna@medium"),
        "both": dict(gate_model="openai:gpt-6-luna",
                     reader_model="openai:gpt-6.1-sol"),
        "reader other anthropic model": dict(reader_model="claude-sonnet-4-5"),
    }
    keys_ = {name: _versions(**models) for name, models in cases.items()}
    assert len(set(keys_.values())) == len(cases), keys_
    assert len({k[0] for k in keys_.values()}) == len(cases)
    assert ":read=openai:gpt-6.1-sol@medium" in keys_["reader sol"][0]
    assert ":gate=openai:gpt-6-luna@low" in keys_["gate luna"][0]
    # Only the role that changed is named.
    assert "gate=" not in keys_["reader sol"][0]
    assert "read=" not in keys_["gate luna"][0]


@check("ot")
def one_model_written_two_ways_is_one_key():
    assert (_versions(reader_model="openai:gpt-6.1-sol")
            == _versions(reader_model="openai:gpt-6.1-sol@medium")
            == _versions(reader_model="OpenAI:gpt-6.1-sol@MEDIUM"))
    assert (_versions(gate_model="openai:gpt-6-luna")
            == _versions(gate_model="openai:gpt-6-luna@low"))


@check("ot")
def a_bad_model_spec_fails_before_any_fetch_or_call():
    for models in (dict(reader_model="openai:gpt-6.1-sol@none"),
                   dict(gate_model="mystery:model"),
                   dict(reader_model="openai:no-such-model")):
        raises(ValueError, config.ot_models, **models)
        raises(ValueError, open_targets.fetch_and_save_open_targets_traits,
               "GENE", "/nonexistent", "pheno", [], **models)


def _record(**models):
    agent, match = _versions(**models)
    return {"agent_version": agent, "ot_match_version": match,
            "shortlist": [{"disease_id": "A", "name": "a", "score": 1.0}],
            "graded": [{"disease_id": "A", "tag": "EXACT"}]}


@check("ot")
def a_cached_record_is_reused_only_by_the_models_that_made_it():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sidecar.json")
        def load(**models):
            return open_targets._load_match_sidecar(
                path, gate_model=models.get("gate_model"),
                reader_model=models.get("reader_model"))
        sol = dict(reader_model="openai:gpt-6.1-sol")

        open_targets._write_match_sidecar(path, _record())     # the published pair
        assert load() is not None
        assert load(reader_model="anthropic:claude-opus-5") is not None
        assert load(**sol) is None
        assert load(gate_model="openai:gpt-6-luna") is None

        open_targets._write_match_sidecar(path, _record(**sol))
        assert load(**sol) is not None
        assert load(reader_model="openai:gpt-6.1-sol@medium") is not None
        assert load() is None                                  # published pair
        assert load(reader_model="openai:gpt-6.1-sol@high") is None
        assert load(gate_model="openai:gpt-6-luna", **sol) is None


@check("ot")
def a_record_from_before_the_models_were_configurable_is_still_the_published_pair():
    # The key of such a record is exactly what the old code produced.
    old = f"{PUBLISHED}:{config.OT_MATCH_PROMPT}"
    assert config.ot_agent_version() == old
    assert config.ot_agent_version(reasons=False) == old


def _traits():
    return [{"disease_id": "EFO_1", "name": "asthma", "score": 0.9},
            {"disease_id": "EFO_2", "name": "wheezing", "score": 0.5}]


@contextlib.contextmanager
def _no_encoder():
    """The shortlist keeps every trait, in order. The real one loads an encoder
    (numpy, model weights); what is under test here is who the models are, not
    which traits are nearest, so the module is replaced for the duration."""
    import pesto
    name = "pesto.ot_shortlist"
    real_mod, real_attr = sys.modules.get(name), getattr(pesto, "ot_shortlist", None)
    stub = types.ModuleType(name)
    stub.shortlist = lambda phenotype, traits, k=None, name=None: list(traits)
    sys.modules[name], pesto.ot_shortlist = stub, stub
    try:
        yield
    finally:
        if real_mod is None:
            sys.modules.pop(name, None)
            if real_attr is None and hasattr(pesto, "ot_shortlist"):
                del pesto.ot_shortlist
        else:
            sys.modules[name], pesto.ot_shortlist = real_mod, real_attr


def _reply(prompt):
    """What each agent says, told apart by the words of its own prompt."""
    n = len(_traits())
    if "DROP:" in prompt:
        return "DROP: 2"
    return "\n".join(f"{i}. {'EXACT' if i == 1 else 'DIFFERENT'}"
                     for i in range(1, n + 1))


@check("ot")
def the_matcher_calls_the_configured_models_and_records_them():
    seen = []

    def fake(prompt, model="x", temperature=0.0, agent_name=None, max_tokens=None, **kw):
        seen.append((agent_name, model))
        return {"text": _reply(prompt), "input_tokens": 100, "output_tokens": 10,
                "stop_reason": "end_turn"}

    real = llm_service.call_llm_with_usage
    llm_service.call_llm_with_usage = fake
    try:
        with _no_encoder():
            default = ot_matcher.match("G", "asthma", _traits())
            custom = ot_matcher.match(
                "G", "asthma", _traits(), model="openai:gpt-6.1-sol",
                gate_model="openai:gpt-6-luna")
    finally:
        llm_service.call_llm_with_usage = real
    by_agent = lambda tag: [m for a, m in seen if tag in (a or "")]
    assert default["matched_id"] == "EFO_1" and custom["matched_id"] == "EFO_1"
    assert default["tokens"]["gate_model"] == "claude-haiku-4-5"
    assert default["tokens"]["read_model"] == "claude-opus-5"
    # Recorded canonically, effort spelled out: the record says what actually ran.
    assert custom["tokens"]["gate_model"] == "openai:gpt-6-luna@low"
    assert custom["tokens"]["read_model"] == "openai:gpt-6.1-sol@medium"
    # Gate and reader used the model each was given, never the other's.
    models = {m for _, m in seen}
    assert models == {"claude-haiku-4-5", "claude-opus-5",
                      "openai:gpt-6-luna@low", "openai:gpt-6.1-sol@medium"}, seen
    assert set(by_agent("gate")) <= {"claude-haiku-4-5", "openai:gpt-6-luna@low"}, seen


@check("ot")
def an_openai_only_open_targets_run_needs_no_anthropic_key():
    def script(request):
        text = _reply(request["input"][0]["content"])
        return response(text=text, input_tokens=200, output_tokens=20)

    with fake_openai(script) as fake, keys(OPENAI_API_KEY="sk-test"), \
            cost.capturing() as spent, contextlib.redirect_stdout(io.StringIO()):
        assert providers.missing_keys(
            config.ot_models("openai:gpt-6-luna", "openai:gpt-6.1-sol")) == []
        with _no_encoder():
            out = ot_matcher.match("G", "asthma", _traits(),
                                   model="openai:gpt-6.1-sol",
                                   gate_model="openai:gpt-6-luna")
    assert out["matched_id"] == "EFO_1", out
    assert not os.environ.get("ANTHROPIC_API_KEY")
    sent_models = sorted({r["model"] for r in fake.sent})
    assert sent_models == ["gpt-6-luna", "gpt-6.1-sol"], sent_models
    assert {r["model"] for r in spent.rows} == {"openai:gpt-6-luna@low",
                                                "openai:gpt-6.1-sol@medium"}, spent.rows
    # And the usage a record keeps prices under the models that produced it.
    rows = cost.from_ot_tokens("G", "asthma", out["tokens"])
    assert {r["model"] for r in rows} == {"openai:gpt-6-luna@low",
                                          "openai:gpt-6.1-sol@medium"}, rows


@check("ot")
def a_truncated_reply_stops_the_run_whichever_provider_gave_it():
    def fake(prompt, **kw):
        return {"text": "1. EX", "input_tokens": 1, "output_tokens": 1,
                "stop_reason": "max_tokens"}
    real = llm_service.call_llm_with_usage
    llm_service.call_llm_with_usage = fake
    try:
        with _no_encoder():
            e = raises(Exception, ot_matcher.match, "G", "asthma", _traits(),
                       model="openai:gpt-6.1-sol", gate_model="openai:gpt-6-luna")
    finally:
        llm_service.call_llm_with_usage = real
    assert "max_tokens" in str(e) or "truncat" in str(e).lower(), e


# ================================================================== pricing
def _m(n):                                   # a million tokens each way
    return 1_000_000


@check("pricing")
def listed_prices_are_applied_per_million_tokens():
    p = config.price_usd
    assert p("haiku", _m(1), _m(1)) == p("claude-haiku-4-5", _m(1), _m(1)) == 6.00
    assert p("opus5", _m(1), _m(1)) == p("claude-opus-5", _m(1), _m(1)) == 30.00
    assert p("openai:gpt-6-luna", _m(1), _m(1)) == 0.60
    assert p("openai:gpt-6.1-sol", _m(1), _m(1)) == 12.00
    assert abs(p("openai:gpt-6-luna", 2_500, 400) - (0.00025 + 0.0002)) < 1e-12


@check("pricing")
def a_price_belongs_to_the_model_not_to_how_it_is_spelled():
    p = config.price_usd
    same = [p("claude-opus-5", 1000, 1000), p("anthropic:claude-opus-5", 1000, 1000),
            p("ANTHROPIC:claude-opus-5", 1000, 1000)]
    assert len(set(same)) == 1 and same[0] is not None
    for spelled in ("openai:gpt-6.1-sol", "openai:gpt-6.1-sol@low",
                    "openai:gpt-6.1-sol@high", "OpenAI:gpt-6.1-sol@medium"):
        assert p(spelled, 1000, 1000) == p("openai:gpt-6.1-sol", 1000, 1000) is not None, spelled


@check("pricing")
def unknown_models_are_unpriced_never_charged_as_haiku():
    p = config.price_usd
    for model in ("claude-sonnet-4-5", "openai:gpt-9", "openai:gpt-6", "gpt-6-luna",
                  "mystery", "", None):
        assert p(model, 1_000_000, 1_000_000) is None, model
    assert not hasattr(config, "PRICE_PER_MTOK_INPUT")       # no silent default left


@check("pricing")
def every_model_pesto_can_run_has_a_price():
    for spec in ("haiku", "opus", "opus5", "claude-haiku-4-5", "claude-opus-5",
                 "openai:gpt-6-luna", "openai:gpt-6.1-sol"):
        providers.validate(spec)
        assert config.price_usd(spec, 1, 1) is not None, spec


def _spend(*calls):
    with cost.capturing() as spent:
        for model, i, o in calls:
            cost.record(model, i, o)
    return spent.summary()


@check("pricing")
def a_summary_names_what_it_could_not_price():
    s = _spend(("claude-haiku-4-5", 1_000_000, 0), ("claude-sonnet-4-5", 500, 500),
               ("claude-sonnet-4-5", 1, 1), ("", 3, 3))
    assert s["usd"] == 1.0                      # the priced call alone
    assert s["unpriced"] == ["(unnamed)", "claude-sonnet-4-5"], s
    s = _spend(("openai:gpt-6-luna@low", 1_000_000, 0))
    assert s["usd"] == 0.10 and s["unpriced"] == []


@check("pricing")
def an_unpriced_line_is_an_empty_cell_and_poisons_its_total():
    priced = cost.row("G", "p", "Bands", "claude-haiku-4-5", 1, 10, 10, 0.5, False)
    unpriced = cost.row("G", "p", "Read", "claude-sonnet-4-5", 1, 10, 10, None, False)
    assert priced["usd"] == "0.500000" and unpriced["usd"] == ""
    total = cost.with_total([priced, unpriced], "G", "p")[-1]
    assert total["usd"] == "" and total["input_tokens"] == 20 and total["calls"] == 2
    total = cost.with_total([priced, priced], "G", "p")[-1]
    assert total["usd"] == "1.000000"
    assert cost.row("G", "p", "x", "m", 0, 0, 0, 0, False)["usd"] == "0.000000"  # free is not unpriced


@check("pricing")
def open_targets_rows_follow_the_models_recorded_with_the_counts():
    counts = dict(gate_in=1_000_000, gate_out=0, read_in=0, read_out=1_000_000)
    rows = {r["step"]: r for r in cost.from_ot_tokens("G", "p", dict(
        counts, gate_model="openai:gpt-6-luna@low", read_model="openai:gpt-6.1-sol@medium"))}
    assert rows["ot_gate"]["model"] == "openai:gpt-6-luna@low" and rows["ot_gate"]["usd"] == "0.100000"
    assert rows["ot_read"]["model"] == "openai:gpt-6.1-sol@medium" and rows["ot_read"]["usd"] == "10.000000"
    # A record from before the models were recorded was the published pair.
    old = {r["step"]: r for r in cost.from_ot_tokens("G", "p", counts)}
    assert old["ot_gate"]["model"] == "claude-haiku-4-5" and old["ot_gate"]["usd"] == "1.000000"
    assert old["ot_read"]["model"] == "claude-opus-5" and old["ot_read"]["usd"] == "25.000000"
    # And a model with no price is left blank, not charged as a published one.
    odd = {r["step"]: r for r in cost.from_ot_tokens("G", "p", dict(
        counts, gate_model="claude-sonnet-4-5", read_model="claude-opus-5"))}
    assert odd["ot_gate"]["usd"] == "" and odd["ot_read"]["usd"] == "25.000000"


@check("pricing")
def a_cached_run_keeps_its_unpriced_marker_through_the_trace():
    from pesto.flow.types import Step, Trace
    trace = Trace((Step("Read", "f", model="claude-sonnet-4-5", input_tokens=5,
                        output_tokens=5, usd=0.0, calls=1, unpriced=("claude-sonnet-4-5",)),
                   Step("Bands", "g", model="haiku", input_tokens=5, output_tokens=5,
                        usd=0.25, calls=1)))
    rows = {r["step"]: r for r in cost.from_trace("G", "p", trace)}
    assert rows["Read"]["usd"] == "" and rows["Bands"]["usd"] == "0.250000"
    # Written and read back as a stored run is, a step still says so.
    from pesto.flow import store
    back = store.Step(**{k: v for k, v in trace.as_list()[0].items()
                         if k in store._STEP_FIELDS})
    assert list(back.unpriced) == ["claude-sonnet-4-5"]
    old = {k: v for k, v in trace.as_list()[1].items() if k != "unpriced"}  # a stored run from before
    assert store.Step(**old).unpriced == ()


# ====================================================================== cli
from pesto import cli  # noqa: E402
from pesto.flow import arms  # noqa: E402

OPENAI_ONLY = ["--arm", "abstracts", "--model", "openai:gpt-6.1-sol",
               "--model-fast", "openai:gpt-6-luna",
               "--ot-gate-model", "openai:gpt-6-luna",
               "--ot-reader-model", "openai:gpt-6.1-sol"]


def _args(*argv):
    return cli.build_parser().parse_args(["--gene", "G", "--phenotype", "p", *argv])


def _needed(*argv):
    args = _args(*argv)
    reader, worker = cli.pick_models(args.model, args.model_fast or args.model)

    def fitted(name):
        return cli.fit(arms.get(name), args, reader, worker)
    arm = None if args.arm == arms.AUTO else fitted(args.arm)
    return cli.needed_models(args, arm, fitted)


def _providers(needed):
    return [p.name for p in providers.providers_for(needed)]


def _refusal(needed):
    try:
        cli.require_keys(needed)
    except SystemExit as e:
        return str(e)
    return None


@check("cli")
def the_default_command_needs_the_anthropic_key_and_only_that():
    for argv in ((), ("--arm", "abstracts")):
        assert _providers(_needed(*argv)) == ["anthropic"], argv
    assert _providers(_needed("--arm", "abstracts-trait")) == ["anthropic"]


@check("cli")
def an_openai_only_command_needs_only_the_openai_key():
    needed = _needed(*OPENAI_ONLY)
    assert _providers(needed) == ["openai"], needed
    with keys(OPENAI_API_KEY="sk-o"):
        assert _refusal(needed) is None
    with keys(ANTHROPIC_API_KEY="sk-a"):                     # the wrong key is no help
        msg = _refusal(needed)
    assert "OPENAI_API_KEY" in msg and "ANTHROPIC_API_KEY" not in msg, msg
    assert "api.openai.com" in msg and "api.anthropic.com" not in msg


@check("cli")
def the_auto_router_is_an_anthropic_call_and_the_refusal_says_so():
    needed = _needed(*[a for a in OPENAI_ONLY if a not in ("--arm", "abstracts")])
    assert _providers(needed) == ["anthropic", "openai"], needed
    assert needed["opus5"] == ["the `--arm auto` router"]
    with keys(OPENAI_API_KEY="sk-o"):
        msg = _refusal(needed)
    assert "ANTHROPIC_API_KEY" in msg and "--arm auto" in msg and "--arm abstracts" in msg, msg
    assert "OPENAI_API_KEY" not in msg
    with keys(OPENAI_API_KEY="sk-o", ANTHROPIC_API_KEY="sk-a"):
        assert _refusal(needed) is None


@check("cli")
def each_missing_provider_is_named_once_with_what_needs_it():
    needed = _needed(*OPENAI_ONLY[2:])                       # auto, all OpenAI
    with keys():
        msg = _refusal(needed)
    assert msg.count("No Anthropic API key") == 1 and msg.count("No OpenAI API key") == 1, msg
    assert "openai:gpt-6.1-sol@medium" in msg and "openai:gpt-6-luna@low" in msg, msg
    assert ".env" in msg


@check("cli")
def open_targets_models_follow_their_own_flags_not_model():
    # --model reaches the arm and not Open Targets, as before.
    needed = _needed("--arm", "abstracts", "--model", "openai:gpt-6.1-sol",
                     "--model-fast", "openai:gpt-6-luna")
    assert _providers(needed) == ["anthropic", "openai"]
    assert needed["claude-opus-5"] == ["the Open Targets reader"]
    assert needed["claude-haiku-4-5"] == ["the Open Targets gate"]
    # And the Open Targets flags reach Open Targets and not the arm.
    needed = _needed("--arm", "abstracts", "--ot-reader-model", "openai:gpt-6.1-sol")
    assert needed["openai:gpt-6.1-sol@medium"] == ["the Open Targets reader"]
    # The arm keeps its own names for its models; the gate is Open Targets'.
    assert needed["claude-haiku-4-5"] == ["the Open Targets gate"]
    assert needed["haiku"] == needed["opus5"] == ["the literature arm"]


@check("cli")
def switching_off_a_call_drops_its_key_requirement():
    base = ["--arm", "abstracts", "--model", "openai:gpt-6.1-sol",
            "--model-fast", "openai:gpt-6-luna",
            "--ot-reader-model", "openai:gpt-6.1-sol"]
    # The gate is Anthropic's by default; with no gate, nothing else is.
    assert _providers(_needed(*base)) == ["anthropic", "openai"]
    assert _providers(_needed(*base, "--no-ot-gate")) == ["openai"]
    # --max-date skips Open Targets altogether.
    assert _providers(_needed("--arm", "abstracts", "--model", "openai:gpt-6.1-sol",
                              "--model-fast", "openai:gpt-6-luna",
                              "--max-date", "2019")) == ["openai"]


@check("cli")
def a_spec_that_cannot_run_is_refused_naming_its_flag():
    for argv, flag in ((("--model", "openai:gpt-6.1-sol@none"), "--model"),
                       (("--model-fast", "mystery:thing"), "--model-fast"),
                       (("--ot-gate-model", "openai:nope"), "--ot-gate-model"),
                       (("--ot-reader-model", "openai:gpt-6-luna@bogus"), "--ot-reader-model")):
        try:
            _needed("--arm", "abstracts", *argv)
        except SystemExit as e:
            assert flag + ":" in str(e), (argv, str(e))
        else:
            raise AssertionError(f"{argv} was accepted")


@check("cli")
def models_change_the_fingerprint_and_bare_names_do_not():
    plain = arms.get("abstracts")
    assert cli.fit(plain, _args(), None, None).fingerprint() == plain.fingerprint()
    swapped = cli.fit(plain, _args(), "openai:gpt-6.1-sol", "openai:gpt-6-luna")
    assert swapped.fingerprint() != plain.fingerprint()
    assert "openai:gpt-6.1-sol" in swapped.describe()
    assert plain.models() == ["haiku", "opus5"], plain.models()      # as the arm names them


@check("cli")
def describing_a_pipeline_needs_no_key_of_any_provider():
    with keys(), contextlib.redirect_stdout(io.StringIO()) as out:
        code = cli.main(["--arm", "abstracts", "--show-pipeline", *OPENAI_ONLY[2:]])
    assert code == 0 and "openai:gpt-6.1-sol" in out.getvalue()


@check("cli")
def a_command_stops_before_any_work_when_its_key_is_missing():
    with keys(), contextlib.redirect_stdout(io.StringIO()):
        try:
            cli.main(["--gene", "G", "--phenotype", "p", *OPENAI_ONLY])
        except SystemExit as e:
            assert "OPENAI_API_KEY" in str(e), e
        else:
            raise AssertionError("ran without a key")


@check("cli")
def a_refused_key_names_the_provider_that_refused_it():
    class AuthenticationError(Exception):
        pass
    AuthenticationError.__module__ = "openai"
    assert providers.auth_failure(AuthenticationError("401")).name == "openai"
    AuthenticationError.__module__ = "anthropic._exceptions"
    assert providers.auth_failure(AuthenticationError("401")).name == "anthropic"


# ================================================================== router
AUTO_OPENAI = ["--model", "openai:gpt-6.1-sol", "--model-fast", "openai:gpt-6-luna",
               "--ot-gate-model", "openai:gpt-6-luna",
               "--ot-reader-model", "openai:gpt-6.1-sol"]
ROUTER_OPENAI = ["--router-model", "openai:gpt-6.1-sol@medium"]


@check("router")
def the_default_router_is_the_claude_one_and_nothing_changes():
    assert arms.ROUTER_MODEL == "opus5"
    args = _args()
    assert args.router_model is None and cli.router_model_of(args) == "opus5"
    needed = _needed()                                       # arm auto, defaults
    assert needed["opus5"][0] == "the `--arm auto` router"
    assert _providers(needed) == ["anthropic"]
    # --model does not reach the router, as before.
    needed = _needed(*AUTO_OPENAI)
    assert needed["opus5"] == ["the `--arm auto` router"] and "anthropic" in _providers(needed)
    # No router line in the cost table of a default run.
    assert cli.router_cost_rows(args, "G", "p", [{"model": "opus5", "input_tokens": 9,
                                                  "output_tokens": 9}]) == []


@check("router")
def an_openai_router_makes_auto_an_openai_only_command():
    needed = _needed(*AUTO_OPENAI, *ROUTER_OPENAI)
    assert _providers(needed) == ["openai"], needed
    assert needed["openai:gpt-6.1-sol@medium"].count("the `--arm auto` router") == 1
    with keys(OPENAI_API_KEY="sk-o"):
        assert _refusal(needed) is None
    with keys(ANTHROPIC_API_KEY="sk-a"):
        msg = _refusal(needed)
    assert "OPENAI_API_KEY" in msg and "ANTHROPIC_API_KEY" not in msg, msg
    assert "the router" in msg or "--arm auto" in msg


@check("router")
def only_the_key_of_the_selected_router_is_required():
    # Claude everywhere but the router on OpenAI: needs both, and says why for OpenAI.
    needed = _needed(*ROUTER_OPENAI)
    assert _providers(needed) == ["anthropic", "openai"]
    with keys(ANTHROPIC_API_KEY="sk-a"):
        msg = _refusal(needed)
    assert "OPENAI_API_KEY" in msg and "ANTHROPIC_API_KEY" not in msg
    assert "openai:gpt-6.1-sol@medium" in msg and "--arm auto" in msg
    # OpenAI everywhere but the router on Claude: needs Anthropic for the router alone.
    needed = _needed(*AUTO_OPENAI, "--router-model", "claude-haiku-4-5")
    with keys(OPENAI_API_KEY="sk-o"):
        msg = _refusal(needed)
    assert "ANTHROPIC_API_KEY" in msg and "claude-haiku-4-5" in msg and "OPENAI_API_KEY" not in msg


@check("router")
def a_router_that_cannot_run_is_refused_naming_the_flag():
    for spec in ("openai:gpt-6.1-sol@none", "mystery:x", "openai:no-such-model"):
        try:
            _needed(*ROUTER_OPENAI[:0], "--router-model", spec)
        except SystemExit as e:
            assert "--router-model:" in str(e), (spec, str(e))
        else:
            raise AssertionError(f"{spec} was accepted")


@check("router")
def a_router_with_an_explicit_arm_is_an_error_not_silently_ignored():
    with keys(OPENAI_API_KEY="sk-o"), contextlib.redirect_stdout(io.StringIO()):
        try:
            cli.main(["--gene", "G", "--phenotype", "p", "--arm", "abstracts",
                      "--model", "openai:gpt-6-luna", *ROUTER_OPENAI])
        except SystemExit as e:
            assert "--router-model only applies with --arm auto" in str(e), e
        else:
            raise AssertionError("accepted")


def _routed(args_extra, reply_text="disease"):
    """Run the real route() with a stand-in model; return (arm name, calls made)."""
    seen = []

    def fake(prompt, model="x", temperature=0.0, agent_name=None, max_tokens=None, **kw):
        seen.append((agent_name, model))
        cost.record(model, 11, 3)
        return {"text": reply_text, "input_tokens": 11, "output_tokens": 3,
                "stop_reason": "end_turn"}
    real = llm_service.call_llm_with_usage
    from pesto import harness
    real_h = harness.call_llm_with_usage
    llm_service.call_llm_with_usage = harness.call_llm_with_usage = fake
    try:
        args = _args(*args_extra)
        arm, rows = cli.route(args, "asthma", None, None)
    finally:
        llm_service.call_llm_with_usage, harness.call_llm_with_usage = real, real_h
    return arm.name, seen, rows, args


@check("router")
def the_router_call_goes_to_the_selected_model_and_picks_the_arm():
    name, seen, rows, _ = _routed([])
    assert seen == [("phenotype_kind", "claude-opus-5")] and name == "abstracts", seen
    name, seen, rows, args = _routed(ROUTER_OPENAI, reply_text="other")
    assert seen == [("phenotype_kind", "openai:gpt-6.1-sol@medium")], seen
    assert name == "abstracts-trait"
    # Its spend is captured, and shown because the router was named.
    assert rows == [{"model": "openai:gpt-6.1-sol@medium", "input_tokens": 11, "output_tokens": 3}]
    line = cli.router_cost_rows(args, "G", "p", rows)
    assert len(line) == 1 and line[0]["step"] == "router" and line[0]["usd"] == "0.000052"
    total = cost.with_total(line, "G", "p")[-1]
    assert total["input_tokens"] == 11 and total["usd"] == "0.000052"


@check("router")
def the_router_is_in_the_record_but_not_in_any_fingerprint_or_cache_key():
    plain = {n: arms.get(n).fingerprint() for n in arms.FAMILIES["abstracts"]}
    for extra in ([], ROUTER_OPENAI, ["--router-model", "claude-haiku-4-5"]):
        args = _args(*extra)
        for n in plain:                        # the arm a run lands on is the same arm
            assert cli.fit(arms.get(n), args, None, None).fingerprint() == plain[n]
    # A stored run is valid whichever router sent the pair to its arm.
    assert providers.canonical("openai:gpt-6.1-sol") == "openai:gpt-6.1-sol@medium"


# ------------------------------------------------------------------- runner
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=("specs", "keys", "openai", "ot", "pricing", "cli", "router"))
    args = ap.parse_args()
    ran = failed = 0
    skipped = []
    for fn in RESULTS:
        if args.group and fn.group != args.group:
            continue
        ran += 1
        try:
            fn()
            print(f"ok    [{fn.group}] {fn.__name__}")
        except Skip as why:
            ran -= 1
            skipped.append(fn)
            print(f"SKIP  [{fn.group}] {fn.__name__}: {why}")
        except Exception:                                    # noqa: BLE001
            failed += 1
            print(f"FAIL  [{fn.group}] {fn.__name__}")
            traceback.print_exc()
    print(f"{ran - failed}/{ran} passed"
          + (f", {len(skipped)} SKIPPED (not run: see above)" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
