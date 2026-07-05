from __future__ import annotations

import json
from pathlib import Path

import pytest

from equitylens_synthetic.cli import main


@pytest.fixture
def targets_path(tmp_path: Path) -> Path:
    def share(equity_group_id: str, share_pct: float) -> dict:
        return {
            "institution_id": "acu",
            "equity_group_id": equity_group_id,
            "count": 0.0,
            "all_students": 10000.0,
            "share_pct": share_pct,
            "tolerance_pp": 1.0,
            "imputed_target_flag": False,
            "imputation_source": None,
        }

    target_set = {
        "target_version": "v1",
        "reference_year": 2023,
        "targets": {
            "enrolment_share": [
                share("low_ses_sa1", 12.0),
                share("first_nations", 2.0),
                share("regional", 11.0),
                share("remote", 1.0),
                share("disability", 7.0),
                share("non_english_speaking_background", 3.0),
                share("women_non_traditional_area", 4.0),
            ],
            "seifa_decile_share": [
                {"decile": d, "population": 1000, "share_pct": 10.0, "tolerance_pp": 2.0}
                for d in range(1, 11)
            ],
        },
    }
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(target_set), encoding="utf-8")
    return path


def test_baseline_command_writes_population_and_comparison(
    targets_path: Path, tmp_path: Path, capsys
) -> None:
    output_dir = tmp_path / "out"
    exit_code = main(
        [
            "--targets",
            str(targets_path),
            "--n-students",
            "1000",
            "--output-dir",
            str(output_dir),
            "baseline",
        ]
    )
    assert exit_code == 0
    assert (output_dir / "baseline_population.csv").exists()
    assert (output_dir / "baseline_marginal_comparison.csv").exists()
    assert "Max abs deviation" in capsys.readouterr().out


def test_raked_command_reports_convergence(targets_path: Path, tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "out"
    exit_code = main(
        [
            "--targets",
            str(targets_path),
            "--n-students",
            "1000",
            "--output-dir",
            str(output_dir),
            "raked",
        ]
    )
    assert exit_code == 0
    assert (output_dir / "raked_population.csv").exists()
    output = capsys.readouterr().out
    assert "Converged: True" in output
    assert "Post-integerization total students: 1000" in output
