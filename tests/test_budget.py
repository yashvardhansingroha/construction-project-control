"""Unit tests for budget calculations, BOQ mapping, and Planned Value (PV) curves."""

from datetime import date
import pytest

from src.data_io import load_activities, load_boq, load_config
from src.schedule import add_dates, compute_cpm, date_to_wd
from src.budget import (
    activity_budgets,
    activity_item_budget,
    bac,
    month_end_wd,
    month_of_wd,
    monthly_pv,
)


@pytest.fixture
def activities():
    return load_activities()


@pytest.fixture
def boq():
    return load_boq()


@pytest.fixture
def config():
    return load_config()


def test_budget_bac_and_activity_sums(activities, boq):
    """Verify that sum of activity budgets equals BAC = 38,113,500 exactly."""
    budgets = activity_budgets(activities, boq)
    total_bac = bac(activities, boq)
    assert total_bac == 38113500.0
    assert budgets["budget_inr"].sum() == 38113500.0

    # Curing activities and milestones must have 0 budget
    b_map = budgets.set_index("id")["budget_inr"].to_dict()
    for _, row in activities.iterrows():
        act_id = row["id"]
        act_type = row["type"]
        if act_type in ["milestone", "curing"]:
            assert b_map[act_id] == 0.0, f"{act_id} expected 0 budget"
        else:
            assert b_map[act_id] > 0.0, f"{act_id} expected positive budget"


def test_monthly_pv_rupee_exact(activities, boq, config):
    """Verify that monthly PV sums to BAC to the rupee and cumulative PV is non-decreasing."""
    start_date = config["calendar"]["start_date"]
    cpm_df = compute_cpm(activities)
    cpm_with_dates = add_dates(cpm_df, start_date)
    budgets = activity_budgets(activities, boq)

    pv_df = monthly_pv(cpm_with_dates, budgets, start_date)

    # Integer equality: sum of monthly PV == BAC
    assert int(pv_df["pv_inr"].sum()) == 38113500
    assert int(pv_df["cum_pv_inr"].iloc[-1]) == 38113500

    # Cumulative PV must be non-decreasing
    for i in range(len(pv_df) - 1):
        assert pv_df["cum_pv_inr"].iloc[i + 1] >= pv_df["cum_pv_inr"].iloc[i]


def test_month_helpers(config):
    """Verify month_of_wd and month_end_wd against calendar date conversions."""
    start_date = config["calendar"]["start_date"]  # 2026-01-05

    # month_of_wd: Jan = 1, Feb = 2, Jun = 6, Sep = 9
    assert month_of_wd(0, start_date) == 1
    # Check end of June date wd
    june_30 = date(2026, 6, 30)
    wd_june_30 = date_to_wd(june_30, start_date)  # 151
    assert month_of_wd(wd_june_30, start_date) == 6

    # month_end_wd(6) matches date_to_wd of 2026-06-30 + 1
    assert month_end_wd(6, start_date) == wd_june_30 + 1
    assert month_end_wd(6, start_date) == 152
