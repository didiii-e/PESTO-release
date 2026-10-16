"""Check the citations of PESTO and of the closed-book model on the Fig. 2c pairs.

The question: when each configuration names the papers behind its verdict, do
those papers exist, are they the papers it says they are, and do they bear on
the gene-phenotype pair? Both arms go through the same checks.

PESTO: the PMIDs in the justification of the `current` runs behind Fig. 2c
(results/prior_year10/runs/flow/*__ff136250f372.json). They are drawn from the
articles it read, so they exist by construction.

Closed book: the references of scripts/272_knowledge_citations.py. Each one is
resolved against PubMed:
  pmid_correct          the PMID given is the paper described
  pmid_wrong_paper_real the PMID points elsewhere (or nowhere), but a title
                        search finds the paper described
  pmid_wrong_unresolved the PMID points elsewhere (or nowhere), and no paper
                        matching the description is found
  no_pmid_resolved      no PMID given, the paper is found by title
  no_pmid_unresolved    no PMID given, no matching paper found
"Unresolved" means not found by these searches, not proven fabricated.

Every resolved paper of either arm is then read by Haiku, blind to the arm,
against the pair (src/pesto/prompts/citation_support_judge.txt):
  A human genetic evidence for the pair, B other bearing, C unrelated.
Reference: the PMIDs GenCC curators submitted for the pair (Limited class).

Writes results/knowledge_citations/:
  pubmed_records.json   PubMed metadata and abstracts, cached
  judge_cache.json      Haiku labels keyed by pmid|gene|phenotype, cached
  ref_checks.tsv        one row per citation, both arms
  pair_summary.tsv      one row per pair and arm
  bin_summary.tsv       the same aggregated by 3-year window of first report

  PESTO_PROJECT_ROOT=$PWD python3 scripts/273_verify_citations.py [--no-judge]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PESTO_PROJECT_ROOT", str(ROOT))

from pesto.cost import capturing
from pesto.harness import MODELS
from pesto.services.llm_service import call_llm_with_usage
from pesto.services.pubmed_service import (
    BASE_URL_NCBI, NCBI_API_KEY, make_api_request_with_retry,
)
from pesto.utils.helpers import load_prompt

OUT = ROOT / "results" / "knowledge_citations"
SAMPLE = ROOT / "results" / "prior_year10" / "sample.tsv"
FLOW = ROOT / "results" / "prior_year10" / "runs" / "flow"
CURRENT_FP = "ff136250f372"
KNOW_RUNS = OUT / "runs.json"
RECORDS = OUT / "pubmed_records.json"
JUDGED = OUT / "judge_cache.json"
GENCC = ROOT / "data" / "raw" / "gencc-submissions.tsv"
HGNC = ROOT / "data" / "hgnc_complete_set.txt"
REAPP = {"39971408", "33831308", "31983240", "29959160"}
PMID_IN_TEXT = re.compile(r"\b\d{7,8}\b")
JUDGE = load_prompt("citation_support_judge")
WORKERS = 8
LOCK = threading.Lock()
STOP = {"a", "an", "the", "of", "in", "and", "or", "with", "to", "for", "by",
        "on", "is", "are", "as", "at", "from", "its", "their", "into"}
GRADES_PRESENT = ("Existing", "Established")


def load_tsv(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def save_tsv(path, rows, cols):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def year_bin(year):
    y = int(year)
    if y <= 2010:
        return "2010"
    for lo in (2011, 2014, 2017, 2020):
        if y <= lo + 2:
            return f"{lo}-{lo + 2}"
    return "2023-2025"


def ascii_fold(text):
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()


def norm_title(text):
    return re.sub(r"[^a-z0-9 ]+", " ", ascii_fold(text).lower()).split()


def title_sim(a, b):
    return SequenceMatcher(None, " ".join(norm_title(a)), " ".join(norm_title(b))).ratio()


def surname(author):
    a = ascii_fold(author).lower().replace("et al", "")
    a = re.split(r"[,;]", a)[0].strip()
    toks = [t for t in re.split(r"[\s.]+", a) if t]
    if not toks:
        return ""
    # "Iuso A" and "Van de Vondel" alike: drop trailing initials.
    while len(toks) > 1 and len(toks[-1]) <= 2:
        toks.pop()
    return " ".join(toks)


# ------------------------------------------------------------------ PubMed

def efetch(pmids):
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    resp = make_api_request_with_retry(f"{BASE_URL_NCBI}efetch.fcgi", params, timeout=60)
    if resp is None:
        raise RuntimeError(f"efetch failed for {len(pmids)} PMIDs")
    out = {}
    root = ET.fromstring(resp.content)
    # GeneReviews chapters and other books come back as PubmedBookArticle.
    for art in root.findall(".//PubmedBookArticle"):
        pmid = (art.findtext(".//BookDocument/PMID") or "").strip()
        title_el = art.find(".//ArticleTitle")
        if title_el is None:
            title_el = art.find(".//Book/BookTitle")
        first = art.find(".//AuthorList/Author")
        out[pmid] = {
            "pmid": pmid,
            "title": "".join(title_el.itertext()).strip() if title_el is not None else "",
            "abstract": " ".join("".join(el.itertext()).strip()
                                 for el in art.findall(".//Abstract/AbstractText")),
            "first_author": (first.findtext("LastName") or "").strip() if first is not None else "",
            "year": (art.findtext(".//Book/PubDate/Year") or "").strip(),
            "journal": (art.findtext(".//Book/BookTitle") or "").strip(),
        }
    for art in root.findall(".//PubmedArticle"):
        pmid = (art.findtext(".//MedlineCitation/PMID") or "").strip()
        title = "".join(art.find(".//ArticleTitle").itertext()).strip() \
            if art.find(".//ArticleTitle") is not None else ""
        abstract = " ".join("".join(el.itertext()).strip()
                            for el in art.findall(".//Abstract/AbstractText"))
        first = art.find(".//AuthorList/Author")
        author = ""
        if first is not None:
            author = (first.findtext("LastName") or first.findtext("CollectiveName") or "").strip()
        year = (art.findtext(".//JournalIssue/PubDate/Year")
                or (art.findtext(".//JournalIssue/PubDate/MedlineDate") or "")[:4]
                or art.findtext(".//ArticleDate/Year") or "")
        out[pmid] = {"pmid": pmid, "title": title, "abstract": abstract,
                     "first_author": author, "year": year.strip(),
                     "journal": (art.findtext(".//Journal/ISOAbbreviation")
                                 or art.findtext(".//Journal/Title") or "").strip()}
    return out


def esearch(term, retmax=5):
    params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": retmax}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    resp = make_api_request_with_retry(f"{BASE_URL_NCBI}esearch.fcgi", params)
    if resp is None:
        return []
    return resp.json().get("esearchresult", {}).get("idlist", [])


class Records:
    """PubMed records, fetched once and kept on disk. A PMID PubMed does not
    know is stored as None for the run, and asked again on the next one."""

    def __init__(self):
        cached = json.loads(RECORDS.read_text()) if RECORDS.exists() else {}
        # Records released without their abstract (copyright) are fetched again.
        self.data = {k: v for k, v in cached.items() if v and "abstract" in v}

    def get(self, pmids):
        need = sorted({p for p in pmids if p and p not in self.data})
        for i in range(0, len(need), 150):
            chunk = need[i:i + 150]
            got = efetch(chunk)
            with LOCK:
                for p in chunk:
                    self.data[p] = got.get(p)
        return {p: self.data.get(p) for p in pmids if p}

    def save(self):
        RECORDS.write_text(json.dumps(self.data, indent=0), encoding="utf-8")


def describes(rec, ref):
    """Does this PubMed record match the paper the reference describes?"""
    if not rec:
        return False
    sim = title_sim(rec["title"], ref.get("title", ""))
    same_author = bool(surname(ref.get("first_author", ""))) and \
        surname(ref["first_author"]) == surname(rec["first_author"])
    try:
        close_year = abs(int(ref.get("year") or 0) - int(rec["year"] or 0)) <= 1
    except ValueError:
        close_year = False
    return sim >= 0.7 or (same_author and close_year and sim >= 0.4)


def find_by_description(ref, gene, records):
    """Search PubMed for the paper a reference describes; its PMID or ''."""
    words = [w for w in norm_title(ref.get("title", "")) if w not in STOP and len(w) > 2]
    words = sorted(set(words), key=len, reverse=True)[:8]
    terms = []
    try:
        y = int(ref.get("year") or 0)
        years = f" AND {y - 1}:{y + 1}[dp]" if y else ""
    except ValueError:
        years = ""
    if words:
        terms.append(" AND ".join(f"{w}[ti]" for w in words) + years)
    name = surname(ref.get("first_author", ""))
    if name:
        terms.append(f"{name}[1au] AND {gene}[tiab]{years}")
    seen = []
    for term in terms:
        for p in esearch(term):
            if p not in seen:
                seen.append(p)
    if not seen:
        return ""
    recs = records.get(seen)
    best = max(seen, key=lambda p: title_sim((recs.get(p) or {}).get("title", ""),
                                             ref.get("title", "")))
    return best if describes(recs.get(best), ref) else ""


def resolve(ref, gene, records):
    pmid = ref.get("pmid", "")
    if pmid:
        rec = records.get([pmid]).get(pmid)
        if describes(rec, ref):
            return "pmid_correct", pmid, rec is not None
        found = find_by_description(ref, gene, records)
        status = "pmid_wrong_paper_real" if found else "pmid_wrong_unresolved"
        return status, found, rec is not None
    found = find_by_description(ref, gene, records)
    return ("no_pmid_resolved" if found else "no_pmid_unresolved"), found, None


# ------------------------------------------------------------------ inputs

def gencc_gold(sample):
    keys = {(r["gene"], r["disease_curie"]) for r in sample}
    gold = defaultdict(set)
    with GENCC.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            key = ((r.get("gene_symbol") or "").strip(), (r.get("disease_curie") or "").strip())
            if key in keys and r.get("classification_title") == "Limited":
                gold[key] |= set(re.findall(r"\d{5,9}", r.get("submitted_as_pmids") or "")) - REAPP
    return gold


def aliases():
    out = {}
    for r in load_tsv(HGNC):
        names = [n for col in ("alias_symbol", "prev_symbol")
                 for n in (r.get(col) or "").strip('"').split("|") if n]
        out[r["symbol"]] = names
    return out


def pesto_citations(pair):
    slugged = re.sub(r"[^a-z0-9]+", "_", f"{pair['gene']}_{pair['phenotype']}".lower()).strip("_")
    path = FLOW / f"{slugged}__{CURRENT_FP}.json"
    if not path.exists():
        hits = [p for p in FLOW.glob(f"*__{CURRENT_FP}.json")
                if json.loads(p.read_text()).get("gene") == pair["gene"]
                and json.loads(p.read_text()).get("phenotype") == pair["phenotype"]]
        if not hits:
            raise FileNotFoundError(f"no current run for {pair['gene']} / {pair['phenotype']}")
        path = hits[0]
    run = json.loads(path.read_text())
    read = {a["pmid"] for a in run.get("articles") or []}
    cited = []
    for p in PMID_IN_TEXT.findall(run["verdict"].get("justification") or ""):
        if p not in cited:
            cited.append(p)
    return run["verdict"]["call"], cited, read


# ------------------------------------------------------------------ judge

def judge_one(pmid, gene, phenotype, rec, alias_names):
    note = (f"{gene} may appear under another symbol: {', '.join(alias_names)}.\n"
            if alias_names else "")
    text = JUDGE.format(gene_name=gene, phenotype=phenotype, alias_note=note,
                        pmid=pmid, title=rec.get("title", ""),
                        journal=rec.get("journal", ""), year=rec.get("year", ""),
                        abstract=rec.get("abstract") or "(no abstract)")
    for _ in range(2):
        with capturing() as cap:
            resp = call_llm_with_usage(text, MODELS["haiku"], 0.0,
                                       agent_name="citation_judge") or {}
        raw = resp.get("text", "") or ""
        m = re.search(r"<label>\s*([ABC])\s*</label>", raw)
        if m:
            reason = re.search(r"<reason>(.*?)</reason>", raw, re.S)
            return {"label": m.group(1),
                    "reason": reason.group(1).strip() if reason else "",
                    "usd": cap.summary(MODELS["haiku"]).get("usd", 0)}
    return {"label": "", "reason": "PARSE_FAIL", "usd": 0}


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-judge", action="store_true",
                    help="resolve citations only, no Haiku calls")
    args = ap.parse_args()

    sample = load_tsv(SAMPLE)
    know = {(r["gene"], r["phenotype"]): r for r in json.loads(KNOW_RUNS.read_text())
            if not r.get("error")}
    missing = [p for p in sample if (p["gene"], p["phenotype"]) not in know]
    if missing:
        print(f"ERROR: {len(missing)} pairs lack a closed-book run; "
              "finish scripts/272_knowledge_citations.py first", file=sys.stderr)
        return 1
    gold = gencc_gold(sample)
    alias = aliases()
    records = Records()

    # Every citation of both arms, as (pair, arm, rank, given ref).
    cites = []
    pesto_verdict = {}
    for p in sample:
        key = (p["gene"], p["phenotype"])
        call, cited, read = pesto_citations(p)
        pesto_verdict[key] = call
        for i, pmid in enumerate(cited, 1):
            cites.append({"pair": p, "arm": "pesto", "rank": i,
                          "ref": {"pmid": pmid}, "in_read": pmid in read})
        for i, ref in enumerate(know[key].get("refs") or [], 1):
            cites.append({"pair": p, "arm": "knowledge", "rank": i, "ref": ref})

    records.get([c["ref"]["pmid"] for c in cites if c["ref"].get("pmid")])
    records.save()
    print(f"{len(cites)} citations "
          f"({sum(c['arm'] == 'pesto' for c in cites)} PESTO, "
          f"{sum(c['arm'] == 'knowledge' for c in cites)} closed book); "
          f"{len(records.data)} PubMed records cached", flush=True)

    def check(c):
        gene = c["pair"]["gene"]
        if c["arm"] == "pesto":
            pmid = c["ref"]["pmid"]
            exists = records.get([pmid]).get(pmid) is not None
            c.update(status="pmid_correct" if exists else "pmid_wrong_unresolved",
                     resolved=pmid if exists else "", pmid_exists=exists)
        else:
            status, found, exists = resolve(c["ref"], gene, records)
            c.update(status=status, resolved=found, pmid_exists=exists)
        return c

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(check, [c for c in cites if c["arm"] == "knowledge"]))
    for c in cites:
        if c["arm"] == "pesto":
            check(c)
    records.save()

    judged = json.loads(JUDGED.read_text()) if JUDGED.exists() else {}
    if not args.no_judge:
        todo = {}
        for c in cites:
            if c["resolved"]:
                k = f"{c['resolved']}|{c['pair']['gene']}|{c['pair']['phenotype']}"
                if k not in judged:
                    todo[k] = c
        print(f"judging {len(todo)} paper-pair combinations with Haiku "
              f"({len(judged)} cached)", flush=True)

        def run(item):
            k, c = item
            g, ph = c["pair"]["gene"], c["pair"]["phenotype"]
            rec = records.data.get(c["resolved"]) or {}
            out = judge_one(c["resolved"], g, ph, rec, alias.get(g, []))
            with LOCK:
                judged[k] = out
                if len(judged) % 50 == 0:
                    JUDGED.write_text(json.dumps(judged, indent=0), encoding="utf-8")
            return out

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            list(pool.map(run, todo.items()))
        JUDGED.write_text(json.dumps(judged, indent=0), encoding="utf-8")

    rows = []
    for c in cites:
        p, ref = c["pair"], c["ref"]
        rec = records.data.get(c["resolved"]) or {}
        j = judged.get(f"{c['resolved']}|{p['gene']}|{p['phenotype']}", {}) if c["resolved"] else {}
        rows.append({
            "year": p["year"], "bin": year_bin(p["year"]), "gene": p["gene"],
            "phenotype": p["phenotype"], "arm": c["arm"], "rank": c["rank"],
            "given_pmid": ref.get("pmid", ""),
            "given_author": ref.get("first_author", ""),
            "given_year": ref.get("year", ""), "given_title": ref.get("title", ""),
            "status": c["status"], "pmid_exists": c["pmid_exists"],
            "resolved_pmid": c["resolved"], "resolved_title": rec.get("title", ""),
            "in_gencc": bool(c["resolved"]) and c["resolved"] in gold[(p["gene"], p["disease_curie"])],
            "label": j.get("label", ""), "reason": j.get("reason", ""),
        })
    save_tsv(OUT / "ref_checks.tsv", rows, list(rows[0]))

    by_pair = defaultdict(list)
    for r in rows:
        by_pair[(r["gene"], r["phenotype"], r["arm"])].append(r)
    pairs = []
    for p in sample:
        key = (p["gene"], p["phenotype"])
        for arm in ("pesto", "knowledge"):
            rs = by_pair.get((p["gene"], p["phenotype"], arm), [])
            verdict = pesto_verdict[key] if arm == "pesto" else know[key]["verdict"]
            g = gold[(p["gene"], p["disease_curie"])]
            found = {r["resolved_pmid"] for r in rs} & g
            exact = {r["given_pmid"] for r in rs if r["status"] == "pmid_correct"} & g
            pairs.append({
                "year": p["year"], "bin": year_bin(p["year"]), "gene": p["gene"],
                "phenotype": p["phenotype"], "arm": arm, "verdict": verdict,
                "present": verdict in GRADES_PRESENT,
                "n_cited": len(rs),
                "n_real": sum(bool(r["resolved_pmid"]) for r in rs),
                "n_unresolved": sum(r["status"].endswith("unresolved") for r in rs),
                "n_pmid_wrong": sum(r["status"].startswith("pmid_wrong") for r in rs),
                "n_gencc": len(g),
                "gencc_found": len(found),
                "gencc_exact_pmid": len(exact),
                "any_gencc": bool(found),
                "any_gencc_exact_pmid": bool(exact),
                "any_A": any(r["label"] == "A" for r in rs),
                "any_AB": any(r["label"] in ("A", "B") for r in rs),
            })
    save_tsv(OUT / "pair_summary.tsv", pairs, list(pairs[0]))

    both_present = {(r["gene"], r["phenotype"]) for r in pairs if r["arm"] == "pesto" and r["present"]} & \
                   {(r["gene"], r["phenotype"]) for r in pairs if r["arm"] == "knowledge" and r["present"]}
    summary = []
    for b in ("2010", "2011-2013", "2014-2016", "2017-2019", "2020-2022", "2023-2025", "all"):
        for arm in ("pesto", "knowledge"):
            for subset in ("all", "both_present"):
                xs = [r for r in pairs if r["arm"] == arm and (b == "all" or r["bin"] == b)
                      and (subset == "all" or (r["gene"], r["phenotype"]) in both_present)]
                cs = [r for r in rows if r["arm"] == arm and (b == "all" or r["bin"] == b)
                      and (subset == "all" or (r["gene"], r["phenotype"]) in both_present)]
                if not xs:
                    continue
                summary.append({
                    "bin": b, "arm": arm, "subset": subset, "pairs": len(xs),
                    "pairs_citing": sum(r["n_cited"] > 0 for r in xs),
                    "pairs_gencc": sum(r["any_gencc"] for r in xs),
                    "pairs_gencc_exact_pmid": sum(r["any_gencc_exact_pmid"] for r in xs),
                    "gencc_pmids": sum(r["n_gencc"] for r in xs),
                    "gencc_found": sum(r["gencc_found"] for r in xs),
                    "gencc_exact_pmid": sum(r["gencc_exact_pmid"] for r in xs),
                    "pairs_A": sum(r["any_A"] for r in xs),
                    "pairs_AB": sum(r["any_AB"] for r in xs),
                    "citations": len(cs),
                    "cit_pmid_given": sum(bool(r["given_pmid"]) for r in cs),
                    "cit_pmid_correct": sum(r["status"] == "pmid_correct" for r in cs),
                    "cit_pmid_wrong": sum(r["status"].startswith("pmid_wrong") for r in cs),
                    "cit_unresolved": sum(r["status"].endswith("unresolved") for r in cs),
                    "cit_real": sum(bool(r["resolved_pmid"]) for r in cs),
                    "cit_A": sum(r["label"] == "A" for r in cs),
                    "cit_B": sum(r["label"] == "B" for r in cs),
                    "cit_C": sum(r["label"] == "C" for r in cs),
                })
    save_tsv(OUT / "bin_summary.tsv", summary, list(summary[0]))

    print(f"\n{'bin':10s} {'arm':9s} {'subset':12s} pairs cite gencc exact "
          f"refs found exact  A   AB | cits pmidOK pmidWrong unres  A   B   C")
    for s in summary:
        print(f"{s['bin']:10s} {s['arm']:9s} {s['subset']:12s} {s['pairs']:4d} "
              f"{s['pairs_citing']:4d} {s['pairs_gencc']:5d} "
              f"{s['pairs_gencc_exact_pmid']:5d} {s['gencc_pmids']:4d} "
              f"{s['gencc_found']:5d} {s['gencc_exact_pmid']:5d} {s['pairs_A']:3d} "
              f"{s['pairs_AB']:4d} | {s['citations']:4d} {s['cit_pmid_correct']:6d} "
              f"{s['cit_pmid_wrong']:9d} {s['cit_unresolved']:5d} {s['cit_A']:3d} "
              f"{s['cit_B']:3d} {s['cit_C']:3d}")
    usd = sum(float(v.get("usd") or 0) for v in judged.values())
    print(f"\nHaiku judge, all cached labels: ${usd:.2f}")
    print(f"wrote {OUT.relative_to(ROOT)}/ref_checks.tsv, pair_summary.tsv, bin_summary.tsv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
