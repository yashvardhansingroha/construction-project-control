"""Master execution pipeline integrating schedule, budget, simulation, EVM, materials, payments, and QC."""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

# Ensure repo root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.data_io import load_activities, load_boq, load_config, load_coefficients
from src.schedule import add_dates, compute_cpm, critical_path, wd_to_date
from src.budget import activity_budgets, activity_item_budget, bac, month_end_wd, monthly_pv
from src.simulate import simulate
from src.evm import activity_evm, item_cost_variance, monthly_evm, schedule_forecast
from src.charts import gantt_chart, s_curve_chart
from src.materials import material_status, next_month_plan
from src.payments import bills_at
from src.quality import build_inspections, quality_summary, ncr_log_at
from src.flags import evaluate_flags, get_top_issues


def _round_val(val: Any) -> Any:
    """Helper to round numbers: whole integers for amounts, 3 decimals for indices."""
    if val is None:
        return None
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        if abs(val) >= 100.0:
            return int(round(val))
        return round(float(val), 3)
    return val


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively convert Dates, NumPy scalars, and DataFrames to JSON-serializable types."""
    if obj is None:
        return None
    if isinstance(obj, float) and (np.isnan(obj) or pd.isna(obj)):
        return None
    if isinstance(obj, (date, pd.Timestamp)):
        return str(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return float(obj)
    if isinstance(obj, pd.DataFrame):
        records = obj.to_dict(orient="records")
        return [_sanitize_for_json(r) for r in records]
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(item) for item in obj]
    return obj


import copy
import calendar

_CACHE: Dict[Tuple[Any, ...], Dict[str, Any]] = {}


def _deep_update(base: dict, overrides: dict) -> dict:
    """Recursively update a nested dictionary in place."""
    for k, v in overrides.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _get_pipeline_context(
    config_path: Optional[Union[str, Path]] = None,
    injections_enabled: Optional[bool] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Retrieve or compute core schedule, budget, coefficients, and simulation objects."""
    overrides_key = json.dumps(config_overrides, sort_keys=True) if config_overrides else None
    cache_key = (str(config_path) if config_path else None, injections_enabled, overrides_key)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    config = load_config(config_path) if config_path is not None else load_config()
    if config_overrides:
        config = copy.deepcopy(config)
        _deep_update(config, config_overrides)
    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()
    start_date = config["calendar"]["start_date"]
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)

    cpm_df = compute_cpm(activities)
    cpm_with_dates = add_dates(cpm_df, start_date)
    crit_path_ids = critical_path(cpm_df)
    planned_duration = int(cpm_df["ef"].max())
    baseline_handover_row = cpm_with_dates[cpm_with_dates["id"] == "M_HANDOVER"].iloc[0]
    baseline_handover_date = str(baseline_handover_row["finish_date"])

    item_budget_df = activity_item_budget(activities, boq)
    budgets_df = activity_budgets(activities, boq)
    bac_value = bac(activities, boq)
    pv_full_df = monthly_pv(cpm_with_dates, budgets_df, start_date)

    sim_result = simulate(
        config=config,
        activities=activities,
        boq=boq,
        through_month=6,
        injections_enabled=injections_enabled,
    )

    evm_df = monthly_evm(pv_full_df, sim_result, budgets_df, bac_value, months=range(1, 7))

    ctx = {
        "config": config,
        "activities": activities,
        "boq": boq,
        "coeffs": coeffs,
        "start_date": start_date,
        "cpm_df": cpm_df,
        "cpm_with_dates": cpm_with_dates,
        "crit_path_ids": crit_path_ids,
        "planned_duration": planned_duration,
        "baseline_handover_date": baseline_handover_date,
        "item_budget_df": item_budget_df,
        "budgets_df": budgets_df,
        "bac_value": bac_value,
        "pv_full_df": pv_full_df,
        "sim_result": sim_result,
        "evm_df": evm_df,
        "injections_enabled": injections_enabled,
    }
    _CACHE[cache_key] = ctx
    return ctx


def month_view(
    m: int,
    injections_enabled: Optional[bool] = None,
    config_path: Optional[Union[str, Path]] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return all project control data for month m (1..6) for reporting and dashboards.
    
    Overall status rule (FROZEN):
    - RED if any red flag of category milestone_slip, spi, or cpi
    - else AMBER if any red or amber flag
    - else GREEN
    """
    ctx = _get_pipeline_context(config_path, injections_enabled, config_overrides)
    config = ctx["config"]
    activities = ctx["activities"]
    boq = ctx["boq"]
    coeffs = ctx["coeffs"]
    start_date = ctx["start_date"]
    cpm_with_dates = ctx["cpm_with_dates"]
    budgets_df = ctx["budgets_df"]
    bac_value = ctx["bac_value"]
    pv_full_df = ctx["pv_full_df"]
    sim_result = ctx["sim_result"]

    year = start_date.year
    last_day = calendar.monthrange(year, m)[1]
    month_end_date = date(year, m, last_day)

    # 1. EVM table rows 1..m and headline m
    evm_df = monthly_evm(pv_full_df, sim_result, budgets_df, bac_value, months=range(1, m + 1))
    monthly_evm_records = []
    for _, r in evm_df.iterrows():
        monthly_evm_records.append({
            "month": int(r["month"]),
            "pv": _round_val(r["pv"]),
            "ev": _round_val(r["ev"]),
            "ac": _round_val(r["ac"]),
            "sv": _round_val(r["sv"]),
            "cv": _round_val(r["cv"]),
            "spi": _round_val(r["spi"]),
            "cpi": _round_val(r["cpi"]),
            "eac": _round_val(r["eac"]),
            "eac_combined": _round_val(r["eac_combined"]),
            "etc": _round_val(r["etc"]),
            "vac": _round_val(r["vac"]),
            "tcpi": _round_val(r["tcpi"]),
        })

    m_evm_row = evm_df[evm_df["month"] == m].iloc[0]
    headline = {
        "pv": _round_val(m_evm_row["pv"]),
        "ev": _round_val(m_evm_row["ev"]),
        "ac": _round_val(m_evm_row["ac"]),
        "sv": _round_val(m_evm_row["sv"]),
        "cv": _round_val(m_evm_row["cv"]),
        "spi": _round_val(m_evm_row["spi"]),
        "cpi": _round_val(m_evm_row["cpi"]),
        "eac": _round_val(m_evm_row["eac"]),
        "eac_combined": _round_val(m_evm_row["eac_combined"]),
        "etc": _round_val(m_evm_row["etc"]),
        "vac": _round_val(m_evm_row["vac"]),
        "tcpi": _round_val(m_evm_row["tcpi"]),
    }

    # 2. Schedule forecast at month end m
    data_date_wd = month_end_wd(m, start_date)
    m_spi = m_evm_row["spi"]
    f_info = schedule_forecast(
        cpm_with_dates=cpm_with_dates,
        activities=activities,
        status_dict=sim_result.status_at(m),
        start_date=start_date,
        spi=m_spi,
        data_date_wd=data_date_wd,
    )

    f_cpm_df = f_info["forecast_cpm_df"].set_index("id")
    cpm_dates_map = cpm_with_dates.set_index("id").to_dict(orient="index")

    milestones_list = []
    for _, row in activities[activities["type"] == "milestone"].iterrows():
        ms_id = row["id"]
        ms_name = row["name"]
        b_ef = int(cpm_dates_map[ms_id]["ef"])
        f_ef = int(f_cpm_df.loc[ms_id, "ef"])
        slip_wd = f_ef - b_ef
        b_date = str(cpm_dates_map[ms_id]["finish_date"])
        f_date = str(wd_to_date(f_ef - 1 if f_ef > 0 else 0, start_date))

        # Check if achieved by month m
        st = sim_result.status_at(m).get(ms_id, {})
        is_done = st.get("state") == "done"
        act_finish_wd = st.get("actual_finish")
        if is_done and act_finish_wd is not None:
            act_finish_date = str(wd_to_date(act_finish_wd - 1 if act_finish_wd > 0 else 0, start_date))
            status_text = f"Achieved ({date.fromisoformat(act_finish_date).strftime('%d %b %Y')})"
            status_val = "Achieved"
            achieved_date = act_finish_date
        else:
            status_text = f"Forecast ({date.fromisoformat(f_date).strftime('%d %b %Y')})"
            status_val = "Forecast"
            achieved_date = None

        milestones_list.append({
            "id": ms_id,
            "name": ms_name,
            "baseline_date": b_date,
            "forecast_date": f_date,
            "slip_wd": slip_wd,
            "status": status_val,
            "status_text": status_text,
            "achieved_date": achieved_date,
        })

    schedule_forecast_dict = {
        "planned_duration_wd": f_info["planned_duration_wd"],
        "baseline_handover_date": f_info["baseline_handover_date"],
        "crude_duration_wd": f_info["crude_duration_wd"],
        "crude_handover_date": f_info["crude_handover_date"],
        "crude_delay_wd": f_info["crude_delay_wd"],
        "cpm_duration_wd": f_info["cpm_duration_wd"],
        "cpm_handover_date": f_info["cpm_handover_date"],
        "cpm_delay_wd": f_info["cpm_delay_wd"],
        "milestones": milestones_list,
    }

    # 3. Flags and top 5
    m_flags = evaluate_flags(
        month=m,
        sim=sim_result,
        config=config,
        activities=activities,
        boq=boq,
        coeffs=coeffs,
        injections_enabled=injections_enabled,
    )
    top_5 = get_top_issues(m_flags, limit=5)

    # 4. Overall status rule
    has_red_core = any(
        f["severity"] == "red" and f["category"] in ["milestone_slip", "spi", "cpi"]
        for f in m_flags
    )
    has_any_flag = any(f["severity"] in ["red", "amber"] for f in m_flags)

    if has_red_core:
        overall_status = "RED"
    elif has_any_flag:
        overall_status = "AMBER"
    else:
        overall_status = "GREEN"

    # Status line
    h_date_obj = date.fromisoformat(f_info["cpm_handover_date"])
    h_date_fmt = h_date_obj.strftime("%d %b %Y")
    delay_wd = f_info["cpm_delay_wd"]
    spi_str = f"{m_spi:.3f}" if m_spi is not None else "1.000"
    cpi_str = f"{m_evm_row['cpi']:.3f}" if m_evm_row['cpi'] is not None else "1.000"

    if delay_wd > 0:
        status_line = f"{overall_status}: handover forecast {h_date_fmt}, {delay_wd} working days late; SPI {spi_str}, CPI {cpi_str}"
    else:
        status_line = f"{overall_status}: on schedule and within budget; handover forecast {h_date_fmt}; SPI {spi_str}, CPI {cpi_str}"

    # 5. Materials
    mat_stat_df = material_status(
        m=m,
        sim=sim_result,
        config=config,
        activities=activities,
        boq=boq,
        coeffs=coeffs,
        injections_enabled=injections_enabled,
    )
    m_mat_stat = mat_stat_df.to_dict(orient="records")
    for r in m_mat_stat:
        for k in ["required_next_month", "procured_this_month", "shortfall", "surplus", "opening_stock", "consumed", "closing_stock"]:
            r[k] = round(float(r[k]), 1)

    m_plan = next_month_plan(
        m=m,
        sim=sim_result,
        config=config,
        activities=activities,
        boq=boq,
        coeffs=coeffs,
    )
    m_plan = {k: round(float(v), 1) for k, v in m_plan.items()}

    # 6. Payments
    m_bills_df = bills_at(
        eval_date=month_end_date,
        sim=sim_result,
        config=config,
        boq=boq,
        injections_enabled=injections_enabled,
    )
    m_bills = _sanitize_for_json(m_bills_df)

    # 7. QC & NCRs
    m_qc = quality_summary(
        eval_date=month_end_date,
        sim=sim_result,
        activities=activities,
        config=config,
        injections_enabled=injections_enabled,
    )
    m_ncrs_df = ncr_log_at(
        eval_date=month_end_date,
        sim=sim_result,
        activities=activities,
        config=config,
        injections_enabled=injections_enabled,
    )
    m_ncrs = _sanitize_for_json(m_ncrs_df)

    return {
        "month": m,
        "month_date": str(month_end_date),
        "overall_status": overall_status,
        "status_line": status_line,
        "monthly_evm": monthly_evm_records,
        "headline": headline,
        "schedule_forecast": schedule_forecast_dict,
        "flags": _sanitize_for_json(m_flags),
        "top_5_issues": _sanitize_for_json(top_5),
        "material_status": m_mat_stat,
        "next_month_plan": m_plan,
        "ra_bills": m_bills,
        "qc_summary": _sanitize_for_json(m_qc),
        "ncr_log": m_ncrs,
    }


def run(
    config_path: Optional[Union[str, Path]] = None,
    injections_enabled: Optional[bool] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
    export_outputs: Optional[bool] = None,
) -> Dict[str, Any]:
    """Execute complete project control pipeline and export results.json and charts."""
    if export_outputs is None:
        export_outputs = (config_overrides is None)

    if config_path is not None:
        config = load_config(config_path)
    else:
        config = load_config()

    if config_overrides:
        config = copy.deepcopy(config)
        _deep_update(config, config_overrides)

    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()
    start_date = config["calendar"]["start_date"]
    data_date = config["calendar"]["data_date"]

    # 1. Baseline Schedule & CPM
    cpm_df = compute_cpm(activities)
    cpm_with_dates = add_dates(cpm_df, start_date)
    crit_path_ids = critical_path(cpm_df)
    planned_duration = int(cpm_df["ef"].max())
    baseline_handover_row = cpm_with_dates[cpm_with_dates["id"] == "M_HANDOVER"].iloc[0]
    baseline_handover_date = str(baseline_handover_row["finish_date"])

    # 2. Baseline Budget & Planned Value
    item_budget_df = activity_item_budget(activities, boq)
    budgets_df = activity_budgets(activities, boq)
    bac_value = bac(activities, boq)
    pv_full_df = monthly_pv(cpm_with_dates, budgets_df, start_date)

    # 3. Monthly Actual Simulation (through Month 6)
    sim_result = simulate(
        config=config,
        activities=activities,
        boq=boq,
        through_month=6,
        injections_enabled=injections_enabled,
    )

    # 4. Monthly EVM Analysis
    evm_df = monthly_evm(pv_full_df, sim_result, budgets_df, bac_value, months=range(1, 7))

    # Month 6 Schedule Forecasts
    data_date_wd = month_end_wd(6, start_date)
    m6_evm_row = evm_df[evm_df["month"] == 6].iloc[0]
    m6_spi = m6_evm_row["spi"]

    forecast_info = schedule_forecast(
        cpm_with_dates=cpm_with_dates,
        activities=activities,
        status_dict=sim_result.status_at(6),
        start_date=start_date,
        spi=m6_spi,
        data_date_wd=data_date_wd,
    )

    # Build monthly EVM records
    monthly_evm_records = []
    for _, r in evm_df.iterrows():
        rec = {
            "month": int(r["month"]),
            "pv": _round_val(r["pv"]),
            "ev": _round_val(r["ev"]),
            "ac": _round_val(r["ac"]),
            "sv": _round_val(r["sv"]),
            "cv": _round_val(r["cv"]),
            "spi": _round_val(r["spi"]),
            "cpi": _round_val(r["cpi"]),
            "eac": _round_val(r["eac"]),
            "eac_combined": _round_val(r["eac_combined"]),
            "etc": _round_val(r["etc"]),
            "vac": _round_val(r["vac"]),
            "tcpi": _round_val(r["tcpi"]),
        }
        monthly_evm_records.append(rec)

    m6_headline = {
        "pv": _round_val(m6_evm_row["pv"]),
        "ev": _round_val(m6_evm_row["ev"]),
        "ac": _round_val(m6_evm_row["ac"]),
        "sv": _round_val(m6_evm_row["sv"]),
        "cv": _round_val(m6_evm_row["cv"]),
        "spi": _round_val(m6_evm_row["spi"]),
        "cpi": _round_val(m6_evm_row["cpi"]),
        "eac": _round_val(m6_evm_row["eac"]),
        "eac_combined": _round_val(m6_evm_row["eac_combined"]),
        "etc": _round_val(m6_evm_row["etc"]),
        "vac": _round_val(m6_evm_row["vac"]),
        "tcpi": _round_val(m6_evm_row["tcpi"]),
    }

    # Item cost variance for STEEL
    item_var_df = item_cost_variance(sim_result, item_budget_df, month=6)
    steel_row = item_var_df[item_var_df["item"] == "STEEL"]
    steel_var_pct = float(steel_row["variance_pct"].iloc[0]) if not steel_row.empty else 0.0

    # 5. T4 Additions: Flags, Materials, Payments, Quality
    flags_by_month: Dict[str, List[Dict[str, Any]]] = {}
    flags_count_by_severity: Dict[str, Dict[str, int]] = {}

    for m in range(1, 7):
        fl = evaluate_flags(
            month=m,
            sim=sim_result,
            config=config,
            activities=activities,
            boq=boq,
            coeffs=coeffs,
            injections_enabled=injections_enabled,
        )
        flags_by_month[str(m)] = fl
        n_red = sum(1 for f in fl if f["severity"] == "red")
        n_amber = sum(1 for f in fl if f["severity"] == "amber")
        flags_count_by_severity[str(m)] = {"red": n_red, "amber": n_amber}

    m6_flags = flags_by_month["6"]
    month_6_top_5_issues = get_top_issues(m6_flags, limit=5)

    # Material Status Month 6 & Plan Month 7
    m6_mat_status_df = material_status(
        m=6,
        sim=sim_result,
        config=config,
        activities=activities,
        boq=boq,
        coeffs=coeffs,
        injections_enabled=injections_enabled,
    )
    month_6_material_status = m6_mat_status_df.to_dict(orient="records")
    for r in month_6_material_status:
        for k in ["required_next_month", "procured_this_month", "shortfall", "surplus", "opening_stock", "consumed", "closing_stock"]:
            r[k] = round(float(r[k]), 1)

    month_6_next_month_plan = next_month_plan(
        m=6,
        sim=sim_result,
        config=config,
        activities=activities,
        boq=boq,
        coeffs=coeffs,
    )
    month_6_next_month_plan = {k: round(float(v), 1) for k, v in month_6_next_month_plan.items()}

    # RA Bills at Data Date
    bills_df = bills_at(
        eval_date=data_date,
        sim=sim_result,
        config=config,
        boq=boq,
        injections_enabled=injections_enabled,
    )
    ra_bills_records = bills_df.to_dict(orient="records")

    # QC Summary & NCR Log at Data Date
    qc_summary_dict = quality_summary(
        eval_date=data_date,
        sim=sim_result,
        activities=activities,
        config=config,
        injections_enabled=injections_enabled,
    )
    ncr_log_df = ncr_log_at(
        eval_date=data_date,
        sim=sim_result,
        activities=activities,
        config=config,
        injections_enabled=injections_enabled,
    )
    ncr_log_records = ncr_log_df.to_dict(orient="records")

    # 6. Build Master Results Dictionary
    baseline_cpm_records = []
    for _, r in cpm_df.iterrows():
        baseline_cpm_records.append({
            "id": str(r["id"]),
            "duration": int(r["duration_days"]),
            "es": int(r["es"]),
            "ef": int(r["ef"]),
            "ls": int(r["ls"]),
            "lf": int(r["lf"]),
            "total_float": int(r["total_float"]),
            "is_critical": bool(r["is_critical"]),
        })
    retention_held = sum(int(b["retention"]) for b in ra_bills_records)

    results = {
        "synthetic": True,
        "bac": int(round(bac_value)),
        "baseline_duration_wd": planned_duration,
        "baseline_handover_date": baseline_handover_date,
        "baseline_cpm": baseline_cpm_records,
        "total_activities": len(cpm_df),
        "retention_held_to_date": retention_held,
        "critical_path": crit_path_ids,
        "injections_applied": sim_result.injections_applied,
        "monthly_evm": monthly_evm_records,
        "month_6_headline": m6_headline,
        "schedule_forecast": {
            "planned_duration_wd": forecast_info["planned_duration_wd"],
            "baseline_handover_date": forecast_info["baseline_handover_date"],
            "crude_duration_wd": forecast_info["crude_duration_wd"],
            "crude_handover_date": forecast_info["crude_handover_date"],
            "crude_delay_wd": forecast_info["crude_delay_wd"],
            "cpm_duration_wd": forecast_info["cpm_duration_wd"],
            "cpm_handover_date": forecast_info["cpm_handover_date"],
            "cpm_delay_wd": forecast_info["cpm_delay_wd"],
            "milestones": month_view(6, injections_enabled=injections_enabled, config_path=config_path, config_overrides=config_overrides)["schedule_forecast"]["milestones"],
        },
        "steel_item_variance_month_6_pct": round(steel_var_pct, 2),
        "flags": _sanitize_for_json(flags_by_month),
        "flags_count_by_severity": flags_count_by_severity,
        "month_6_top_5_issues": _sanitize_for_json(month_6_top_5_issues),
        "month_6_material_status": month_6_material_status,
        "month_6_next_month_plan": month_6_next_month_plan,
        "ra_bills_at_data_date": _sanitize_for_json(ra_bills_records),
        "qc_summary_at_data_date": _sanitize_for_json(qc_summary_dict),
        "ncr_log_at_data_date": _sanitize_for_json(ncr_log_records),
        "overall_status_month_6": month_view(6, injections_enabled=injections_enabled, config_path=config_path, config_overrides=config_overrides)["overall_status"],
    }

    if export_outputs:
        # Sensitivity Analysis
        from src.sensitivity import run_sensitivity
        sens_data = run_sensitivity(export_json=True)
        results["sensitivity"] = sens_data

        # 7. Save Charts and Results JSON
        charts_dir = repo_root / "outputs" / "charts"
        charts_dir.mkdir(parents=True, exist_ok=True)

        # (a) S-Curve chart
        s_curve_path = charts_dir / "s_curve.png"
        s_curve_chart(
            monthly_evm_df=evm_df,
            pv_full_df=pv_full_df,
            path=s_curve_path,
            title="G+4 Residential Building: Baseline vs Actual S-Curve (Synthetic)",
        )

        # (b) Gantt forecast chart
        gantt_fcast_path = charts_dir / "gantt_forecast.png"
        gantt_chart(
            cpm_df_with_dates=cpm_with_dates,
            path=gantt_fcast_path,
            forecast_df=forecast_info["forecast_cpm_df"],
            title="G+4 Residential Building: Baseline vs Forecast Schedule (Synthetic)",
        )

        # (c) results.json
        results_path = repo_root / "outputs" / "results.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, sort_keys=True)

        # (d) Excel workbook & Month 6 PDF report
        from src.report import write_workbook, build_pdf
        wb_path = repo_root / "outputs" / "workbook.xlsx"
        write_workbook(wb_path, injections_enabled=injections_enabled)
        pdf_path = repo_root / "outputs" / "report_month_06.pdf"
        build_pdf(6, pdf_path, injections_enabled=injections_enabled)

    return results


def main() -> None:
    """Run pipeline and print comprehensive summary to stdout."""
    res = run()
    print("=" * 72)
    print("PIPELINE EXECUTION COMPLETE (Synthetic)")
    print("=" * 72)
    print(f"BAC: INR {res['bac']:,}")
    print(f"Baseline Handover Date: {res['baseline_handover_date']} ({res['baseline_duration_wd']} working days)")
    print(f"Crude Forecast Handover: {res['schedule_forecast']['crude_handover_date']} (Delay: +{res['schedule_forecast']['crude_delay_wd']} wd)")
    print(f"CPM-Based Forecast Handover: {res['schedule_forecast']['cpm_handover_date']} (Delay: +{res['schedule_forecast']['cpm_delay_wd']} wd)")
    print(f"STEEL Item Variance Month 6: {res['steel_item_variance_month_6_pct']:.2f}%")
    print(f"Injections Applied: {res['injections_applied']}")
    print("-" * 72)
    print("Month 1-6 EVM Table:")
    print(f"{'M':<3} {'PV (INR)':<12} {'EV (INR)':<12} {'AC (INR)':<12} {'SPI':<7} {'CPI':<7} {'EAC (INR)':<12}")
    for m_rec in res["monthly_evm"]:
        spi_s = f"{m_rec['spi']:.3f}" if m_rec['spi'] is not None else "N/A"
        cpi_s = f"{m_rec['cpi']:.3f}" if m_rec['cpi'] is not None else "N/A"
        eac_s = f"{m_rec['eac']:,}" if m_rec['eac'] is not None else "N/A"
        print(f"{m_rec['month']:<3} {m_rec['pv']:<12,} {m_rec['ev']:<12,} {m_rec['ac']:<12,} {spi_s:<7} {cpi_s:<7} {eac_s:<12}")
    print("-" * 72)
    print("Flag Counts by Severity (Months 1-6):")
    for m_str, counts in res["flags_count_by_severity"].items():
        print(f"  Month {m_str}: RED = {counts['red']}, AMBER = {counts['amber']}")
    print("-" * 72)
    print("Month 6 Top 5 Issues:")
    for idx, issue in enumerate(res["month_6_top_5_issues"], start=1):
        print(f"  {idx}. [{issue['severity'].upper()}] {issue['where']}: {issue['what']} (Mag: {issue['magnitude']})")
        print(f"     Owner: {issue['owner']} | Action: {issue['action']}")
    print("-" * 72)
    print("Month 6 Material Status Table:")
    print(f"{'Material':<15} {'Required M7':<13} {'Procured M6':<13} {'Shortfall':<11} {'Surplus':<10} {'Closing Stock':<14}")
    for mat_row in res["month_6_material_status"]:
        print(f"{mat_row['material']:<15} {mat_row['required_next_month']:<13.1f} {mat_row['procured_this_month']:<13.1f} {mat_row['shortfall']:<11.1f} {mat_row['surplus']:<10.1f} {mat_row['closing_stock']:<14.1f}")
    print(f"Month 7 Purchase Plan: {res['month_6_next_month_plan']}")
    print("-" * 72)
    print("RA Bill Table at Data Date (2026-06-30):")
    print(f"{'Bill No':<8} {'Gross (INR)':<13} {'Retention':<11} {'TDS':<9} {'Net Payable':<13} {'Status':<9} {'Days Pend':<10} {'Days Pay':<9}")
    for b in res["ra_bills_at_data_date"]:
        dp = str(b['days_pending']) if b['days_pending'] is not None else "-"
        dpy = str(b['days_to_pay']) if b['days_to_pay'] is not None else "-"
        print(f"{b['bill_no']:<8} {b['gross_amount']:<13,} {b['retention']:<11,} {b['tds']:<9,} {b['net_payable']:<13,} {b['status']:<9} {dp:<10} {dpy:<9}")
    print("-" * 72)
    print(f"QC Summary at Data Date: Inspections: {res['qc_summary_at_data_date']['total_inspections']}, Passes: {res['qc_summary_at_data_date']['passes']}, Pass Rate: {res['qc_summary_at_data_date']['pass_rate']*100:.1f}%, Open NCRs: {res['qc_summary_at_data_date']['open_ncrs']}")
    print("NCR Log at Data Date:")
    for ncr in res["ncr_log_at_data_date"]:
        cl = str(ncr['closed_date']) if ncr['closed_date'] else "None"
        print(f"  {ncr['ncr_id']} ({ncr['activity_id']} - {ncr['check_type']}): Raised {ncr['raised_date']}, Closed {cl}, Status: {ncr['status']}, Days Open: {ncr['days_open']}")
    print("=" * 72)


if __name__ == "__main__":
    main()
