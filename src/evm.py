"""Earned Value Management (EVM) calculation engine and schedule forecasting."""

from datetime import date
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

from src.schedule import add_dates, forecast_cpm, wd_to_date


def evm_metrics(
    pv: float,
    ev: float,
    ac: float,
    bac: float,
) -> Dict[str, Optional[float]]:
    """Compute standard Earned Value Management metrics and forecasts.

    Formulas:
    - Schedule Variance: SV = EV - PV
    - Cost Variance: CV = EV - AC
    - Schedule Performance Index: SPI = EV / PV (None if PV == 0)
    - Cost Performance Index: CPI = EV / AC (None if AC == 0)
    - Estimate at Completion (EAC):
        EAC = BAC / CPI (if CPI is None, EAC = BAC)
        EAC_combined = AC + (BAC - EV) / (CPI * SPI) (None if CPI or SPI is None)
    - Estimate to Complete: ETC = EAC - AC
    - Variance at Completion: VAC = BAC - EAC
    - To-Complete Performance Index:
        TCPI = (BAC - EV) / (BAC - AC) (0 if EV == BAC; None if BAC == AC)
    """
    # 1. Variances
    # Formula: Schedule Variance SV = EV - PV
    sv = ev - pv
    # Formula: Cost Variance CV = EV - AC
    cv = ev - ac

    # 2. Performance Indices
    # Formula: SPI = EV / PV
    spi = (ev / pv) if pv > 0 else None
    # Formula: CPI = EV / AC
    cpi = (ev / ac) if ac > 0 else None

    # 3. Forecasts
    # Formula: EAC = BAC / CPI (assumes historical cost efficiency continues)
    if cpi is not None and cpi > 0:
        eac = bac / cpi
    else:
        # Edge case: AC = 0 (no cost data yet, forecast equals baseline budget)
        eac = bac

    # Formula: EAC_combined = AC + (BAC - EV) / (CPI * SPI)
    # Accounts for combined cost and schedule performance impact on remaining work
    if cpi is not None and spi is not None and (cpi * spi) > 0:
        eac_combined = ac + (bac - ev) / (cpi * spi)
    else:
        eac_combined = None

    # Formula: ETC = EAC - AC (remaining cost expected to complete project)
    etc = eac - ac

    # Formula: VAC = BAC - EAC (variance between baseline budget and final cost forecast)
    vac = bac - eac

    # 4. To-Complete Performance Index
    # Formula: TCPI = (BAC - EV) / (BAC - AC)
    if abs(ev - bac) < 1e-9:
        # When 100% complete (EV = BAC), remaining work is zero
        tcpi = 0.0
    elif abs(bac - ac) < 1e-9:
        # Edge case: budget exhausted (BAC == AC), division by zero
        tcpi = None
    else:
        tcpi = (bac - ev) / (bac - ac)

    return {
        "pv": pv,
        "ev": ev,
        "ac": ac,
        "sv": sv,
        "cv": cv,
        "spi": spi,
        "cpi": cpi,
        "eac": eac,
        "eac_combined": eac_combined,
        "etc": etc,
        "vac": vac,
        "tcpi": tcpi,
    }


def monthly_evm(
    pv_df: pd.DataFrame,
    sim: Any,
    budgets: pd.DataFrame,
    bac_val: float,
    months: Any = range(1, 7),
) -> pd.DataFrame:
    """Compute cumulative EVM metrics table across specified months."""
    budget_map = budgets.set_index("id")["budget_inr"].to_dict()
    cum_pv_map = pv_df.set_index("month")["cum_pv_inr"].to_dict()

    rows = []
    for m in months:
        # 1. Cumulative PV at month end
        pv = float(cum_pv_map.get(m, 0.0))

        # 2. Cumulative EV at month end: sum(activity budget * % complete)
        ev = 0.0
        for act_id, total_b in budget_map.items():
            if act_id in sim.pct_complete.index:
                pct = float(sim.pct_complete.loc[act_id, m])
                ev += total_b * pct

        # 3. Cumulative AC at month end: sum of actual costs incurred up to month m
        if not sim.ac_monthly.empty:
            ac = float(sim.ac_monthly[sim.ac_monthly["month"] <= m]["amount"].sum())
        else:
            ac = 0.0

        # Compute all EVM metrics
        metrics = evm_metrics(pv=pv, ev=ev, ac=ac, bac=bac_val)
        row = {"month": m}
        row.update(metrics)
        rows.append(row)

    return pd.DataFrame(rows)


def activity_evm(
    sim: Any,
    budgets: pd.DataFrame,
    pv_by_activity: Optional[Dict[str, float]],
    month: int,
) -> pd.DataFrame:
    """Compute cumulative EVM status per activity at a given month end."""
    budget_map = budgets.set_index("id")["budget_inr"].to_dict()
    rows = []

    for act_id, b_val in budget_map.items():
        if act_id not in sim.pct_complete.index:
            continue

        pct = float(sim.pct_complete.loc[act_id, month])
        # Formula: EV = Activity Budget * Physical % Complete
        ev = b_val * pct

        # Actual cost incurred on this activity up through month
        if not sim.ac_monthly.empty:
            act_ac_df = sim.ac_monthly[
                (sim.ac_monthly["activity_id"] == act_id) & (sim.ac_monthly["month"] <= month)
            ]
            ac = float(act_ac_df["amount"].sum())
        else:
            ac = 0.0

        pv = pv_by_activity.get(act_id, 0.0) if pv_by_activity else 0.0
        cv = ev - ac
        cpi = (ev / ac) if ac > 0 else None

        # Formula: cost_variance_pct = (AC - EV) / EV * 100
        cost_variance_pct = ((ac - ev) / ev * 100.0) if ev > 0 else 0.0

        rows.append({
            "id": act_id,
            "pv": pv,
            "ev": ev,
            "ac": ac,
            "cv": cv,
            "cpi": cpi,
            "cost_variance_pct": cost_variance_pct,
        })

    return pd.DataFrame(rows)


def item_cost_variance(
    sim: Any,
    item_budget: pd.DataFrame,
    month: Optional[int] = None,
) -> pd.DataFrame:
    """Compute earned value of quantity placed at baseline rate vs actual cost per BOQ item.

    If month is specified, evaluates work placed in that month (month == month).
    """
    boq_rates = item_budget.set_index("item")["rate_inr"].to_dict()
    all_items = sorted(list(set(item_budget["item"])))

    rows = []
    if not sim.ac_monthly.empty:
        if month is not None:
            up_to_m = sim.ac_monthly[sim.ac_monthly["month"] == month]
        else:
            up_to_m = sim.ac_monthly
    else:
        up_to_m = pd.DataFrame()

    for item_key in all_items:
        base_rate = float(boq_rates[item_key])
        if not up_to_m.empty and item_key in set(up_to_m["item"]):
            item_df = up_to_m[up_to_m["item"] == item_key]
            qty_placed = float(item_df["quantity"].sum())
            actual_cost = float(item_df["amount"].sum())
        else:
            qty_placed = 0.0
            actual_cost = 0.0

        # Formula: Earned Value = Quantity Placed * Baseline Unit Rate
        earned_value = qty_placed * base_rate
        # Formula: variance_pct = (Actual Cost - Earned Value) / Earned Value * 100
        if earned_value > 0:
            variance_pct = (actual_cost - earned_value) / earned_value * 100.0
        else:
            variance_pct = 0.0

        rows.append({
            "item": item_key,
            "quantity": qty_placed,
            "earned_value": earned_value,
            "actual_cost": actual_cost,
            "variance_pct": variance_pct,
        })

    return pd.DataFrame(rows)


def schedule_forecast(
    cpm_with_dates: pd.DataFrame,
    activities: pd.DataFrame,
    status_dict: Dict[str, Dict[str, Any]],
    start_date: Union[str, date],
    spi: Optional[float],
    data_date_wd: int,
) -> Dict[str, Any]:
    """Compute crude (duration / SPI) and CPM-based schedule completion forecasts."""
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)

    planned_duration = int(cpm_with_dates["ef"].max())
    baseline_handover_row = cpm_with_dates[cpm_with_dates["id"] == "M_HANDOVER"].iloc[0]
    baseline_handover_date = baseline_handover_row["finish_date"]

    # 1. Crude forecast: planned duration / SPI
    if spi is not None and spi > 0:
        crude_duration = int(round(planned_duration / spi))
        crude_handover_date = wd_to_date(crude_duration - 1, start_date)
        crude_delay_wd = crude_duration - planned_duration
    else:
        crude_duration = planned_duration
        crude_handover_date = baseline_handover_date
        crude_delay_wd = 0

    # 2. CPM-based forecast: re-run CPM with remaining durations from data date
    f_cpm = forecast_cpm(activities, status_dict, data_date_wd)
    f_cpm_dates = add_dates(f_cpm, start_date)

    cpm_duration = int(f_cpm["ef"].max())
    cpm_handover_row = f_cpm_dates[f_cpm_dates["id"] == "M_HANDOVER"].iloc[0]
    cpm_handover_date = cpm_handover_row["finish_date"]
    cpm_delay_wd = cpm_duration - planned_duration

    return {
        "planned_duration_wd": planned_duration,
        "baseline_handover_date": str(baseline_handover_date),
        "crude_duration_wd": crude_duration,
        "crude_handover_date": str(crude_handover_date),
        "crude_delay_wd": crude_delay_wd,
        "cpm_duration_wd": cpm_duration,
        "cpm_handover_date": str(cpm_handover_date),
        "cpm_delay_wd": cpm_delay_wd,
        "forecast_cpm_df": f_cpm_dates,
    }
