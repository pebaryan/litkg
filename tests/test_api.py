from __future__ import annotations

from helpers import BERT, UNRELATED, FakeFetcher

from litkg.api import API_VERSION, ReferenceBackend, make_entry


def test_make_entry_accepts_loose_fields() -> None:
    entry = make_entry(key="x", title="T", authors="Doe, Jane and Roe, R.", year="2021a", eprint="1706.03762", entry_type="Article")
    assert entry.authors == ["Doe, Jane", "Roe, R."]
    assert entry.year == 2021
    assert entry.entry_type == "article"
    assert entry.fields["eprint"] == "1706.03762"


def test_backend_verifies_entries_and_reports_plain_data() -> None:
    backend = ReferenceBackend(fetcher=FakeFetcher(dois={"10.1000/soil.2015.1": UNRELATED}), workers=1)
    good, wrong, empty = backend.verify(
        [
            make_entry(key="bert", title=BERT["title"][0], authors=["Devlin, Jacob", "Chang, Ming-Wei"], year=2019, entry_type="inproceedings"),
            make_entry(key="resnet", title="Deep Residual Learning for Image Recognition", authors="He, Kaiming", year=2016, doi="10.1000/soil.2015.1"),
            make_entry(key="blank", entry_type="article"),
        ]
    )
    assert good.status == "verified" and good.severity == "note"
    assert wrong.status == "mismatch" and wrong.severity == "error"
    assert wrong.candidate.doi == "10.1109/cvpr.2016.90"
    assert "missing-title" in [f.code for f in empty.findings]
    assert wrong.to_dict()["findings"][0]["code"] == "title-mismatch"
    assert API_VERSION == 1


def test_backend_offline_uses_library_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("litkg.api.library_index", lambda path: {"title:an unpublished internal study": "urn:paper"})
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{local, title={An Unpublished Internal Study}, author={Doe, Jane}, year=2021}", encoding="utf-8")
    with ReferenceBackend(online=False, store="store.ttl") as backend:
        [verdict] = backend.verify(backend.load_bibliography(bib))
    assert verdict.key == "local"
    assert verdict.status == "in-library"
    assert verdict.library_paper == "urn:paper"
    assert backend.suggest("anything") == []
