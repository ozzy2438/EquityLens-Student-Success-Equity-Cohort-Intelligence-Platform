from pathlib import Path

from equitylens_ingestion.cli import main


def test_list_command_outputs_matching_source(capsys) -> None:
    exit_code = main(["list", "--section", "15", "--year", "2024"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "doe_s15_2024" in output
    assert "doe_s11_2024" not in output


def test_ingest_with_no_match_returns_usage_error(capsys, tmp_path: Path) -> None:
    exit_code = main(["--data-root", str(tmp_path / "data"), "ingest", "--year", "1900"])
    assert exit_code == 2
    assert "No sources matched" in capsys.readouterr().err


def test_missing_registry_returns_configuration_error(capsys, tmp_path: Path) -> None:
    exit_code = main(["--config", str(tmp_path / "missing.yml"), "list"])
    assert exit_code == 2
    assert "Cannot read source registry" in capsys.readouterr().err
