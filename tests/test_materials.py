"""Unit tests for material quantification, baseline requirement, actual consumption, and inventory ledger."""

import pytest
import pandas as pd
import numpy as np

from src.data_io import load_config, load_activities, load_boq, load_coefficients
from src.schedule import compute_cpm, add_dates
from src.simulate import simulate
from src.materials import (
    material_need,
    baseline_requirement_by_month,
    actual_consumption_by_month,
    material_status,
    simulate_procurement_ledger,
    MATERIALS_LIST,
)


def test_material_need():
    """Verify material_need converts BOQ quantities to exact material requirements.
    
    Test: 10 cum RCC M25 -> 80 cement bags, 0 kg steel, 4.2 cum sand, 8.4 cum aggregate, 0 bricks.
    """
    coeffs = load_coefficients()
    need = material_need({"RCC_M25": 10.0}, coeffs=coeffs)

    assert pytest.approx(need["cement_bags"], rel=1e-6) == 80.0
    assert pytest.approx(need["steel_kg"], rel=1e-6) == 0.0
    assert pytest.approx(need["sand_cum"], rel=1e-6) == 4.2
    assert pytest.approx(need["aggregate_cum"], rel=1e-6) == 8.4
    assert pytest.approx(need["bricks"], rel=1e-6) == 0.0


def test_baseline_requirement_sum():
    """Verify baseline monthly requirements summed over all months match total BOQ material needs.
    
    sum(monthly_material) == sum(BOQ quantity * coefficient) for every material (tolerance 1e-6).
    """
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()
    start_date = config["calendar"]["start_date"]

    cpm_df = compute_cpm(activities)
    cpm_with_dates = add_dates(cpm_df, start_date)

    base_req_df = baseline_requirement_by_month(activities, boq, cpm_with_dates, start_date, coeffs=coeffs)

    # Compute expected total need directly from BOQ and coefficients
    boq_qty_map = boq.set_index("item")["quantity"].to_dict()
    expected_totals = material_need(boq_qty_map, coeffs=coeffs)

    for mat in MATERIALS_LIST:
        actual_total = float(base_req_df[mat].sum())
        expected = float(expected_totals[mat])
        assert pytest.approx(actual_total, rel=1e-6) == expected, f"Material {mat} mismatch: {actual_total} vs {expected}"


def test_stock_identity():
    """Verify material inventory ledger satisfies stock identity: closing = opening + procured - consumed."""
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()

    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)
    ledger = simulate_procurement_ledger(sim, config, activities, boq, coeffs)

    for m, stat_df in ledger.items():
        for _, row in stat_df.iterrows():
            mat = row["material"]
            op = float(row["opening_stock"])
            proc = float(row["procured_this_month"])
            cons = float(row["consumed"])
            closing = float(row["closing_stock"])
            expected_closing = op + proc - cons
            assert pytest.approx(closing, abs=1e-6) == expected_closing, (
                f"Month {m} {mat}: closing ({closing}) != opening ({op}) + procured ({proc}) - consumed ({cons})"
            )
