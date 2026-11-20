"""Material quantification, baseline requirement, actual consumption, and procurement simulation.
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from src.data_io import load_coefficients, load_boq, load_activities, load_config
from src.budget import month_of_wd, month_end_wd
from src.schedule import forecast_cpm


MATERIALS_LIST = ["cement_bags", "steel_kg", "sand_cum", "aggregate_cum", "bricks"]


def material_need(item_quantities: Dict[str, float], coeffs: Optional[pd.DataFrame] = None) -> Dict[str, float]:
    """Convert BOQ item quantities to raw material requirements using coefficients.
    
    need = sum(quantity * coefficient) per material.
    """
    if coeffs is None:
        coeffs = load_coefficients()

    coeff_map = coeffs.set_index("item").to_dict(orient="index")
    totals = {mat: 0.0 for mat in MATERIALS_LIST}

    for item, qty in item_quantities.items():
        if item in coeff_map and qty > 0.0:
            row = coeff_map[item]
            for mat in MATERIALS_LIST:
                totals[mat] += float(qty) * float(row.get(mat, 0.0))

    return totals


def baseline_requirement_by_month(
    activities: pd.DataFrame,
    boq: pd.DataFrame,
    cpm_with_dates: pd.DataFrame,
    start_date: Any,
    coeffs: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute baseline monthly material requirement by linearly spreading work over baseline schedule.
    
    Summed over all months, each material equals sum(BOQ quantity * coefficient).
    """
    if coeffs is None:
        coeffs = load_coefficients()

    boq_qty_map = boq.set_index("item")["quantity"].to_dict()
    cpm_map = cpm_with_dates.set_index("id").to_dict(orient="index")

    # Determine project duration in months
    max_ef = int(cpm_with_dates["ef"].max())
    max_month = month_of_wd(max_ef - 1, start_date)

    monthly_item_qty: Dict[int, Dict[str, float]] = {m: {} for m in range(1, max_month + 1)}

    for _, row in activities.iterrows():
        act_id = row["id"]
        dur = int(row["duration_days"])
        boq_items = row["boq_items"]
        if dur <= 0 or not boq_items:
            continue

        cpm_row = cpm_map[act_id]
        es = int(cpm_row["es"])
        ef = int(cpm_row["ef"])

        for d in range(es, ef):
            m = month_of_wd(d, start_date)
            for item, share in boq_items.items():
                total_qty = float(boq_qty_map[item]) * float(share)
                daily_qty = total_qty / float(dur)
                monthly_item_qty[m][item] = monthly_item_qty[m].get(item, 0.0) + daily_qty

    rows = []
    for m in range(1, max_month + 1):
        m_need = material_need(monthly_item_qty[m], coeffs)
        rows.append({"month": m, **m_need})

    return pd.DataFrame(rows)


def actual_consumption_by_month(sim: Any, coeffs: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Compute actual material consumption for months 1..through_month from sim.ac_monthly."""
    if coeffs is None:
        coeffs = load_coefficients()

    ac_df = sim.ac_monthly
    max_month = int(ac_df["month"].max()) if not ac_df.empty else 0

    rows = []
    for m in range(1, max_month + 1):
        m_df = ac_df[ac_df["month"] == m]
        item_qty = m_df.groupby("item")["quantity"].sum().to_dict()
        m_need = material_need(item_qty, coeffs)
        rows.append({"month": m, **m_need})

    return pd.DataFrame(rows)


def forecast_requirement(
    sim: Any,
    m: int,
    activities: pd.DataFrame,
    boq: pd.DataFrame,
    start_date: Any,
    coeffs: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """Compute requirement for month m+1 as known at the end of month m.
    
    Spreads remaining quantities linearly over the forecast_cpm schedule.
    """
    if coeffs is None:
        coeffs = load_coefficients()

    boq_qty_map = boq.set_index("item")["quantity"].to_dict()
    data_date_wd = month_end_wd(m, start_date)
    status_m = sim.status_at(m)
    f_cpm = forecast_cpm(activities, status_m, data_date_wd)
    f_cpm_map = f_cpm.set_index("id").to_dict(orient="index")

    m_start_wd = data_date_wd
    m_end_wd = month_end_wd(m + 1, start_date)

    boq_item_qty: Dict[str, float] = {}

    for _, row in activities.iterrows():
        act_id = row["id"]
        boq_items = row["boq_items"]
        if not boq_items:
            continue

        st = status_m.get(act_id, {"state": "not_started"})
        state = st.get("state", "not_started")
        if state == "done":
            continue

        cpm_row = f_cpm_map[act_id]
        es = int(cpm_row["es"])
        ef = int(cpm_row["ef"])

        if state == "in_progress":
            rem_days = int(st.get("remaining_days", 1))
            # Work remaining runs from data_date_wd to ef
            overlap_start = max(data_date_wd, m_start_wd)
            overlap_end = min(ef, m_end_wd)
            days_in_m1 = max(0, overlap_end - overlap_start)
            fraction = float(days_in_m1) / float(rem_days) if rem_days > 0 else 0.0

            pct = float(sim.pct_complete.loc[act_id, m])
            rem_pct = max(0.0, 1.0 - pct)

            for item, share in boq_items.items():
                item_total_qty = float(boq_qty_map[item]) * float(share)
                qty = item_total_qty * rem_pct * fraction
                boq_item_qty[item] = boq_item_qty.get(item, 0.0) + qty

        elif state == "not_started":
            dur = int(row["duration_days"])
            if dur <= 0:
                continue
            overlap_start = max(es, m_start_wd)
            overlap_end = min(ef, m_end_wd)
            days_in_m1 = max(0, overlap_end - overlap_start)
            fraction = float(days_in_m1) / float(dur)

            for item, share in boq_items.items():
                item_total_qty = float(boq_qty_map[item]) * float(share)
                qty = item_total_qty * fraction
                boq_item_qty[item] = boq_item_qty.get(item, 0.0) + qty

    return material_need(boq_item_qty, coeffs)


def is_injections_enabled(sim: Any, injections_enabled: Optional[bool] = None) -> bool:
    """Determine whether injections are active from flag or SimResult."""
    if injections_enabled is not None:
        return injections_enabled
    if hasattr(sim, "injections_enabled"):
        return bool(sim.injections_enabled)
    return bool(getattr(sim, "injections_applied", []))


def simulate_procurement_ledger(
    sim: Any,
    config: Dict[str, Any],
    activities: pd.DataFrame,
    boq: pd.DataFrame,
    coeffs: Optional[pd.DataFrame] = None,
    injections_enabled: Optional[bool] = None,
) -> Dict[int, pd.DataFrame]:
    """Simulate material inventory ledger across months 1..through_month.
    
    Rules:
    - Month 1: procured = actual consumption(1) + forecast need(2)
      opening stock = 0; closing stock = opening + procured - consumed = forecast need(2)
    - Month m >= 2: procured = forecast need(m+1) * 1.05 (5% buffer)
      Exception (cement_shortage in month 4): procured = forecast need(5) * 0.70
      closing stock = opening stock + procured - consumed
    """
    if coeffs is None:
        coeffs = load_coefficients()

    start_date = config["calendar"]["start_date"]
    through_month = int(sim.ac_monthly["month"].max()) if not sim.ac_monthly.empty else 6

    actual_cons_df = actual_consumption_by_month(sim, coeffs).set_index("month")

    # Injections
    injections_cfg = config.get("injections", {})
    cement_shortage_cfg = injections_cfg.get("cement_shortage", {})
    inj_on = is_injections_enabled(sim, injections_enabled)
    apply_cement_shortage = inj_on and cement_shortage_cfg.get("enabled", True)

    forecast_needs: Dict[int, Dict[str, float]] = {}
    for m in range(1, through_month + 1):
        forecast_needs[m + 1] = forecast_requirement(sim, m, activities, boq, start_date, coeffs)

    opening_stocks: Dict[str, float] = {mat: 0.0 for mat in MATERIALS_LIST}
    monthly_status: Dict[int, pd.DataFrame] = {}

    for m in range(1, through_month + 1):
        req_next = forecast_needs[m + 1]
        cons_row = actual_cons_df.loc[m].to_dict() if m in actual_cons_df.index else {mat: 0.0 for mat in MATERIALS_LIST}

        status_rows = []
        next_opening_stocks: Dict[str, float] = {}

        for mat in MATERIALS_LIST:
            op = opening_stocks[mat]
            cons = cons_row.get(mat, 0.0)
            req = req_next.get(mat, 0.0)

            if m == 1:
                proc = cons + req
            else:
                if m == 4 and mat == "cement_bags" and apply_cement_shortage:
                    fraction = float(cement_shortage_cfg.get("procured_fraction_of_requirement", 0.70))
                    proc = req * fraction
                else:
                    proc = req * 1.05

            shortfall = max(0.0, req - proc)
            surplus = max(0.0, proc - req)
            closing = op + proc - cons

            status_rows.append({
                "material": mat,
                "required_next_month": req,
                "procured_this_month": proc,
                "shortfall": shortfall,
                "surplus": surplus,
                "opening_stock": op,
                "consumed": cons,
                "closing_stock": closing,
            })
            next_opening_stocks[mat] = closing

        opening_stocks = next_opening_stocks
        monthly_status[m] = pd.DataFrame(status_rows)

    return monthly_status


def material_status(
    m: int,
    sim: Any,
    config: Dict[str, Any],
    activities: pd.DataFrame,
    boq: pd.DataFrame,
    coeffs: Optional[pd.DataFrame] = None,
    injections_enabled: Optional[bool] = None,
) -> pd.DataFrame:
    """Return material status table for month m."""
    ledger = simulate_procurement_ledger(sim, config, activities, boq, coeffs, injections_enabled)
    return ledger[m]


def next_month_plan(
    m: int,
    sim: Any,
    config: Dict[str, Any],
    activities: pd.DataFrame,
    boq: pd.DataFrame,
    coeffs: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """Return purchase plan (forecast requirement for month m+1) evaluated at end of month m."""
    start_date = config["calendar"]["start_date"]
    return forecast_requirement(sim, m, activities, boq, start_date, coeffs)
