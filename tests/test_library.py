from __future__ import annotations

import os

from litkg.indexer import index_directory
from litkg.parser import PaperInfo, ReferenceInfo
from litkg.store import LitStore
from litkg.triples import resolve_citation_targets


def test_reindex_reuses_unchanged_pdfs(tmp_path, monkeypatch) -> None:
    library = tmp_path / "library"
    library.mkdir()
    first = library / "a.pdf"
    second = library / "b.pdf"
    first.write_bytes(b"%PDF a")
    second.write_bytes(b"%PDF b")
    parsed: list[str] = []

    def fake_parse(path: str) -> PaperInfo:
        parsed.append(os.path.basename(path))
        return PaperInfo(
            source_path=path,
            title=f"Paper {os.path.basename(path)}",
            authors=["Doe, Jane"],
            references=[ReferenceInfo(raw_text="Ref", title="Ref")],
        )

    monkeypatch.setattr("litkg.indexer.parse_pdf", fake_parse)
    store_path = str(tmp_path / "store.ttl")

    stats = index_directory(str(library), LitStore(store_path))
    assert (stats.papers, stats.cached) == (2, 0)

    stats = index_directory(str(library), LitStore(store_path))
    assert (stats.papers, stats.cached) == (2, 2)
    assert sorted(parsed) == ["a.pdf", "b.pdf"]

    second.write_bytes(b"%PDF b changed")
    stats = index_directory(str(library), LitStore(store_path))
    assert stats.cached == 1
    assert parsed[-1] == "b.pdf"
    titles = {row["title"] for row in LitStore(store_path).query(
        "PREFIX lit: <https://litkg.dev/ontology#> SELECT ?title WHERE { ?p a lit:Paper ; lit:title ?title }"
    )}
    assert titles == {"Paper a.pdf", "Paper b.pdf"}

    index_directory(str(library), LitStore(store_path), use_cache=False)
    assert parsed.count("a.pdf") == 2


def test_fuzzy_title_matching_ignores_short_generic_titles() -> None:
    lookup = {"deep learning": "urn:short", "attention is all you need": "urn:long"}
    generic = ReferenceInfo(raw_text="Smith, J. (2020). Deep learning for robust speech recognition. In Proc. ICASSP.")
    assert resolve_citation_targets(generic, lookup) == []
    specific = ReferenceInfo(raw_text="Vaswani, A. et al. (2017). Attention is all you need. NeurIPS.")
    assert resolve_citation_targets(specific, lookup) == ["urn:long"]
    partial_word = ReferenceInfo(raw_text="Reattention is all you needed now")
    assert resolve_citation_targets(partial_word, lookup) == []


def test_cli_index_prints_summary_and_json(tmp_path) -> None:
    import json

    from click.testing import CliRunner

    from litkg.cli import cli

    library = tmp_path / "library"
    library.mkdir()
    (library / "refs.bib").write_text("@article{a, title={A Title}, author={X, Y}, year=2020}", encoding="utf-8")
    store = str(tmp_path / "store.ttl")
    runner = CliRunner()
    result = runner.invoke(cli, ["index", str(library), "--store", store])
    assert result.exit_code == 0, result.output
    assert "1 bibliography (1 entries)" in result.output
    result = runner.invoke(cli, ["index", str(library), "--store", store, "--json"])
    assert json.loads(result.output)["bibliographies"] == 1
