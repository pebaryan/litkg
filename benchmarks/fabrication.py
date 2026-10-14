"""Measure how well `litkg check --online` separates real references from fabricated ones.

Real references are sampled from Crossref and frozen in ``corpus.json`` so runs are
comparable. Each real reference is turned into several test cases:

    real-doi        unchanged entry with its DOI                      must pass
    real-nodoi      same entry without DOI (found by title search)    must pass
    fake-doi        DOI suffix replaced with a nonexistent one        must fail
    swapped-doi     DOI of a different work in the corpus             must fail
    fake-authors    real title, invented authors, no DOI              must fail
    invented        invented title and authors, no DOI                must be flagged

Usage:
    python benchmarks/fabrication.py                 # uses corpus.json, cached responses
    python benchmarks/fabrication.py --new-corpus 50 # sample a fresh corpus first
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from litkg.parser import ReferenceInfo  # noqa: E402
from litkg.verify import HttpClient, Verifier, record_from_csl  # noqa: E402

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus.json"
RESULTS = HERE / "results.json"

INVENTED_FAMILIES = ["Halvorsen", "Okonkwo", "Marchetti", "Ishikawa", "Delacroix", "Varga", "Lindqvist", "Abernathy"]
INVENTED_GIVEN = ["Elena", "Tomas", "Priya", "Marcus", "Ingrid", "Kenji", "Amara", "Felix"]
INVENTED_WORDS = [
    "Adaptive", "Hierarchical", "Contrastive", "Federated", "Sparse", "Quantum", "Causal", "Latent",
    "Retrieval", "Diffusion", "Graph", "Transformers", "Calibration", "Robustness", "Alignment", "Distillation",
]
EXPECT = {
    "real-doi": "pass",
    "real-nodoi": "pass",
    "fake-doi": "fail",
    "swapped-doi": "fail",
    "fake-authors": "fail",
    "invented": "flag",
}


def sample_corpus(client: HttpClient, size: int) -> list[dict]:
    corpus: list[dict] = []
    seen: set[str] = set()
    while len(corpus) < size:
        url = "https://api.crossref.org/works?" + urlencode(
            {"sample": 50, "filter": "type:journal-article", "select": "DOI,title,author,issued,container-title,type"}
        )
        client.refresh = True  # samples are random; never reuse a cached sample
        response = client.get(url)
        client.refresh = False
        for item in json.loads(response.body)["message"]["items"]:
            record = record_from_csl(item, "crossref")
            authors = [a for a in item.get("author", []) if a.get("family") and a.get("given")]
            if (
                not record.title
                or len(record.title.split()) < 5
                or not record.year
                or not record.doi
                or not authors
                or record.doi in seen
                or not record.title.isascii()
            ):
                continue
            seen.add(record.doi)
            corpus.append(
                {
                    "title": record.title,
                    "authors": [f"{a['family']}, {a['given']}" for a in authors[:6]],
                    "year": record.year,
                    "doi": record.doi,
                    "venue": record.venue,
                }
            )
            if len(corpus) == size:
                break
    return corpus


def make_cases(corpus: list[dict], seed: int) -> list[tuple[str, int, ReferenceInfo]]:
    rng = random.Random(seed)
    cases = []
    for index, real in enumerate(corpus):
        base = {"title": real["title"], "authors": real["authors"], "year": real["year"], "entry_type": "article", "venue": real["venue"]}
        other = corpus[(index + 1 + rng.randrange(len(corpus) - 1)) % len(corpus)]
        prefix, _, _ = real["doi"].partition("/")
        invented_authors = [f"{rng.choice(INVENTED_FAMILIES)}, {rng.choice(INVENTED_GIVEN)}" for _ in range(2)]
        invented_title = " ".join(rng.sample(INVENTED_WORDS, 3)) + " for " + " ".join(rng.sample(INVENTED_WORDS, 2)) + " Systems"
        variants = {
            "real-doi": {**base, "doi": real["doi"]},
            "real-nodoi": base,
            "fake-doi": {**base, "doi": f"{prefix}/litkg.{rng.randrange(10**8, 10**9)}"},
            "swapped-doi": {**base, "doi": other["doi"]},
            "fake-authors": {**base, "authors": invented_authors},
            "invented": {"title": invented_title, "authors": invented_authors, "year": real["year"], "entry_type": "article"},
        }
        for kind, fields in variants.items():
            cases.append((kind, index, ReferenceInfo(raw_text=fields["title"], **fields)))
    return cases


def outcome(verification) -> str:
    severities = {finding.severity for finding in verification.findings}
    if "error" in severities:
        return "error"
    if "warning" in severities:
        return "warning"
    return "ok"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--new-corpus", type=int, default=0, metavar="N", help="sample N fresh real references from Crossref")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--mailto", default=None, help="contact email for the Crossref/OpenAlex polite pool")
    parser.add_argument("--cache-dir", default=str(HERE / ".cache"))
    args = parser.parse_args()

    client = HttpClient(cache_dir=args.cache_dir, mailto=args.mailto)
    if args.new_corpus:
        CORPUS.write_text(json.dumps(sample_corpus(client, args.new_corpus), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))

    cases = make_cases(corpus, args.seed)
    verifier = Verifier(client, mailto=args.mailto)
    try:
        verifications = verifier.verify_many([entry for _, _, entry in cases], workers=4)
    finally:
        client.save()

    tally: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    misses = []
    for (kind, index, entry), verification in zip(cases, verifications, strict=True):
        result = outcome(verification)
        tally[kind][result] += 1
        expected = EXPECT[kind]
        wrong = (expected == "pass" and result == "error") or (expected == "fail" and result != "error") or (
            expected == "flag" and result == "ok"
        )
        if wrong:
            misses.append(
                {
                    "kind": kind,
                    "corpus_index": index,
                    "title": entry.title,
                    "doi": entry.doi,
                    "status": verification.status,
                    "findings": [f"{f.severity}:{f.code}: {f.message}" for f in verification.findings],
                }
            )

    def rate(kind: str, outcomes: tuple[str, ...]) -> float:
        counts = tally[kind]
        total = sum(counts.values())
        return sum(counts[name] for name in outcomes) / total if total else 0.0

    summary = {
        "corpus": len(corpus),
        "cases": len(cases),
        "seed": args.seed,
        "false_failures_on_real": {kind: round(rate(kind, ("error",)), 3) for kind in ("real-doi", "real-nodoi")},
        "warnings_on_real": {kind: round(rate(kind, ("warning",)), 3) for kind in ("real-doi", "real-nodoi")},
        "fabrications_failing_gate": {kind: round(rate(kind, ("error",)), 3) for kind in ("fake-doi", "swapped-doi", "fake-authors", "invented")},
        "fabrications_flagged": {kind: round(rate(kind, ("error", "warning")), 3) for kind in ("fake-doi", "swapped-doi", "fake-authors", "invented")},
        "outcomes": {kind: dict(counts) for kind, counts in tally.items()},
    }
    RESULTS.write_text(json.dumps({"summary": summary, "misses": misses}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"{len(corpus)} real references, {len(cases)} cases (seed {args.seed})\n")
    print("| Case | Expected | Error | Warning | OK |")
    print("|---|---|---|---|---|")
    for kind in EXPECT:
        counts = tally[kind]
        total = sum(counts.values()) or 1
        print(
            f"| {kind} | {EXPECT[kind]} | {counts['error'] / total:.0%} | {counts['warning'] / total:.0%} | {counts['ok'] / total:.0%} |"
        )
    print(f"\n{len(misses)} unexpected outcome(s); details in {RESULTS.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
