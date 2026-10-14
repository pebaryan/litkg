from litkg.papercite import parse_cite_keys, gate_result


def test_parse_cite_keys() -> None:
    text = "See \\cite{Foo2020,Bar2021} and \\citet{Baz2022}."
    assert parse_cite_keys(text) == ["Foo2020", "Bar2021", "Baz2022"]


def test_gate_result_unresolved() -> None:
    result = {"cite_keys": ["A"], "counts": {"unresolved": 1}, "unresolved": ["A"], "duplicates": [], "results": [{"cite_key": "A", "status": "unresolved"}]}
    ok, message = gate_result(result)
    assert not ok
    assert "unresolved" in message
