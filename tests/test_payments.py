"""Unit tests for RA bill calculations, statutory deductions, and payment ledger."""

from datetime import date
import pytest
import pandas as pd

from src.data_io import load_config, load_activities, load_boq
from src.simulate import simulate
from src.payments import compute_bill_amounts, generate_bills, bills_at


def test_deductions_and_net_payable():
    """Verify statutory deductions and exact whole-rupee net payable identity.
    
    Gross 1,000,000 -> retention 50,000 (5%), TDS 20,000 (2%), net 930,000.
    """
    res = compute_bill_amounts(1_000_000, retention_pct=5.0, tds_pct=2.0)
    assert res["gross"] == 1_000_000
    assert res["retention"] == 50_000
    assert res["tds"] == 20_000
    assert res["net_payable"] == 930_000
    assert res["gross"] - res["retention"] - res["tds"] == res["net_payable"]


def test_cumulative_retention_and_held_bill():
    """Verify cumulative retention equals running sum of deductions, and held bill has no paid date."""
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    bills_df = generate_bills(sim, config, boq)

    # 1. Cumulative retention equals running sum
    running_sum = 0
    for _, row in bills_df.iterrows():
        running_sum += int(row["retention"])
        assert int(row["cumulative_retention"]) == running_sum

    # 2. Held bill (RA-05) has no paid date and status Held at every date
    ra05_row = bills_df[bills_df["bill_no"] == "RA-05"].iloc[0]
    assert bool(ra05_row["is_held"]) is True
    assert ra05_row["paid_date"] is None

    # Check status at various dates
    for check_date in [date(2026, 6, 1), date(2026, 6, 30), date(2026, 9, 30), date(2027, 1, 1)]:
        b_at = bills_at(check_date, sim, config, boq)
        r5 = b_at[b_at["bill_no"] == "RA-05"].iloc[0]
        assert r5["status"] == "Held"
        assert r5["paid_date"] is None


def test_sum_of_gross_bills_equals_ac():
    """Verify sum of gross RA-01..06 equals simulated actual cost AC at Month 6 to the rupee."""
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    bills_df = generate_bills(sim, config, boq)
    total_gross = int(bills_df["gross_amount"].sum())
    total_ac = int(round(sim.ac_monthly["amount"].sum()))

    assert total_gross == total_ac
    assert total_gross == 19_192_840
