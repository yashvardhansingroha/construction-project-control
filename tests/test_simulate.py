"""Unit tests for monthly simulation invariants, issue injections, and negative controls."""

import pytest
import numpy as np
import pandas as pd

from src.data_io import load_activities, load_boq, load_config
from src.budget import activity_budgets, activity_item_budget, bac, month_end_wd, monthly_pv
from src.schedule import add_dates, compute_cpm
from src.simulate import simulate
from src.evm import activity_evm, item_cost_variance, monthly_evm, schedule_forecast
from src import pipeline


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def activities():
    return load_activities()


@pytest.fixture
def boq():
    return load_boq()


def test_simulation_invariants(config, activities, boq):
    """Verify simulation invariants: progress bounds, monotonicity, full completion, and reproducibility."""
    start_date = config["calendar"]["start_date"]
    cpm_df = compute_cpm(activities)
    cpm_with_dates = add_dates(cpm_df, start_date)
    budgets_df = activity_budgets(activities, boq)
    bac_val = bac(activities, boq)
    pv_df = monthly_pv(cpm_with_dates, budgets_df, start_date)

    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    # 1. % complete in [0, 1] and non-decreasing month to month for every activity
    for act_id in sim.pct_complete.index:
        for m in range(1, 6):
            pct_curr = float(sim.pct_complete.loc[act_id, m])
            pct_next = float(sim.pct_complete.loc[act_id, m + 1])
            assert 0.0 <= pct_curr <= 1.0, f"{act_id} month {m} pct out of range: {pct_curr}"
            assert pct_next >= pct_curr - 1e-9, f"{act_id} decreased from month {m} to {m+1}"

    # 2. Cumulative EV and AC non-decreasing across months
    evm_df = monthly_evm(pv_df, sim, budgets_df, bac_val, months=range(1, 7))
    for i in range(len(evm_df) - 1):
        assert evm_df["ev"].iloc[i + 1] >= evm_df["ev"].iloc[i] - 1e-9
        assert evm_df["ac"].iloc[i + 1] >= evm_df["ac"].iloc[i] - 1e-9

    # 3. Full project simulation at Month 10 gives EV == BAC (to the rupee) and 100% completion
    sim_10 = simulate(config, activities, boq, through_month=10, injections_enabled=True)
    evm_10 = monthly_evm(pv_df, sim_10, budgets_df, bac_val, months=[10])
    ev_10 = int(round(evm_10["ev"].iloc[0]))
    assert ev_10 == int(round(bac_val))

    for act_id in sim_10.pct_complete.index:
        pct_end = float(sim_10.pct_complete.loc[act_id, 10])
        assert pct_end == 1.0, f"Activity {act_id} not 100% complete at month 10"

    # 4. Same seed gives identical results (reproducibility)
    res_1 = pipeline.run(injections_enabled=True)
    res_2 = pipeline.run(injections_enabled=True)
    assert res_1 == res_2

    # 5. Noise draws are identical with injections on and off
    sim_on = simulate(config, activities, boq, through_month=6, injections_enabled=True)
    sim_off = simulate(config, activities, boq, through_month=6, injections_enabled=False)

    # For any activity not subject to the slab delay injection, durations must be identical
    for act_id in activities["id"]:
        if act_id != "SLAB_F2":
            assert sim_on.actual_durations[act_id] == sim_off.actual_durations[act_id]


def test_injections_detection_and_negative_control(config, activities, boq):
    """Verify that injected issues are detected and negative control yields no red flags."""
    start_date = config["calendar"]["start_date"]
    cpm_df = compute_cpm(activities)
    cpm_with_dates = add_dates(cpm_df, start_date)
    budgets_df = activity_budgets(activities, boq)
    item_budget_df = activity_item_budget(activities, boq)
    bac_val = bac(activities, boq)
    pv_df = monthly_pv(cpm_with_dates, budgets_df, start_date)
    data_date_wd = month_end_wd(6, start_date)

    # Simulation WITH injections
    sim_on = simulate(config, activities, boq, through_month=6, injections_enabled=True)
    evm_on = monthly_evm(pv_df, sim_on, budgets_df, bac_val, months=range(1, 7))
    m6_on = evm_on[evm_on["month"] == 6].iloc[0]

    # (a) CPM-based forecast handover delay = 10 working days with injections on, 0 with them off
    fc_on = schedule_forecast(
        cpm_with_dates=cpm_with_dates,
        activities=activities,
        status_dict=sim_on.status_at(6),
        start_date=start_date,
        spi=m6_on["spi"],
        data_date_wd=data_date_wd,
    )
    assert fc_on["cpm_delay_wd"] == 10

    sim_off = simulate(config, activities, boq, through_month=6, injections_enabled=False)
    evm_off = monthly_evm(pv_df, sim_off, budgets_df, bac_val, months=range(1, 7))
    m6_off = evm_off[evm_off["month"] == 6].iloc[0]

    fc_off = schedule_forecast(
        cpm_with_dates=cpm_with_dates,
        activities=activities,
        status_dict=sim_off.status_at(6),
        start_date=start_date,
        spi=m6_off["spi"],
        data_date_wd=data_date_wd,
    )
    assert fc_off["cpm_delay_wd"] == 0

    # (b) With injections on, activities containing STEEL that placed work in months 3-6
    # have CV < 0 and CPI < 1 for that work, and STEEL item variance at month 6 is between +9% and +11%
    # Check STEEL item variance at month 6
    item_var_m6 = item_cost_variance(sim_on, item_budget_df, month=6)
    steel_m6 = item_var_m6[item_var_m6["item"] == "STEEL"].iloc[0]
    assert 9.0 <= steel_m6["variance_pct"] <= 11.0

    # Check activities containing STEEL placing work in months 3-6
    steel_activities = set(item_budget_df[item_budget_df["item"] == "STEEL"]["activity_id"])
    ac_3_6 = sim_on.ac_monthly[
        (sim_on.ac_monthly["month"] >= 3)
        & (sim_on.ac_monthly["month"] <= 6)
        & (sim_on.ac_monthly["item"] == "STEEL")
    ]
    active_steel_acts = set(ac_3_6["activity_id"])
    assert len(active_steel_acts) > 0

    for act_id in active_steel_acts:
        # Check actual cost vs earned value for that activity across months 3-6
        act_work = sim_on.ac_monthly[
            (sim_on.ac_monthly["activity_id"] == act_id)
            & (sim_on.ac_monthly["month"] >= 3)
            & (sim_on.ac_monthly["month"] <= 6)
        ]
        act_ac = act_work["amount"].sum()
        # Earned value for that placed work: sum(quantity * baseline_rate)
        rates_map = item_budget_df.set_index("item")["rate_inr"].to_dict()
        act_ev = sum(r["quantity"] * rates_map[r["item"]] for _, r in act_work.iterrows())
        assert act_ac > act_ev, f"{act_id} AC ({act_ac}) should exceed EV ({act_ev})"
        act_cv = act_ev - act_ac
        act_cpi = act_ev / act_ac
        assert act_cv < 0, f"{act_id} expected CV < 0"
        assert act_cpi < 1.0, f"{act_id} expected CPI < 1.0"

    # (c) Activities without STEEL show |cost_variance_pct| <= 3% (noise bound)
    non_steel_activities = set(activities["id"]) - steel_activities
    act_evm_m6 = activity_evm(sim_on, budgets_df, pv_by_activity=None, month=6)
    for _, r in act_evm_m6.iterrows():
        act_id = r["id"]
        if act_id in non_steel_activities and r["ev"] > 0:
            assert abs(r["cost_variance_pct"]) <= 3.0 + 1e-6, (
                f"{act_id} variance {r['cost_variance_pct']}% exceeds 3% noise bound"
            )

    # (d) Month-6 SPI < 1 with injections on
    assert m6_on["spi"] < 1.0

    # (e) Negative control: injections off -> SPI and CPI >= 0.95 for all months 1-6
    for _, row in evm_off.iterrows():
        m = int(row["month"])
        spi_val = row["spi"]
        cpi_val = row["cpi"]
        assert spi_val is not None and spi_val >= 0.95, f"Month {m} negative control SPI {spi_val} < 0.95"
        assert cpi_val is not None and cpi_val >= 0.95, f"Month {m} negative control CPI {cpi_val} < 0.95"
