import pytest

from litkg.indexer import index_directory
from litkg.papercite import gate_result, parse_cite_keys, sync
from litkg.store import LitStore


def test_parse_cite_keys() -> None:
    text = "See \\cite{Foo2020,Bar2021} and \\citet{Baz2022}."
    assert parse_cite_keys(text) == ["Foo2020", "Bar2021", "Baz2022"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (r"\citep[p.~3]{key1}", ["key1"]),
        (r"\citep[see][ch.~2]{key1, key2}", ["key1", "key2"]),
        (r"\autocite{a} \parencite{b} \textcite{c} \footcite[12]{d}", ["a", "b", "c", "d"]),
        (r"\Citet*{a} \citeauthor{b} \citeyear{c}", ["a", "b", "c"]),
        (r"\cites[3]{a}[see][]{b,c}{d} \cite{e}", ["a", "b", "c", "d", "e"]),
        (r"\nocite{a} \nocite{*}", ["a"]),
        (r"\citestyle{authoryear} \cite{a}", ["a"]),
    ],
)
def test_parse_latex_cite_variants(text: str, expected: list[str]) -> None:
    assert parse_cite_keys(text) == expected


def test_parse_latex_skips_comments() -> None:
    text = "\n".join(
        [
            r"Real \cite{kept}. % \cite{commented}",
            r"% \citep{also_commented}",
            r"100\% sure \cite{after_escaped_percent}",
            r"\begin{comment}\cite{in_env}\end{comment}",
        ]
    )
    assert parse_cite_keys(text) == ["kept", "after_escaped_percent"]


def test_parse_pandoc_cite_keys() -> None:
    text = "\n".join(
        [
            "As shown [see @smith2020, p. 4; -@doe:2021] and @lee_2019.",
            "Mail me at someone@example.com; braces work [@{weird key}].",
            "`@not_inline` is code.",
            "```",
            "@not_fenced",
            "```",
        ]
    )
    assert parse_cite_keys(text, syntax="markdown") == ["smith2020", "doe:2021", "lee_2019", "weird key"]


def test_parse_cite_keys_rejects_unknown_syntax() -> None:
    with pytest.raises(ValueError):
        parse_cite_keys("", syntax="rst")


def test_gate_result_unresolved() -> None:
    result = {"cite_keys": ["A"], "counts": {"unresolved": 1}, "unresolved": ["A"], "duplicates": [], "results": [{"cite_key": "A", "status": "unresolved"}]}
    ok, message = gate_result(result)
    assert not ok
    assert "unresolved" in message


def test_gate_result_fails_when_no_citations_found() -> None:
    result = {"cite_keys": [], "unresolved": [], "duplicates": [], "results": []}
    ok, message = gate_result(result)
    assert not ok
    assert "no citations found" in message
    assert gate_result(result, allow_empty=True)[0]


BIB_A = """
@article{vaswani2017,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish and Shazeer, Noam},
  year = {2017},
  doi = {10.48550/arXiv.1706.03762}
}
@article{shared,
  title = {Deep Residual Learning for Image Recognition},
  author = {He, Kaiming},
  year = {2016}
}
"""

BIB_B = """
@article{shared,
  title = {Batch Normalization},
  author = {Ioffe, Sergey},
  year = {2015}
}
"""


def _store_with_bibs(tmp_path, *bibs: str) -> LitStore:
    library = tmp_path / "library"
    library.mkdir()
    for index, content in enumerate(bibs):
        (library / f"refs{index}.bib").write_text(content, encoding="utf-8")
    store = LitStore(str(tmp_path / "store.ttl"))
    index_directory(str(library), store)
    return store


def test_sync_resolves_natbib_citations_and_gates(tmp_path) -> None:
    store = _store_with_bibs(tmp_path, BIB_A)
    paper = tmp_path / "paper.tex"
    paper.write_text(r"Transformers \citep[p.~2]{vaswani2017}; missing \citet{ghost2024}.", encoding="utf-8")

    result = sync(store, paper)

    assert result["cite_keys"] == ["vaswani2017", "ghost2024"]
    assert result["unresolved"] == ["ghost2024"]
    ok, message = gate_result(result, allow_partial=True)
    assert not ok
    assert "ghost2024" in message


def test_sync_flags_cite_key_defined_differently_across_bibliographies(tmp_path) -> None:
    store = _store_with_bibs(tmp_path, BIB_A, BIB_B)
    paper = tmp_path / "paper.md"
    paper.write_text("ResNets [@shared].", encoding="utf-8")

    result = sync(store, paper)

    assert result["conflicts"] == ["shared"]
    ok, message = gate_result(result, allow_partial=True)
    assert not ok
    assert "defined differently" in message


def test_sync_accepts_identical_definitions_across_bibliographies(tmp_path) -> None:
    store = _store_with_bibs(tmp_path, BIB_A, BIB_A)
    paper = tmp_path / "paper.tex"
    paper.write_text(r"\cite{shared}", encoding="utf-8")

    result = sync(store, paper)

    assert result["conflicts"] == []
    assert gate_result(result, allow_partial=True)[0]
