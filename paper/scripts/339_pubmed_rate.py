"""Time a handful of PubMed esearch calls at the current NCBI pace.

No Anthropic key, no pair assessment. Reports whether NCBI_API_KEY is set
and how long eight small searches take, which is the difference the rate
gate makes (2.5/s without a key, 9/s with one).

  python3 paper/scripts/339_pubmed_rate.py
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from pesto.services import pubmed_service  # noqa: E402


def main():
    n = 8
    t0 = time.perf_counter()
    ok = 0
    for i in range(n):
        resp = pubmed_service.make_api_request_with_retry(
            f"{pubmed_service.BASE_URL_NCBI}esearch.fcgi",
            {"db": "pubmed", "term": "DDX41[Text Word]", "retmax": "1",
             "retmode": "json",
             **({"api_key": pubmed_service.NCBI_API_KEY}
                if pubmed_service.NCBI_API_KEY else {})})
        if resp is not None:
            ok += 1
    elapsed = time.perf_counter() - t0
    pace = pubmed_service.pubmed_rate()
    print(f"ncbi_key\t{bool(pubmed_service.NCBI_API_KEY)}")
    print(f"ncbi_per_second\t{pace}")
    print(f"calls\t{n}")
    print(f"ok\t{ok}")
    print(f"seconds\t{elapsed:.2f}")
    print(f"observed_per_second\t{(ok / elapsed) if elapsed else 0:.2f}")
    print(f"expected_seconds_at_cap\t{n / pace:.2f}")
    print("with_key_would_be\t9.0/s")
    return 0 if ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
