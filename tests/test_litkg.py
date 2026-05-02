from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
import json

import litkg.parser as parser
from litkg.indexer import index_directory
from litkg.export import bibliography_graph, citation_graph
from litkg.cli import cli
from litkg.queries import (
    annotated_bibliography,
    list_bibliographies,
    list_papers,
    list_reading_lists,
    paper_references,
    papers_by_author,
    papers_cited_by,
    papers_citing,
    papers_in_list,
    papers_without_lists,
    search,
)
from litkg.report import annotated_bibliography_html, annotated_bibliography_pdf
from litkg.store import LitStore


class FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self):
        return self._text


class FakeReader:
    def __init__(self, path: str):
        data = FAKE_LIBRARY[str(Path(path).resolve())]
        self.metadata = SimpleNamespace(**data["metadata"])
        self.pages = [FakePage(text) for text in data["pages"]]


FAKE_LIBRARY: dict[str, dict] = {}


def _register_fake_pdf(
    path: Path,
    *,
    title: str,
    authors: str,
    subject: str,
    keywords: str,
    creation_date: str,
    pages: list[str],
    doi: str | None = None,
) -> None:
    FAKE_LIBRARY[str(path.resolve())] = {
        "metadata": {
            "title": title,
            "author": authors,
            "subject": subject,
            "keywords": keywords,
            "creation_date": creation_date,
            **({"doi": doi} if doi else {}),
        },
        "pages": pages,
    }


@pytest.fixture(autouse=True)
def fake_pdf_reader(monkeypatch):
    monkeypatch.setattr(parser, "PdfReader", FakeReader)
    FAKE_LIBRARY.clear()


def test_parse_pdf_extracts_metadata(tmp_path):
    pdf = tmp_path / "attention.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake\n")
    _register_fake_pdf(
        pdf,
        title="Attention Is All You Need",
        authors="Ashish Vaswani; Noam Shazeer",
        subject="NeurIPS",
        keywords="transformers, attention",
        creation_date="D:20170601000000",
        pages=[
            "Attention Is All You Need\nAbstract\nWe propose transformer models.\nIntroduction\n",
            "More text on the second page.",
        ],
    )

    paper = parser.parse_pdf(str(pdf))

    assert paper.title == "Attention Is All You Need"
    assert paper.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert paper.year == 2017
    assert paper.venue == "NeurIPS"
    assert paper.keywords == ["transformers", "attention"]
    assert "transformer models" in (paper.abstract or "")
    assert len(paper.references) == 0
    assert paper.page_count == 2


def test_index_directory_links_lists_and_queries(tmp_path):
    library = tmp_path / "library"
    library.mkdir()

    attention = library / "attention.pdf"
    diffusion = library / "diffusion.pdf"
    orphan = library / "orphan.pdf"
    for path in (attention, diffusion, orphan):
        path.write_bytes(b"%PDF-1.4\n%fake\n")

    _register_fake_pdf(
        attention,
        title="Attention Is All You Need",
        authors="Ashish Vaswani; Noam Shazeer",
        subject="NeurIPS",
        keywords="transformers, attention",
        creation_date="D:20170601000000",
        pages=["Attention Is All You Need\nAbstract\nWe propose transformer models."],
    )
    _register_fake_pdf(
        diffusion,
        title="Diffusion Models for Image Generation",
        authors="Jonathan Ho",
        subject="NeurIPS",
        keywords="diffusion, generative models",
        creation_date="D:20200101000000",
        doi="10.1234/diffusion.2020",
        pages=["Diffusion Models for Image Generation\nAbstract\nWe study diffusion models."],
    )
    _register_fake_pdf(
        orphan,
        title="Swin Transformers for Vision",
        authors="Ze Liu",
        subject="ICCV",
        keywords="vision, transformers",
        creation_date="D:20210101000000",
        pages=["Swin Transformers for Vision\nAbstract\nWe adapt transformers to vision."],
    )
    cited = library / "survey.pdf"
    cited.write_bytes(b"%PDF-1.4\n%fake\n")
    _register_fake_pdf(
        cited,
        title="A Survey of Generative Models",
        authors="Ada Lovelace",
        subject="ACM Computing Surveys",
        keywords="survey, generative models",
        creation_date="D:20230101000000",
        pages=[
            "A Survey of Generative Models\nAbstract\nWe survey recent work.\n",
            "\n".join(
                [
                    "References",
                    "[1] Ho, J. et al. Diffusion Models for Image Generation. doi:10.1234/diffusion.2020",
                    "[2] Vaswani, A. et al. Attention Is All You Need.",
                ]
            ),
        ],
    )

    reading_list = library / "week1.md"
    reading_list.write_text(
        "\n".join(
            [
                "# Week 1",
                "",
                "- [x] [Attention Is All You Need](attention.pdf) - transformer paper",
                "- [ ] Diffusion Models for Image Generation",
            ]
        ),
        encoding="utf-8",
    )

    store = LitStore(tmp_path / "store.ttl")
    stats = index_directory(str(library), store)

    assert stats.papers == 4
    assert stats.reading_lists == 1
    assert stats.entries == 2

    papers = list_papers(store)
    assert [paper["title"] for paper in papers] == [
        "A Survey of Generative Models",
        "Attention Is All You Need",
        "Diffusion Models for Image Generation",
        "Swin Transformers for Vision",
    ]

    attention_rows = papers_by_author(store, "Noam")
    assert len(attention_rows) == 1
    assert attention_rows[0]["title"] == "Attention Is All You Need"

    lists = list_reading_lists(store)
    assert len(lists) == 1
    assert lists[0]["name"] == "Week 1"
    assert lists[0]["entry_count"] == 2

    list_rows = papers_in_list(store, "Week 1")
    assert len(list_rows) == 2
    assert any(row.get("paper") for row in list_rows)

    refs = paper_references(store, "A Survey of Generative Models")
    assert len(refs) == 2
    assert any("Diffusion Models for Image Generation" in row.get("citationText", "") for row in refs)

    citing = papers_citing(store, "Diffusion Models for Image Generation")
    assert len(citing) == 1
    assert citing[0]["sourceTitle"] == "A Survey of Generative Models"

    cited = papers_cited_by(store, "A Survey of Generative Models")
    assert {row["targetTitle"] for row in cited} == {
        "Attention Is All You Need",
        "Diffusion Models for Image Generation",
    }

    orphans = papers_without_lists(store)
    assert len(orphans) == 2
    assert {row["title"] for row in orphans} == {
        "Swin Transformers for Vision",
        "A Survey of Generative Models",
    }

    diffusion_rows = search(store, "diffusion")
    assert len(diffusion_rows) >= 1
    assert diffusion_rows[0]["title"] == "Diffusion Models for Image Generation"

    mermaid = citation_graph(store, root_paper="A Survey of Generative Models", depth=2, fmt="mermaid")
    assert "flowchart LR" in mermaid
    assert "A Survey of Generative Models" in mermaid
    assert "Attention Is All You Need" in mermaid
    assert "Diffusion Models for Image Generation" in mermaid

    dot = citation_graph(store, root_paper="A Survey of Generative Models", depth=2, fmt="dot")
    assert "digraph citation_graph" in dot
    assert "A Survey of Generative Models" in dot

    bib_mermaid = bibliography_graph(store, fmt="mermaid")
    assert "flowchart LR" in bib_mermaid
    assert "Attention Is All You Need" in bib_mermaid
    assert "Diffusion Models for Image Generation" in bib_mermaid

    bib_dot = bibliography_graph(store, fmt="dot")
    assert "digraph bibliography_graph" in bib_dot
    assert "Attention Is All You Need" in bib_dot


def test_bibliography_parsing_and_apa_reference_titles(tmp_path):
    library = tmp_path / "library"
    library.mkdir()

    attention = library / "attention.pdf"
    diffusion = library / "diffusion.pdf"
    survey = library / "survey.pdf"
    for path in (attention, diffusion, survey):
        path.write_bytes(b"%PDF-1.4\n%fake\n")

    _register_fake_pdf(
        attention,
        title="Attention Is All You Need",
        authors="Ashish Vaswani; Noam Shazeer",
        subject="NeurIPS",
        keywords="transformers, attention",
        creation_date="D:20170601000000",
        doi="10.5555/attention.2017",
        pages=["Attention Is All You Need\nAbstract\nWe propose transformer models."],
    )
    _register_fake_pdf(
        diffusion,
        title="Diffusion Models for Image Generation",
        authors="Jonathan Ho",
        subject="NeurIPS",
        keywords="diffusion, generative models",
        creation_date="D:20200101000000",
        doi="10.1234/diffusion.2020",
        pages=["Diffusion Models for Image Generation\nAbstract\nWe study diffusion models."],
    )
    _register_fake_pdf(
        survey,
        title="A Survey of Generative Models",
        authors="Ada Lovelace",
        subject="ACM Computing Surveys",
        keywords="survey, generative models",
        creation_date="D:20230101000000",
        pages=[
            "A Survey of Generative Models\nAbstract\nWe survey recent work.\n",
            "\n".join(
                [
                    "References",
                    "Vaswani, A., Shazeer, N., Parmar, N., et al. (2017). Attention Is All You Need. Advances in Neural Information Processing Systems.",
                    "Ho, J., Jain, A., & Abbeel, P. (2020). Diffusion Models for Image Generation. NeurIPS.",
                ]
            ),
        ],
    )

    bib = library / "refs.bib"
    bib.write_text(
        "\n".join(
            [
                "@article{vaswani2017attention,",
                "  title = {Attention Is All You Need},",
                "  author = {Vaswani, Ashish and Shazeer, Noam},",
                "  journal = {NeurIPS},",
                "  year = {2017},",
                "  doi = {10.5555/attention.2017},",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    csl = library / "refs.json"
    csl.write_text(
        "\n".join(
            [
                "[",
                "  {",
                '    "id": "ho2020diffusion",',
                '    "title": "Diffusion Models for Image Generation",',
                '    "author": [{"family": "Ho", "given": "Jonathan"}],',
                '    "container-title": "NeurIPS",',
                '    "issued": {"date-parts": [[2020]]},',
                '    "DOI": "10.1234/diffusion.2020"',
                "  }",
                "]",
            ]
        ),
        encoding="utf-8",
    )

    store = LitStore(tmp_path / "store.ttl")
    stats = index_directory(str(library), store)

    assert stats.papers == 3
    assert stats.bibliographies == 2
    assert stats.bibliography_entries == 2

    paper = parser.parse_pdf(str(survey))
    assert [ref.title for ref in paper.references] == [
        "Attention Is All You Need",
        "Diffusion Models for Image Generation",
    ]

    bibliographies = list_bibliographies(store)
    assert sorted(item["format"] for item in bibliographies) == sorted(["bibtex", "csl-json"])
    assert [item["entry_count"] for item in bibliographies] == [1, 1]

    cited = papers_cited_by(store, "A Survey of Generative Models")
    assert {row["targetTitle"] for row in cited} == {
        "Attention Is All You Need",
        "Diffusion Models for Image Generation",
    }


def test_annotated_bibliography_statuses(tmp_path):
    library = tmp_path / "library"
    library.mkdir()

    attention = library / "attention.pdf"
    diffusion = library / "diffusion.pdf"
    for path in (attention, diffusion):
        path.write_bytes(b"%PDF-1.4\n%fake\n")

    _register_fake_pdf(
        attention,
        title="Attention Is All You Need",
        authors="Ashish Vaswani; Noam Shazeer",
        subject="NeurIPS",
        keywords="transformers, attention",
        creation_date="D:20170601000000",
        doi="10.5555/attention.2017",
        pages=["Attention Is All You Need\nAbstract\nWe propose transformer models."],
    )
    _register_fake_pdf(
        diffusion,
        title="Diffusion Models for Image Generation",
        authors="Jonathan Ho",
        subject="NeurIPS",
        keywords="diffusion, generative models",
        creation_date="D:20200101000000",
        doi="10.1234/diffusion.2020",
        pages=["Diffusion Models for Image Generation\nAbstract\nWe study diffusion models."],
    )

    bib = library / "refs.bib"
    bib.write_text(
        "\n".join(
            [
                "@article{resolved,",
                "  title = {Diffusion Models for Image Generation},",
                "  author = {Ho, Jonathan},",
                "  year = {2020},",
                "  doi = {10.1234/diffusion.2020},",
                "}",
                "@article{duplicate_a,",
                "  title = {Attention Is All You Need},",
                "  author = {Vaswani, Ashish},",
                "  year = {2017},",
                "  doi = {10.5555/attention.2017},",
                "}",
                "@article{duplicate_b,",
                "  title = {Attention Is All You Need},",
                "  author = {Vaswani, Ashish},",
                "  year = {2017},",
                "  doi = {10.5555/attention.2017},",
                "}",
                "@article{partial,",
                "  title = {Some Unmatched Work},",
                "  author = {Doe, Jane},",
                "  year = {2024},",
                "}",
                "@misc{unresolved,",
                "  note = {Unstructured reference with no extractable metadata},",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    store = LitStore(tmp_path / "store.ttl")
    stats = index_directory(str(library), store)

    assert stats.bibliographies == 1
    assert stats.bibliography_entries == 5

    rows = annotated_bibliography(store, "refs")
    assert len(rows) == 5

    by_key = {row["entryKey"]: row for row in rows}
    assert by_key["resolved"]["status"] == "resolved"
    assert by_key["resolved"]["matchStatus"] == "resolved"
    assert by_key["duplicate_a"]["status"] == "duplicate"
    assert by_key["duplicate_b"]["status"] == "duplicate"
    assert by_key["duplicate_a"]["duplicateCount"] == 2
    assert by_key["partial"]["status"] == "partial"
    assert by_key["unresolved"]["status"] == "unresolved"


def test_annotated_bibliography_html_report(tmp_path):
    library = tmp_path / "library"
    library.mkdir()

    attention = library / "attention.pdf"
    diffusion = library / "diffusion.pdf"
    for path in (attention, diffusion):
        path.write_bytes(b"%PDF-1.4\n%fake\n")

    _register_fake_pdf(
        attention,
        title="Attention Is All You Need",
        authors="Ashish Vaswani; Noam Shazeer",
        subject="NeurIPS",
        keywords="transformers, attention",
        creation_date="D:20170601000000",
        doi="10.5555/attention.2017",
        pages=["Attention Is All You Need\nAbstract\nWe propose transformer models."],
    )
    _register_fake_pdf(
        diffusion,
        title="Diffusion Models for Image Generation",
        authors="Jonathan Ho",
        subject="NeurIPS",
        keywords="diffusion, generative models",
        creation_date="D:20200101000000",
        doi="10.1234/diffusion.2020",
        pages=["Diffusion Models for Image Generation\nAbstract\nWe study diffusion models."],
    )

    bib = library / "refs.bib"
    bib.write_text(
        "\n".join(
            [
                "@article{resolved,",
                "  title = {Diffusion Models for Image Generation},",
                "  author = {Ho, Jonathan},",
                "  year = {2020},",
                "  doi = {10.1234/diffusion.2020},",
                "}",
                "@article{duplicate_a,",
                "  title = {Attention Is All You Need},",
                "  author = {Vaswani, Ashish},",
                "  year = {2017},",
                "  doi = {10.5555/attention.2017},",
                "}",
                "@article{duplicate_b,",
                "  title = {Attention Is All You Need},",
                "  author = {Vaswani, Ashish},",
                "  year = {2017},",
                "  doi = {10.5555/attention.2017},",
                "}",
                "@article{partial,",
                "  title = {Some Unmatched Work},",
                "  author = {Doe, Jane},",
                "  year = {2024},",
                "}",
                "@misc{unresolved,",
                "  note = {Unstructured reference with no extractable metadata},",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    store = LitStore(tmp_path / "store.ttl")
    index_directory(str(library), store)

    html = annotated_bibliography_html(store, "refs")
    lower = html.lower()
    assert "<html" in lower
    assert "annotated bibliography report" in lower
    assert "attention is all you need" in lower
    assert "diffusion models for image generation" in lower
    assert "status-duplicate" in lower
    assert "status-unresolved" in lower

    filtered = annotated_bibliography_html(
        store,
        "refs",
        statuses=["resolved"],
        sort_by="duplicate-count",
        descending=True,
    )
    filtered_lower = filtered.lower()
    assert filtered_lower.count('<tr class="status-') == 1
    assert "diffusion models for image generation" in filtered_lower
    assert "attention is all you need" not in filtered_lower

    sorted_html = annotated_bibliography_html(
        store,
        "refs",
        sort_by="duplicate-count",
        descending=True,
    )
    sorted_lower = sorted_html.lower()
    assert sorted_lower.find("attention is all you need") < sorted_lower.find("diffusion models for image generation")


def test_annotated_bibliography_pdf_report(tmp_path):
    library = tmp_path / "library"
    library.mkdir()

    attention = library / "attention.pdf"
    diffusion = library / "diffusion.pdf"
    for path in (attention, diffusion):
        path.write_bytes(b"%PDF-1.4\n%fake\n")

    _register_fake_pdf(
        attention,
        title="Attention Is All You Need",
        authors="Ashish Vaswani; Noam Shazeer",
        subject="NeurIPS",
        keywords="transformers, attention",
        creation_date="D:20170601000000",
        doi="10.5555/attention.2017",
        pages=["Attention Is All You Need\nAbstract\nWe propose transformer models."],
    )
    _register_fake_pdf(
        diffusion,
        title="Diffusion Models for Image Generation",
        authors="Jonathan Ho",
        subject="NeurIPS",
        keywords="diffusion, generative models",
        creation_date="D:20200101000000",
        doi="10.1234/diffusion.2020",
        pages=["Diffusion Models for Image Generation\nAbstract\nWe study diffusion models."],
    )

    bib = library / "refs.bib"
    bib.write_text(
        "\n".join(
            [
                "@article{resolved,",
                "  title = {Diffusion Models for Image Generation},",
                "  author = {Ho, Jonathan},",
                "  year = {2020},",
                "  doi = {10.1234/diffusion.2020},",
                "}",
                "@article{duplicate_a,",
                "  title = {Attention Is All You Need},",
                "  author = {Vaswani, Ashish},",
                "  year = {2017},",
                "  doi = {10.5555/attention.2017},",
                "}",
                "@article{duplicate_b,",
                "  title = {Attention Is All You Need},",
                "  author = {Vaswani, Ashish},",
                "  year = {2017},",
                "  doi = {10.5555/attention.2017},",
                "}",
                "@article{partial,",
                "  title = {Some Unmatched Work},",
                "  author = {Doe, Jane},",
                "  year = {2024},",
                "}",
                "@misc{unresolved,",
                "  note = {Unstructured reference with no extractable metadata},",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    store = LitStore(tmp_path / "store.ttl")
    index_directory(str(library), store)

    pdf_bytes = annotated_bibliography_pdf(
        store,
        "refs",
        statuses=["resolved", "duplicate"],
        sort_by="status",
        library_name="Test Library",
    )
    assert pdf_bytes.startswith(b"%PDF")

    output = tmp_path / "annotated-bibliography.pdf"
    output.write_bytes(pdf_bytes)

    from pypdf import PdfReader

    reader = PdfReader(str(output))
    assert len(reader.pages) >= 1
    text = "\n".join(page.extract_text() or "" for page in reader.pages).lower()
    assert "annotated bibliography report" in text
    assert "test library" in text
    assert "generated:" in text
    assert "attention is all you need" in text
    assert "diffusion models for image generation" in text


def test_annotated_bibliography_combined_export(tmp_path):
    library = tmp_path / "library"
    library.mkdir()

    attention = library / "attention.pdf"
    diffusion = library / "diffusion.pdf"
    for path in (attention, diffusion):
        path.write_bytes(b"%PDF-1.4\n%fake\n")

    _register_fake_pdf(
        attention,
        title="Attention Is All You Need",
        authors="Ashish Vaswani; Noam Shazeer",
        subject="NeurIPS",
        keywords="transformers, attention",
        creation_date="D:20170601000000",
        doi="10.5555/attention.2017",
        pages=["Attention Is All You Need\nAbstract\nWe propose transformer models."],
    )
    _register_fake_pdf(
        diffusion,
        title="Diffusion Models for Image Generation",
        authors="Jonathan Ho",
        subject="NeurIPS",
        keywords="diffusion, generative models",
        creation_date="D:20200101000000",
        doi="10.1234/diffusion.2020",
        pages=["Diffusion Models for Image Generation\nAbstract\nWe study diffusion models."],
    )

    bib = library / "refs.bib"
    bib.write_text(
        "\n".join(
            [
                "@article{resolved,",
                "  title = {Diffusion Models for Image Generation},",
                "  author = {Ho, Jonathan},",
                "  year = {2020},",
                "  doi = {10.1234/diffusion.2020},",
                "}",
                "@article{duplicate_a,",
                "  title = {Attention Is All You Need},",
                "  author = {Vaswani, Ashish},",
                "  year = {2017},",
                "  doi = {10.5555/attention.2017},",
                "}",
                "@article{duplicate_b,",
                "  title = {Attention Is All You Need},",
                "  author = {Vaswani, Ashish},",
                "  year = {2017},",
                "  doi = {10.5555/attention.2017},",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    store = LitStore(tmp_path / "store.ttl")
    index_directory(str(library), store)

    output_dir = tmp_path / "reports"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "annotated-bibliography-export",
            "refs",
            "--status",
            "resolved",
            "--status",
            "duplicate",
            "--sort-by",
            "status",
            "--output-dir",
            str(output_dir),
            "--library-name",
            "Test Library",
            "--store",
            str(tmp_path / "store.ttl"),
        ],
    )

    assert result.exit_code == 0, result.output
    html_path = output_dir / "annotated-bibliography.html"
    pdf_path = output_dir / "annotated-bibliography.pdf"
    assert html_path.exists()
    assert pdf_path.exists()

    assert "Wrote HTML report" in result.output
    assert "Wrote PDF report" in result.output
    assert "annotated bibliography report" in html_path.read_text(encoding="utf-8").lower()
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_graph_export_bundle(tmp_path):
    library = tmp_path / "library"
    library.mkdir()

    attention = library / "attention.pdf"
    diffusion = library / "diffusion.pdf"
    survey = library / "survey.pdf"
    for path in (attention, diffusion, survey):
        path.write_bytes(b"%PDF-1.4\n%fake\n")

    _register_fake_pdf(
        attention,
        title="Attention Is All You Need",
        authors="Ashish Vaswani; Noam Shazeer",
        subject="NeurIPS",
        keywords="transformers, attention",
        creation_date="D:20170601000000",
        doi="10.5555/attention.2017",
        pages=["Attention Is All You Need\nAbstract\nWe propose transformer models."],
    )
    _register_fake_pdf(
        diffusion,
        title="Diffusion Models for Image Generation",
        authors="Jonathan Ho",
        subject="NeurIPS",
        keywords="diffusion, generative models",
        creation_date="D:20200101000000",
        doi="10.1234/diffusion.2020",
        pages=["Diffusion Models for Image Generation\nAbstract\nWe study diffusion models."],
    )
    _register_fake_pdf(
        survey,
        title="A Survey of Generative Models",
        authors="Ada Lovelace",
        subject="ACM Computing Surveys",
        keywords="survey, generative models",
        creation_date="D:20230101000000",
        pages=[
            "A Survey of Generative Models\nAbstract\nWe survey recent work.\n",
            "\n".join(
                [
                    "References",
                    "[1] Ho, J. et al. Diffusion Models for Image Generation. doi:10.1234/diffusion.2020",
                    "[2] Vaswani, A. et al. Attention Is All You Need.",
                ]
            ),
        ],
    )

    bib = library / "refs.bib"
    bib.write_text(
        "\n".join(
            [
                "@article{resolved,",
                "  title = {Diffusion Models for Image Generation},",
                "  author = {Ho, Jonathan},",
                "  year = {2020},",
                "  doi = {10.1234/diffusion.2020},",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    store = LitStore(tmp_path / "store.ttl")
    index_directory(str(library), store)

    output_dir = tmp_path / "graphs"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "graph-export",
            "--citation-root",
            "A Survey of Generative Models",
            "--bibliography-root",
            "refs",
            "--fmt",
            "mermaid",
            "--fmt",
            "dot",
            "--output-dir",
            str(output_dir),
            "--prefix",
            "library",
            "--store",
            str(tmp_path / "store.ttl"),
        ],
    )

    assert result.exit_code == 0, result.output
    citation_mermaid = output_dir / "library-citation.mmd"
    citation_dot = output_dir / "library-citation.dot"
    bibliography_mermaid = output_dir / "library-bibliography.mmd"
    bibliography_dot = output_dir / "library-bibliography.dot"
    for path in (citation_mermaid, citation_dot, bibliography_mermaid, bibliography_dot):
        assert path.exists()

    assert "A Survey of Generative Models" in citation_mermaid.read_text(encoding="utf-8")
    assert "digraph citation_graph" in citation_dot.read_text(encoding="utf-8")
    assert "Diffusion Models for Image Generation" in bibliography_mermaid.read_text(encoding="utf-8")
    assert "digraph bibliography_graph" in bibliography_dot.read_text(encoding="utf-8")


def test_top_level_export_bundle(tmp_path):
    library = tmp_path / "library"
    library.mkdir()

    attention = library / "attention.pdf"
    diffusion = library / "diffusion.pdf"
    survey = library / "survey.pdf"
    for path in (attention, diffusion, survey):
        path.write_bytes(b"%PDF-1.4\n%fake\n")

    _register_fake_pdf(
        attention,
        title="Attention Is All You Need",
        authors="Ashish Vaswani; Noam Shazeer",
        subject="NeurIPS",
        keywords="transformers, attention",
        creation_date="D:20170601000000",
        doi="10.5555/attention.2017",
        pages=["Attention Is All You Need\nAbstract\nWe propose transformer models."],
    )
    _register_fake_pdf(
        diffusion,
        title="Diffusion Models for Image Generation",
        authors="Jonathan Ho",
        subject="NeurIPS",
        keywords="diffusion, generative models",
        creation_date="D:20200101000000",
        doi="10.1234/diffusion.2020",
        pages=["Diffusion Models for Image Generation\nAbstract\nWe study diffusion models."],
    )
    _register_fake_pdf(
        survey,
        title="A Survey of Generative Models",
        authors="Ada Lovelace",
        subject="ACM Computing Surveys",
        keywords="survey, generative models",
        creation_date="D:20230101000000",
        pages=[
            "A Survey of Generative Models\nAbstract\nWe survey recent work.\n",
            "\n".join(
                [
                    "References",
                    "[1] Ho, J. et al. Diffusion Models for Image Generation. doi:10.1234/diffusion.2020",
                    "[2] Vaswani, A. et al. Attention Is All You Need.",
                ]
            ),
        ],
    )

    bib = library / "refs.bib"
    bib.write_text(
        "\n".join(
            [
                "@article{resolved,",
                "  title = {Diffusion Models for Image Generation},",
                "  author = {Ho, Jonathan},",
                "  year = {2020},",
                "  doi = {10.1234/diffusion.2020},",
                "}",
                "@article{duplicate_a,",
                "  title = {Attention Is All You Need},",
                "  author = {Vaswani, Ashish},",
                "  year = {2017},",
                "  doi = {10.5555/attention.2017},",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    store = LitStore(tmp_path / "store.ttl")
    index_directory(str(library), store)

    output_dir = tmp_path / "bundle"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "export",
            "--output-dir",
            str(output_dir),
            "--citation-root",
            "A Survey of Generative Models",
            "--bibliography-root",
            "refs",
            "--library-name",
            "Test Library",
            "--store",
            str(tmp_path / "store.ttl"),
        ],
    )

    assert result.exit_code == 0, result.output

    graph_citation = output_dir / "graphs" / "graph-citation.mmd"
    graph_bibliography = output_dir / "graphs" / "graph-bibliography.mmd"
    report_html = output_dir / "reports" / "annotated-bibliography.html"
    report_pdf = output_dir / "reports" / "annotated-bibliography.pdf"
    manifest = output_dir / "manifest.json"

    for path in (graph_citation, graph_bibliography, report_html, report_pdf, manifest):
        assert path.exists()

    assert "A Survey of Generative Models" in graph_citation.read_text(encoding="utf-8")
    assert "annotated bibliography report" in report_html.read_text(encoding="utf-8").lower()
    assert report_pdf.read_bytes().startswith(b"%PDF")

    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_data["output_dir"].endswith("bundle")
    assert manifest_data["summary"]["papers"] == 3
    assert manifest_data["summary"]["bibliographies"] == 1
    assert manifest_data["summary"]["bibliography_entries"] == 2
    assert manifest_data["summary"]["citation_edges"] == 2
    assert manifest_data["graphs"]["citation:mermaid"].endswith("graph-citation.mmd")
    assert manifest_data["reports"]["html"].endswith("annotated-bibliography.html")
