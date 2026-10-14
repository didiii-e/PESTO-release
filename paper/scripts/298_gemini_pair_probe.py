#!/usr/bin/env python3
"""Probe (14 October 2026): what one Fig. 2 pair costs on Gemini instead of
Claude, with the reasoning effort matched as closely as the two APIs allow.

The default arm (`current`) is run twice on the same pair, fresh, the same day:

  Claude  Opus 5 for synonyms and reading (it thinks by default), Haiku 4.5 for
          the broadened term and the relevance bands (no thinking).
  Gemini  gemini-4-argon at thinking level MEDIUM in place of Opus, and
          gemini-3.8-flash at LOW in place of Haiku (its lowest level; it
          cannot be told not to think).

The package's Gemini call still sends the legacy thinking_budget, which Gemini
4 rejects, and routes gemini-4 to a regional endpoint, so this script replaces
it for the run without touching the package: thinking_level per model, the
global endpoint, the provider's default temperature (as Opus runs), and room
for the thinking in the output limit. Gemini thinking tokens are recorded apart.
Costs are recomputed from the tokens of each block at list prices (Vertex,
global, 14 October 2026), since the package's price table does not know Gemini.

  python3 scripts/298_gemini_pair_probe.py [GENE] [PHENOTYPE]

Writes results/gemini_probe/<gene>_<phenotype>.json and the two runs under
results/gemini_probe/runs/.
"""
from __future__ import annotations

import collections
import dataclasses
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PESTO_PROJECT_ROOT", ROOT)

from pesto.flow import arms, run as flow_run, store  # noqa: E402
from pesto.flow.types import Query  # noqa: E402
from pesto.services import llm_service  # noqa: E402

OUT = os.path.join(ROOT, "results", "gemini_probe")
LEVELS = {"gemini-4-argon": "MEDIUM", "gemini-3.8-flash": "LOW"}
SWAP = {"opus5": "gemini-4-argon", "haiku": "gemini-3.8-flash"}
MAX_OUTPUT = 32768
PRICES = {  # USD per million tokens, input / output (thinking billed as output)
    "opus5": (5.00, 25.00), "claude-opus-5@vertex": (5.00, 25.00),
    "haiku": (1.00, 5.00), "claude-haiku-4-5@vertex": (1.00, 5.00),
    "gemini-4-argon": (2.00, 10.00),
    "gemini-3.8-flash": (0.75, 3.75),
}
PRICES_LATER = {"gemini-4-argon": (4.00, 20.00), "gemini-3.8-flash": (1.50, 7.50)}
THOUGHTS = collections.defaultdict(int)


def call_gemini(prompt, model, temperature, max_retries, initial_delay):
    from google import genai
    from google.genai.types import GenerateContentConfig, ThinkingConfig
    client = genai.Client(vertexai=True, project=llm_service.VERTEX_PROJECT, location="global")
    config = GenerateContentConfig(max_output_tokens=MAX_OUTPUT,
                                   thinking_config=ThinkingConfig(thinking_level=LEVELS[model]))
    last = None
    for _ in range(max_retries):
        try:
            r = client.models.generate_content(model=model, contents=prompt, config=config)
            u = r.usage_metadata
            thoughts = getattr(u, "thoughts_token_count", 0) or 0
            THOUGHTS[model] += thoughts
            return {"text": r.text, "input_tokens": u.prompt_token_count or 0,
                    "output_tokens": (u.candidates_token_count or 0) + thoughts, "thoughts": thoughts,
                    "flex": False}
        except Exception as exc:  # retried like the package does
            last = exc
            if not re.search(r"429|500|503|unavailable|exhausted|overloaded", str(exc), re.I):
                raise
    raise last


def on_gemini(arm):
    def swap(block):
        model = block.params().get("model")
        return block.but(model=SWAP[model]) if model in SWAP else block
    return dataclasses.replace(arm, name="current-gemini",
                               expand=tuple(swap(b) for b in arm.expand),
                               annotate=tuple(swap(b) for b in arm.annotate),
                               read=swap(arm.read), note=arm.note + ", on Gemini")


def cost(trace, prices):
    rows, total = [], 0.0
    for step in trace.steps:
        model = str(step.model)
        if model in ("None", "") or not int(step.calls or 0):
            continue
        p_in, p_out = prices.get(model, PRICES.get(model, (0, 0)))
        usd = int(step.input_tokens) * p_in / 1e6 + int(step.output_tokens) * p_out / 1e6
        total += usd
        rows.append({"block": step.block, "model": model, "calls": int(step.calls),
                     "input_tokens": int(step.input_tokens), "output_tokens": int(step.output_tokens),
                     "seconds": float(step.seconds), "usd": round(usd, 5)})
    return rows, round(total, 5)


def summary(res):
    v = res.verdict
    return {"verdict": v.call, "distribution": v.distribution.as_dict() if v.distribution else None,
            "found": res.counts.get("found"), "read": res.counts.get("read"),
            "pmids": list(v.pmids), "justification": v.justification,
            "synonyms": res.terms.get("synonyms"), "broadened": res.terms.get("broadened")}


def main():
    gene = sys.argv[1] if len(sys.argv) > 1 else "HAND1"
    phenotype = sys.argv[2] if len(sys.argv) > 2 else "congenital heart disease"
    query = Query(gene, phenotype)
    runs_dir = os.path.join(OUT, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    llm_service._call_gemini = call_gemini

    out = {"gene": gene, "phenotype": phenotype, "levels": LEVELS}
    for label, arm in (("claude", arms.CURRENT), ("gemini", on_gemini(arms.CURRENT))):
        THOUGHTS.clear()
        res = flow_run.run(arm, query, runs_dir=runs_dir)
        store.save(res, runs_dir)
        rows, usd = cost(res.trace, PRICES)
        entry = {"arm": arm.name, "fingerprint": arm.fingerprint(), "usd": usd, "blocks": rows,
                 **summary(res)}
        if label == "gemini":
            entry["thinking_tokens"] = dict(THOUGHTS)
            entry["usd_from_2027"] = cost(res.trace, {**PRICES, **PRICES_LATER})[1]
        out[label] = entry
        print(f"{label}: {res.verdict.call}, {res.counts.get('read')} read of "
              f"{res.counts.get('found')}, ${usd:.4f}")
        for r in rows:
            print(f"   {r['block']:16s} {r['model']:24s} calls {r['calls']:2d}  in {r['input_tokens']:6d}  "
                  f"out {r['output_tokens']:5d}  {r['seconds']:5.1f}s  ${r['usd']:.4f}")
    print("gemini thinking tokens:", out["gemini"]["thinking_tokens"])
    slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{gene}_{phenotype}").strip("_").lower()
    with open(os.path.join(OUT, f"{slug}.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
