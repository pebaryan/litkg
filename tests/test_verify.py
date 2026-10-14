from __future__ import annotations

import io
from urllib.error import HTTPError

import pytest
from helpers import BERT, HE_2016, UNRELATED, FakeFetcher

from litkg.parser import ReferenceInfo
from litkg.verify import (
    HttpClient,
    LookupFailed,
    Verifier,
    arxiv_id_for,
    compare,
    latex_to_text,
    normalize_doi,
    person,
    record_from_csl,
    title_similarity,
)


def entry(**kwargs) -> ReferenceInfo:
    return ReferenceInfo(raw_text="", **kwargs)


def test_latex_to_text_and_title_similarity() -> None:
    assert latex_to_text(r"{BERT}: Pre-training \& {Fine-Tuning} in G\"{o}del's \emph{world}") == "BERT: Pre-training & Fine-Tuning in Godel's world"
    assert title_similarity("{BERT}: Pre-training", "BERT: pre-training") == 1.0
    assert title_similarity("Deep Residual Learning for Image Recognition", "Deep residual learning for image recognition: extended") >= 0.9
    assert title_similarity("Attention Is All You Need", "A Survey of Soil Microbiomes") < 0.6


def test_person_parsing() -> None:
    assert person("Vaswani, Ashish") == ("vaswani", "a")
    assert person("Ashish Vaswani") == ("vaswani", "a")
    assert person("van der Berg, J.") == ("berg", "j")
    assert person("Lee") == ("lee", "")


def test_identifier_normalization() -> None:
    assert normalize_doi("https://doi.org/10.1109/CVPR.2016.90") == "10.1109/cvpr.2016.90"
    assert normalize_doi("doi: 10.1000/xyz.") == "10.1000/xyz"
    assert normalize_doi("not-a-doi") is None
    assert arxiv_id_for(entry(fields={"eprint": "1706.03762", "archiveprefix": "arXiv"})) == "1706.03762"
    assert arxiv_id_for(entry(fields={"url": "https://arxiv.org/abs/2001.08361v2"})) == "2001.08361"
    assert arxiv_id_for(entry(fields={"journal": "arXiv preprint arXiv:2001.08361"})) == "2001.08361"
    assert arxiv_id_for(entry(doi="10.48550/arXiv.1706.03762")) == "1706.03762"
    assert arxiv_id_for(entry(fields={"journal": "Nature"})) is None


def test_compare_detects_fabricated_authors_with_shared_surname() -> None:
    record = record_from_csl(BERT, "crossref")
    findings = compare(entry(title=BERT["title"][0], authors=["Brown, Michael", "Lee, Sarah"], year=2019), record, "the DOI")
    assert [(f.severity, f.code) for f in findings if f.code == "author-mismatch"] == [("error", "author-mismatch")]


def test_compare_tolerates_initials_order_and_preprint_years() -> None:
    record = record_from_csl(HE_2016, "doi.org")
    findings = compare(
        entry(title="Deep residual learning for image recognition", authors=["K. He", "X. Zhang", "S. Ren", "J. Sun"], year=2015, doi="10.1109/CVPR.2016.90"),
        record,
        "the DOI",
    )
    assert [(f.severity, f.code) for f in findings] == [("note", "year-mismatch")]

    swapped = compare(entry(title=HE_2016["title"], authors=["Zhang, X.", "He, K."]), record, "the DOI")
    assert [f.code for f in swapped if f.severity == "warning"] == ["author-order"]


def test_verify_doi_pointing_to_a_different_work_suggests_the_right_one() -> None:
    fetcher = FakeFetcher(dois={"10.1000/soil.2015.1": UNRELATED})
    verification = Verifier(fetcher).verify(
        entry(title="Deep Residual Learning for Image Recognition", authors=["He, Kaiming"], year=2016, doi="10.1000/soil.2015.1")
    )
    assert verification.status == "mismatch"
    assert verification.findings[0].code == "title-mismatch"
    assert verification.candidate.doi == "10.1109/cvpr.2016.90"


def test_verify_title_search_finds_doi_and_unknown_titles_stay_unverified() -> None:
    verifier = Verifier(FakeFetcher())
    found = verifier.verify(entry(title=BERT["title"][0], authors=["Devlin, Jacob"], year=2019, entry_type="inproceedings"))
    assert found.status == "verified"
    assert [f.code for f in found.findings] == ["missing-doi"]

    missing = verifier.verify(entry(title="Quantum Gradient Descent for Alignment", authors=["Smith, J."], entry_type="article"))
    assert missing.status == "unverified"
    assert missing.findings[0].code == "no-match"


def test_verify_unknown_arxiv_id_and_misc_entries() -> None:
    verifier = Verifier(FakeFetcher())
    gone = verifier.verify(entry(title="Imaginary Preprint", fields={"eprint": "2401.99999", "archiveprefix": "arXiv"}))
    assert gone.status == "not-found" and gone.findings[0].code == "arxiv-not-found"
    web = verifier.verify(entry(title="PyTorch", entry_type="misc"))
    assert web.status == "skipped"


def test_verify_many_converts_lookup_failures() -> None:
    verifier = Verifier(FakeFetcher(fail_hosts={"doi.org"}))
    [result] = verifier.verify_many([entry(title="x y z", doi="10.1109/CVPR.2016.90")], workers=1)
    assert result.status == "unverified"
    assert result.findings[0].code == "lookup-failed"


def test_suggest_ranks_candidates() -> None:
    ranked = Verifier(FakeFetcher()).suggest(entry(title="Deep Residual Learning"))
    assert ranked[0][1].doi == "10.1109/cvpr.2016.90"
    assert ranked[0][0] >= ranked[-1][0]


class FakeHandle:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body.encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def test_http_client_caches_retries_and_sends_user_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("litkg.verify.time.sleep", lambda seconds: None)
    calls = []

    def opener(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 503, "busy", {}, io.BytesIO(b""))
        return FakeHandle(200, '{"ok": true}')

    client = HttpClient(cache_dir=tmp_path, mailto="me@example.org", opener=opener)
    assert client.get("https://doi.org/10.1/x").body == '{"ok": true}'
    assert len(calls) == 2
    assert "mailto:me@example.org" in calls[-1].get_header("User-agent")
    client.save()

    cached = HttpClient(cache_dir=tmp_path, opener=lambda *a, **k: pytest.fail("should use cache"))
    assert cached.get("https://doi.org/10.1/x").status == 200


def test_http_client_returns_404_and_raises_after_retries(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("litkg.verify.time.sleep", lambda seconds: None)

    def not_found(request, timeout):
        raise HTTPError(request.full_url, 404, "missing", {}, io.BytesIO(b""))

    assert HttpClient(cache_dir=None, opener=not_found).get("https://doi.org/10.1/missing").status == 404

    def offline(request, timeout):
        raise OSError("network unreachable")

    with pytest.raises(LookupFailed):
        HttpClient(cache_dir=None, opener=offline, retries=2).get("https://doi.org/10.1/y")
