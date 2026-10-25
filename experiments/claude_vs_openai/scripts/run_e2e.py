"""End-to-end family runs through the real `pesto --bench` path, both families at once.

  run_e2e.py --rep r1 --pairs pairs.tsv --out runs/r1
Claude and OpenAI process the same table in the same order, concurrently, so PubMed
and Open Targets are asked the same questions at the same time of day. Each family
has its own data dir and no cache. Resumable.
"""
import argparse, contextvars, os, sys, threading, traceback

sys.path.insert(0, "/Users/dinan_elsyad/pesto_cmp")
import instr                                                     # noqa: E402
from pesto import cli                                            # noqa: E402

FAMILIES = {
    "claude": [],      # every default: the arm's own Claude models; router Opus 5 (named so its cost shows)
    "openai": ["--model", "openai:gpt-6.1-sol", "--model-fast", "openai:gpt-6-luna",
               "--router-model", "openai:gpt-6.1-sol",
               "--ot-gate-model", "openai:gpt-6-luna",
               "--ot-reader-model", "openai:gpt-6.1-sol"],
}
COMMON = ["--arm", "auto", "--no-cache", "--workers", "3", "--resume"]


def argv_for(fam, pairs, outdir):
    d = os.path.join(outdir, fam)
    os.makedirs(d, exist_ok=True)
    extra = FAMILIES[fam] or ["--router-model", "opus5"]
    return (["--bench", pairs, "--out", os.path.join(d, "pesto.tsv"),
             "--data-dir", os.path.join(d, "data")] + COMMON + extra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rep", required=True)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--families", nargs="+", default=["claude", "openai"])
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    instr.OUT["dir"] = a.out
    instr.install()
    codes = {}

    def go(fam):
        instr.CTX.set({"fam": fam, "rep": a.rep})
        try:
            codes[fam] = cli.main(argv_for(fam, a.pairs, a.out))
        except BaseException as e:                        # noqa: BLE001
            traceback.print_exc()
            codes[fam] = f"{type(e).__name__}: {e}"

    threads = []
    for fam in a.families:
        t = threading.Thread(target=contextvars.copy_context().run, args=(go, fam), name=fam)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    print("exit codes:", codes, "| spend so far $%.2f" % instr.spent(), file=sys.stderr)


if __name__ == "__main__":
    main()
