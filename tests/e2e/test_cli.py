"""End-to-end CLI runs through `cli.main`.

`main` is called in-process (not as a subprocess) so failures show a real
traceback and coverage still counts the CLI code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import cli


def test_an_offline_run_prints_a_summary_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["-q", "N-halamine rechargeable coating", "--offline", "--quiet"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "Mode: offline" in out
    assert "Question: N-halamine rechargeable coating" in out
    assert "Sources used: OfflineMock" in out
    assert "Top selected papers:" in out


def test_the_json_flag_writes_the_canonical_contract_payload(tmp_path: Path) -> None:
    json_path = tmp_path / "out.json"

    cli.main(["-q", "coating", "--offline", "--quiet", "--json", str(json_path)])
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["contract_version"] == "v1"
    assert payload["mode"] == "offline"
    assert payload["counts"]["found"] == len(payload["papers"])
    assert payload["request_id"].startswith("req_")


def test_the_profile_flag_overrides_the_config_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"profile": "generic"}), encoding="utf-8")

    cli.main(["-q", "coating", "--offline", "--quiet", "--config", str(config), "--profile", "n-halamine"])

    assert "Profile: n-halamine" in capsys.readouterr().out


def test_an_empty_question_falls_back_to_the_profile_default(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["--offline", "--quiet", "--profile", "n-halamine"])
    out = capsys.readouterr().out

    assert "Question: " in out
    assert "Question: \n" not in out


def test_the_progress_bar_goes_to_stderr_so_stdout_stays_parseable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.main(["-q", "coating", "--offline"])
    captured = capsys.readouterr()

    assert "ETA" in captured.err
    assert "ETA" not in captured.out


def test_quiet_suppresses_the_progress_bar(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["-q", "coating", "--offline", "--quiet"])

    assert capsys.readouterr().err == ""


def test_non_fatal_warnings_are_summarised_rather_than_dumped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.e2e.conftest import FakeSearchService
    from tests.factories import make_response

    class WarningService(FakeSearchService):
        def run(self, request, progress=None):
            return make_response(errors=[{"stage": "openalex", "message": "timeout"}])

    monkeypatch.setattr(cli, "SearchService", WarningService)

    cli.main(["-q", "q", "--offline", "--quiet"])

    assert "1 warning(s) recorded (non-fatal)." in capsys.readouterr().out


def test_an_unknown_flag_exits_with_the_argparse_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--not-a-flag"])

    assert exit_info.value.code == 2


def test_the_cli_emits_the_same_payload_the_service_produced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canonical_payload: dict, capsys
) -> None:
    from tests.e2e.conftest import FakeSearchService

    monkeypatch.setattr(cli, "SearchService", FakeSearchService)
    json_path = tmp_path / "out.json"

    exit_code = cli.main(["-q", "q", "--offline", "--quiet", "--json", str(json_path)])

    assert exit_code == 0
    assert json.loads(json_path.read_text(encoding="utf-8")) == canonical_payload
