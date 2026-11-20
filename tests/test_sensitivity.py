"""Tests for sensitivity and what-if analysis."""

import json
from pathlib import Path
import pytest

from src.sensitivity import run_sensitivity, get_or_run_sensitivity


@pytest.fixture(scope="module")
def sens_data():
    """Run sensitivity analysis once for test module."""
    return run_sensitivity(export_json=False)


@pytest.fixture(scope="module")
def base_results():
    """Load baseline results from outputs/results.json if present, or run pipeline."""
    repo_root = Path(__file__).resolve().parent.parent
    res_path = repo_root / "outputs" / "results.json"
    if res_path.exists():
        with open(res_path, "r", encoding="utf-8") as f:
            return json.load(f)
    from src.pipeline import run
    return run(export_outputs=False)


def test_base_case_matches_main_results(sens_data, base_results):
    """Assert the base scenario (10% steel uplift, 10 wd slab delay) matches main results."""
    m6_base = base_results["month_6_headline"]
    sf_base = base_results["schedule_forecast"]

    # Match in steel_sensitivity table (index 1 is 10%)
    steel_10 = sens_data["steel_sensitivity"][1]
    assert steel_10["steel_uplift_pct"] == 10
    assert steel_10["slab_delay_wd"] == 10
    assert steel_10["spi"] == pytest.approx(m6_base["spi"], abs=1e-3)
    assert steel_10["cpi"] == pytest.approx(m6_base["cpi"], abs=1e-3)
    assert steel_10["eac"] == pytest.approx(m6_base["eac"], abs=1)
    assert steel_10["vac"] == pytest.approx(m6_base["vac"], abs=1)
    assert steel_10["cpm_handover_date"] == sf_base["cpm_handover_date"]
    assert steel_10["cpm_delay_wd"] == sf_base["cpm_delay_wd"]

    # Match in slab_delay_sensitivity table (index 1 is 10 wd)
    slab_10 = sens_data["slab_delay_sensitivity"][1]
    assert slab_10["slab_delay_wd"] == 10
    assert slab_10["steel_uplift_pct"] == 10
    assert slab_10["spi"] == pytest.approx(m6_base["spi"], abs=1e-3)
    assert slab_10["cpi"] == pytest.approx(m6_base["cpi"], abs=1e-3)
    assert slab_10["eac"] == pytest.approx(m6_base["eac"], abs=1)
    assert slab_10["vac"] == pytest.approx(m6_base["vac"], abs=1)
    assert slab_10["cpm_handover_date"] == sf_base["cpm_handover_date"]
    assert slab_10["cpm_delay_wd"] == sf_base["cpm_delay_wd"]


def test_identical_10_10_across_both_tables(sens_data):
    """Assert the 10% steel / 10 wd slab delay scenario is strictly identical across both tables."""
    steel_10 = sens_data["steel_sensitivity"][1]
    slab_10 = sens_data["slab_delay_sensitivity"][1]

    assert steel_10["spi"] == slab_10["spi"]
    assert steel_10["cpi"] == slab_10["cpi"]
    assert steel_10["eac"] == slab_10["eac"]
    assert steel_10["vac"] == slab_10["vac"]
    assert steel_10["cpm_handover_date"] == slab_10["cpm_handover_date"]
    assert steel_10["cpm_delay_wd"] == slab_10["cpm_delay_wd"]


def test_steel_escalation_monotonicity(sens_data):
    """Assert higher steel uplift causes lower CPI, higher EAC, and leaves SPI invariant."""
    steel_records = sens_data["steel_sensitivity"]
    assert len(steel_records) == 3

    r5, r10, r15 = steel_records[0], steel_records[1], steel_records[2]

    # SPI invariant since physical schedule is unaffected by cost escalation
    assert r5["spi"] == r10["spi"] == r15["spi"]

    # Handover date and delay invariant
    assert r5["cpm_delay_wd"] == r10["cpm_delay_wd"] == r15["cpm_delay_wd"] == 10
    assert r5["cpm_handover_date"] == r10["cpm_handover_date"] == r15["cpm_handover_date"]

    # Cost performance strictly degrades monotonically
    assert r5["cpi"] > r10["cpi"] > r15["cpi"]
    assert r5["eac"] < r10["eac"] < r15["eac"]
    assert r5["vac"] > r10["vac"] > r15["vac"]  # VAC is more negative as EAC grows


def test_slab_delay_exact_handover_slip(sens_data):
    """Assert slab delay of N working days results in forecast handover delay of exactly N working days."""
    slab_records = sens_data["slab_delay_sensitivity"]
    assert len(slab_records) == 3

    for r in slab_records:
        n_wd = r["slab_delay_wd"]
        assert r["cpm_delay_wd"] == n_wd
