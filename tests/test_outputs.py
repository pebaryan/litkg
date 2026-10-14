from __future__ import annotations

import json
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from click.testing import CliRunner
from helpers import FakeFetcher

from litkg.check import CheckOptions, check_paper
from litkg.cli import cli
from litkg.fix import EntryFix, apply_to_text, plan_fixes, preview
from litkg.formats import render, render_github, render_text
from litkg.mcp_server import Workspace, WorkspaceError
from litkg.verify import Record, Verifier

FIXTURE = Path(__file__).parent / "fixtures" / "paper"


@pytest.fixture()
def paper(tmp_path, monkeypatch) -> Path:
    target = tmp_path / "paper"
    shutil.copytree(FIXTURE, target)
    monkeypatch.chdir(tmp_path)
    return target / "main.tex"


@pytest.fixture()
def online_report(paper):
    return check_paper(paper, CheckOptions(online=True, workers=1), verifier=Verifier(FakeFetcher()))


@pytest.fixture()
def fake_network(monkeypatch):
    """Make every HttpClient created by the CLI or MCP server use the fake registries."""
    fetcher = FakeFetcher()

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, url, accept="application/json"):
            return fetcher.get(url, accept)

        def save(self):
            pass

    monkeypatch.setattr("litkg.verify.HttpClient", Client)
    return fetcher


# --------------------------------------------------------------------------- formats


def test_text_report_ascii_and_unicode(online_report) -> None:
    ascii_text = render_text(online_report, color=False, unicode=False)
    assert "FAILED" in ascii_text and "x devlin2019bert" in ascii_text
    assert "suggest" in ascii_text
    assert all(ord(char) < 128 for char in ascii_text)
    assert "✗" in render_text(online_report, color=False, unicode=True)


def test_sarif_report(online_report) -> None:
    sarif = json.loads(render(online_report, "sarif"))
    run = sarif["runs"][0]
    assert sarif["version"] == "2.1.0"
    rule_ids = {rule["id"] for rule in run["tool"]["driver"]["rules"]}
    assert {"undefined", "doi-not-found", "author-mismatch"} <= rule_ids
    undefined = next(result for result in run["results"] if result["ruleId"] == "undefined")
    location = undefined["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "paper/sections/intro.tex"
    assert location["region"] == {"startLine": 3, "startColumn": 16}


def test_junit_report(online_report) -> None:
    suite = ET.fromstring(render(online_report, "junit"))
    assert suite.get("tests") == "7"
    assert suite.get("failures") == "3"
    failed = {case.get("name") for case in suite.iter("testcase") if case.find("failure") is not None}
    assert failed == {"cite:undefined2024", "cite:devlin2019bert", "cite:smith2023quantum"}


def test_github_annotations_escape_properties(online_report) -> None:
    lines = render_github(online_report).splitlines()
    error = next(line for line in lines if "undefined2024" in line)
    assert error.startswith("::error file=paper/sections/intro.tex,line=3,col=16,title=litkg undefined undefined2024::")
    assert lines[-1].startswith("litkg: failed")


def test_markdown_summary(online_report) -> None:
    markdown = render(online_report, "markdown")
    assert markdown.startswith("### ❌ litkg citation check")
    assert "| ❌ | `smith2023quantum` |" in markdown
    assert "Suggested corrections" in markdown


# --------------------------------------------------------------------------- fixes


BIB = """@article{k,
  title   = {Wrong Title},
  author  = {Nobody, A.},
  journal = nips,
  year    = {2001},
  doi     = {10.9999/fake}
}
"""


def test_apply_to_text_edits_only_changed_fields() -> None:
    fix = EntryFix("k", "refs.bib", {"title": "Right Title", "doi": None, "eprint": "1706.03762"}, "", Record("arxiv"))
    updated = apply_to_text(BIB, fix)
    assert "title   = {Right Title}," in updated
    assert "journal = nips," in updated  # untouched macro reference survives
    assert "doi" not in updated
    assert updated.rstrip().endswith("eprint = {1706.03762}\n}")


def test_apply_to_text_preserves_crlf() -> None:
    fix = EntryFix("k", "refs.bib", {"year": "2017", "doi": "10.1/x"}, "", Record("x"))
    updated = apply_to_text(BIB.replace("\n", "\r\n"), fix)
    assert "\r\n" in updated and "\n" not in updated.replace("\r\n", "")
    assert "year    = {2017}" in updated


def test_plan_fixes_corrects_authors_and_pins_doi(online_report) -> None:
    plan = plan_fixes(online_report)
    fixes = {fix.key: fix for fix in plan.fixes}
    assert set(fixes) == {"devlin2019bert"}
    assert fixes["devlin2019bert"].changes == {
        "author": "Devlin, Jacob and Chang, Ming-Wei and Lee, Kenton and Toutanova, Kristina",
        "doi": "10.18653/v1/n19-1423",
    }
    assert any("smith2023quantum" in message for message in plan.skipped)
    diff, contents = preview(plan)
    assert "+  author    = {Devlin, Jacob" in diff
    assert len(contents) == 1


# --------------------------------------------------------------------------- CLI


def test_cli_check_exit_codes_and_side_reports(paper, tmp_path) -> None:
    runner = CliRunner()
    failed = runner.invoke(cli, ["check", str(paper), "--sarif", "out/report.sarif", "--junit", "out/report.xml"])
    assert failed.exit_code == 1, failed.output
    assert "undefined2024" in failed.output
    assert json.loads((tmp_path / "out" / "report.sarif").read_text(encoding="utf-8"))["version"] == "2.1.0"
    assert (tmp_path / "out" / "report.xml").exists()

    passed = runner.invoke(cli, ["check", str(paper), "--ignore", "undefined2024", "--format", "json"])
    assert passed.exit_code == 0, passed.output
    assert json.loads(passed.output)["passed"] is True


def test_cli_check_online_uses_registries(paper, fake_network) -> None:
    result = CliRunner().invoke(cli, ["check", str(paper), "--online", "--format", "github"])
    assert result.exit_code == 1
    assert "doi-not-found" in result.output
    assert any("doi.org" in url for url in fake_network.requests)


def test_cli_fix_dry_run_then_write(paper, fake_network) -> None:
    runner = CliRunner()
    bib = paper.parent / "refs.bib"
    before = bib.read_text(encoding="utf-8")
    dry = runner.invoke(cli, ["fix", str(paper)])
    assert dry.exit_code == 0, dry.output
    assert "Dry run" in dry.output
    assert bib.read_text(encoding="utf-8") == before

    applied = runner.invoke(cli, ["fix", str(paper), "--write"])
    assert applied.exit_code == 0, applied.output
    assert "Devlin, Jacob" in bib.read_text(encoding="utf-8")

    recheck = runner.invoke(cli, ["check", str(paper), "--online", "--ignore", "undefined2024", "--ignore", "smith2023quantum"])
    assert recheck.exit_code == 0, recheck.output


def test_cli_version_and_help() -> None:
    runner = CliRunner()
    assert "litkg" in runner.invoke(cli, ["--version"]).output
    assert "litkg check paper.tex" in runner.invoke(cli, ["--help"]).output


# --------------------------------------------------------------------------- MCP workspace


def test_workspace_rejects_paths_outside_root(paper, tmp_path) -> None:
    workspace = Workspace(root=paper.parent)
    with pytest.raises(WorkspaceError):
        workspace.read(str(tmp_path / "elsewhere.pdf"))
    with pytest.raises(WorkspaceError):
        workspace.check_paper("../../etc/passwd")
    with pytest.raises(WorkspaceError):
        Workspace(root=paper.parent, store_path="../outside.ttl")


def test_workspace_check_and_online_gate(paper, fake_network) -> None:
    offline = Workspace(root=paper.parent)
    report = json.loads(offline.check_paper("main.tex"))
    assert report["online"] is False
    assert report["summary"]["citations"] == 7
    with pytest.raises(WorkspaceError):
        offline.suggest_reference("Deep Residual Learning")

    online = Workspace(root=paper.parent, online=True)
    assert json.loads(online.check_paper("main.tex"))["online"] is True
    candidates = json.loads(online.suggest_reference("Deep Residual Learning"))
    assert candidates[0]["doi"] == "10.1109/cvpr.2016.90"
    result = json.loads(online.fix_references("main.tex"))
    assert result["written"] == [] and "Devlin" in result["diff"]


def test_workspace_index_and_query(paper) -> None:
    workspace = Workspace(root=paper.parent)
    stats = json.loads(workspace.index_library("."))
    assert stats["bibliographies"] == 1
    assert json.loads(workspace.bibliographies())[0]["entry_count"] == 6
