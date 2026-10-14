from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from helpers import BERT, HE_2016, FakeFetcher

from litkg.check import CheckOptions, check_paper, load_config
from litkg.citations import find_citations
from litkg.manuscript import load_manuscript
from litkg.parser import parse_bibliography
from litkg.verify import Verifier

FIXTURE = Path(__file__).parent / "fixtures" / "paper"


@pytest.fixture()
def paper(tmp_path) -> Path:
    target = tmp_path / "paper"
    shutil.copytree(FIXTURE, target)
    return target / "main.tex"


def _result(report, key):
    return next(result for result in report.results if result.key == key)


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


# --------------------------------------------------------------------------- citations & manuscript


def test_find_citations_reports_line_and_column() -> None:
    text = "Intro.\nAs shown \\citep[p.~2]{alpha, beta}.\n"
    found = [(c.key, c.line, c.column) for c in find_citations(text)]
    assert found == [("alpha", 2, 23), ("beta", 2, 30)]


def test_find_citations_ignores_verbatim_and_html_comments() -> None:
    latex = "\\begin{verbatim}\\cite{code}\\end{verbatim} \\cite{real}"
    assert [c.key for c in find_citations(latex)] == ["real"]
    markdown = "---\ntitle: x\n---\n<!-- [@hidden] --> Real [@shown]."
    assert [c.key for c in find_citations(markdown, "markdown")] == ["shown"]


def test_manuscript_follows_inputs_in_document_order(paper) -> None:
    manuscript = load_manuscript(paper)
    assert manuscript.keys[:2] == ["vaswani2017attention", "undefined2024"]
    assert manuscript.bibliographies == [str(paper.parent / "refs.bib")]
    first = manuscript.locations("vaswani2017attention")[0]
    assert Path(first.path).name == "intro.tex" and first.line == 2


def test_manuscript_reports_missing_includes_and_bibliographies(tmp_path) -> None:
    main = tmp_path / "main.tex"
    main.write_text("\\input{nope}\n\\cite{a}\n\\addbibresource{missing.bib}\n", encoding="utf-8")
    manuscript = load_manuscript(main)
    references = [item[0] for item in manuscript.missing]
    assert "nope" in references
    assert any(item.endswith("missing.bib") for item in references)


def test_markdown_front_matter_bibliography(tmp_path) -> None:
    (tmp_path / "a.bib").write_text("@misc{a, title={A thing}}", encoding="utf-8")
    (tmp_path / "b.json").write_text('[{"id": "b", "title": "B thing"}]', encoding="utf-8")
    doc = tmp_path / "paper.md"
    doc.write_text("---\ntitle: T\nbibliography:\n  - a.bib\n  - b.json\n---\n\nSee [@a; @b].\n", encoding="utf-8")
    manuscript = load_manuscript(doc)
    assert manuscript.keys == ["a", "b"]
    assert [Path(path).name for path in manuscript.bibliographies] == ["a.bib", "b.json"]


def test_bibtex_parser_handles_strings_comments_and_concatenation(tmp_path) -> None:
    bib = tmp_path / "refs.bib"
    bib.write_text(
        '@string{nips = "NeurIPS"}\n@comment{@article{ghost, title={No}}}\n'
        '@inproceedings{k, title={{BERT}: X}, author={A, B and C, D}, booktitle=nips # " 2019", year=2019, eprint={1810.04805}}',
        encoding="utf-8",
    )
    entries = parse_bibliography(str(bib)).entries
    assert [entry.key for entry in entries] == ["k"]
    assert entries[0].venue == "NeurIPS 2019"
    assert entries[0].fields["eprint"] == "1810.04805"
    assert entries[0].entry_type == "inproceedings"


# --------------------------------------------------------------------------- offline checks


def test_offline_check_flags_undefined_keys(paper) -> None:
    report = check_paper(paper)
    assert not report.passed
    assert _result(report, "undefined2024").status == "undefined"
    assert _result(report, "he2016deep").status == "unchecked"
    issue = _result(report, "undefined2024").issues[0]
    assert Path(issue.path).name == "intro.tex" and issue.line == 3


def test_offline_check_flags_malformed_entries_and_duplicates(tmp_path) -> None:
    (tmp_path / "refs.bib").write_text(
        "@article{a, title={Same Work}, author={X, Y}, year={2020}, doi={not-a-doi}}\n"
        "@article{b, author={X, Y}, year={2999}}\n"
        "@article{c, title={Same Work}, author={X, Y}, year={2020}}\n"
        "@article{d, title={Same Work}, author={X, Y}, year={2020}}\n",
        encoding="utf-8",
    )
    paper = tmp_path / "p.tex"
    paper.write_text("\\cite{a,b,c,d}\\bibliography{refs}", encoding="utf-8")
    report = check_paper(paper)
    assert "malformed-doi" in _codes(_result(report, "a"))
    assert {"missing-title", "implausible-year"} <= _codes(_result(report, "b"))
    assert "duplicate-work" in _codes(_result(report, "d"))


def test_offline_check_flags_conflicting_definitions(tmp_path) -> None:
    (tmp_path / "one.bib").write_text("@article{k, title={First Title}, author={A, B}, year=2020}", encoding="utf-8")
    (tmp_path / "two.bib").write_text("@article{k, title={Second Title}, author={A, B}, year=2020}", encoding="utf-8")
    paper = tmp_path / "p.tex"
    paper.write_text("\\cite{k}\\bibliography{one,two}", encoding="utf-8")
    result = _result(check_paper(paper), "k")
    assert result.status == "conflict"
    assert "one.bib" in result.issues[0].message and "two.bib" in result.issues[0].message


def test_check_without_citations_or_bibliography_fails(tmp_path) -> None:
    empty = tmp_path / "empty.tex"
    empty.write_text("No citations here.", encoding="utf-8")
    assert [issue.code for issue in check_paper(empty).issues] == ["no-citations"]
    nobib = tmp_path / "nobib.tex"
    nobib.write_text("\\cite{a}", encoding="utf-8")
    assert "no-bibliography" in [issue.code for issue in check_paper(nobib).issues]


def test_config_ignore_and_strict(paper) -> None:
    config = paper.parent / ".litkg.json"
    config.write_text(json.dumps({"ignore": {"undefined2024": "added after review"}, "strict": True}), encoding="utf-8")
    data = load_config(config)
    report = check_paper(paper, CheckOptions(ignore=data["ignore"], strict=data["strict"]))
    assert _result(report, "undefined2024").status == "ignored"
    assert report.passed


def test_strict_fails_on_warnings(tmp_path) -> None:
    (tmp_path / "refs.bib").write_text("@article{a, title={A Title}, author={X, Y}}", encoding="utf-8")
    paper = tmp_path / "p.tex"
    paper.write_text("\\cite{a}\\bibliography{refs}", encoding="utf-8")
    assert check_paper(paper).passed
    assert not check_paper(paper, CheckOptions(strict=True)).passed


# --------------------------------------------------------------------------- online checks


def test_online_check_end_to_end(paper) -> None:
    fetcher = FakeFetcher()
    report = check_paper(paper, CheckOptions(online=True, workers=1), verifier=Verifier(fetcher))

    assert _result(report, "he2016deep").status == "verified"
    assert _result(report, "vaswani2017attention").status == "verified"
    assert _result(report, "kaplan2020scaling").status == "verified"

    fabricated = _result(report, "smith2023quantum")
    assert fabricated.status == "not-found"
    assert "doi-not-found" in _codes(fabricated)

    bert = _result(report, "devlin2019bert")
    assert bert.status == "mismatch"
    assert "author-mismatch" in _codes(bert)
    assert bert.candidate.doi == "10.18653/v1/n19-1423"

    assert _result(report, "pytorch_site").status == "skipped"
    assert not report.passed
    assert any("arxiv" in url for url in fetcher.requests)


def test_online_lookup_failure_is_a_warning_not_an_error(paper) -> None:
    fetcher = FakeFetcher(fail_hosts={"doi.org", "export.arxiv.org", "api.crossref.org", "api.openalex.org"})
    report = check_paper(paper, CheckOptions(online=True, workers=1, ignore={"undefined2024": ""}), verifier=Verifier(fetcher))
    he = _result(report, "he2016deep")
    assert he.status == "unverified"
    assert "lookup-failed" in _codes(he)
    assert report.passed


def test_library_paper_counts_as_evidence(tmp_path, monkeypatch) -> None:
    (tmp_path / "refs.bib").write_text("@article{local, title={An Unpublished Internal Study}, author={Doe, Jane}, year=2021}", encoding="utf-8")
    paper = tmp_path / "p.tex"
    paper.write_text("\\cite{local}\\bibliography{refs}", encoding="utf-8")
    monkeypatch.setattr(
        "litkg.check._library_index", lambda path: {"title:an unpublished internal study": "urn:paper"}
    )
    report = check_paper(paper, CheckOptions(online=True, store="store.ttl", workers=1), verifier=Verifier(FakeFetcher(works=[])))
    result = _result(report, "local")
    assert result.status == "in-library"
    assert result.library_paper == "urn:paper"
    assert "no-match" not in _codes(result)


def test_report_json_is_serializable(paper) -> None:
    report = check_paper(paper, CheckOptions(online=True, workers=1), verifier=Verifier(FakeFetcher()))
    data = json.loads(json.dumps(report.to_dict()))
    assert data["summary"]["citations"] == 7
    assert data["passed"] is False
    bert = next(item for item in data["references"] if item["key"] == "devlin2019bert")
    assert bert["candidate"]["authors"][0] == "Devlin, Jacob"


def test_fixture_records_are_consistent() -> None:
    assert HE_2016["DOI"].lower() == "10.1109/cvpr.2016.90"
    assert BERT["author"][0]["family"] == "Devlin"
