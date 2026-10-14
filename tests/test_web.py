from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from litkg.parser import PaperInfo  # noqa: E402
from litkg.store import LitStore  # noqa: E402
from litkg.triples import paper_to_triples  # noqa: E402
from litkg.web import create_app  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "paper"


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    target = tmp_path / "paper"
    shutil.copytree(FIXTURE, target)
    monkeypatch.chdir(tmp_path)
    store_path = tmp_path / "store.ttl"
    store = LitStore(str(store_path))
    store.load_triples(
        paper_to_triples(
            PaperInfo(
                source_path=str(tmp_path / "attention.pdf"),
                title="Attention Is All You Need <script>",
                authors=["Ashish Vaswani"],
                year=2017,
                abstract="Transformers rely on attention.",
                keywords=["transformers"],
            )
        )
    )
    store.save()
    return TestClient(create_app(str(store_path), paper=str(target / "main.tex"))), store_path


def test_pages_render_and_escape(setup) -> None:
    client, _ = setup
    for url in ["/", "/papers", "/bibliographies", "/reading-lists", "/search", "/query", "/review"]:
        response = client.get(url)
        assert response.status_code == 200, url
    papers = client.get("/papers").text
    assert "Attention Is All You Need &lt;script&gt;" in papers
    assert "<script>" not in papers
    assert "Ashish Vaswani" in papers


def test_search_and_paper_detail(setup) -> None:
    client, _ = setup
    found = client.get("/search", params={"q": "attention"}).text
    assert "Ashish Vaswani" in found and "{" not in found.split("<tbody>")[1]
    detail = client.get("/paper", params={"title": "Attention Is All You Need <script>"}).text
    assert "Transformers rely on attention." in detail
    assert client.get("/paper", params={"title": "missing"}).text.count("Paper not found") == 1


def test_review_page_shows_check_results(setup) -> None:
    client, _ = setup
    review = client.get("/review").text
    assert "undefined2024" in review
    assert "Failed" in review
    assert "Verify online" in review


def test_store_reloads_after_reindex(setup) -> None:
    client, store_path = setup
    assert "Attention" in client.get("/papers").text
    store = LitStore(str(store_path))
    store.clear()
    store.save()
    assert "No papers yet" in client.get("/papers").text


def test_sparql_errors_are_shown(setup) -> None:
    client, _ = setup
    response = client.get("/query", params={"q": "SELECT nonsense"})
    assert response.status_code == 200
    assert "role='alert'" in response.text
