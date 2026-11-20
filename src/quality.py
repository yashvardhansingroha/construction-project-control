"""Quality control inspection logs, Non-Conformance Reports (NCR), and QC summary metrics.
"""
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd

from src.data_io import load_config, load_activities
from src.schedule import compute_cpm, wd_to_date


def get_actual_dates(sim: Any, activities: pd.DataFrame, start_date: Any) -> Dict[str, Dict[str, Any]]:
    """Compute actual start and finish dates per activity from sim.actual_durations."""
    actual_acts = activities.copy()
    actual_acts["duration_days"] = [sim.actual_durations[aid] for aid in actual_acts["id"]]
    cpm_df = compute_cpm(actual_acts)

    dates_map: Dict[str, Dict[str, Any]] = {}
    for _, row in cpm_df.iterrows():
        aid = row["id"]
        dur = int(row["duration_days"])
        es = int(row["es"])
        ef = int(row["ef"])
        s_date = wd_to_date(es, start_date)
        f_date = wd_to_date(ef - 1, start_date) if dur > 0 else s_date
        dates_map[aid] = {
            "start_date": s_date,
            "finish_date": f_date,
            "es": es,
            "ef": ef,
            "duration": dur,
        }
    return dates_map


def is_injections_enabled(sim: Any, injections_enabled: Optional[bool] = None) -> bool:
    """Determine whether injections are active from flag or SimResult."""
    if injections_enabled is not None:
        return injections_enabled
    if hasattr(sim, "injections_enabled"):
        return bool(sim.injections_enabled)
    return bool(getattr(sim, "injections_applied", []))


def build_inspections(
    sim: Any,
    activities: Optional[pd.DataFrame] = None,
    config: Optional[Dict[str, Any]] = None,
    eval_date: Optional[Any] = None,
    injections_enabled: Optional[bool] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Build quality inspection log and NCR log up to eval_date.
    
    Inspections:
    - reinforcement_check at start date of FTG, PLB, every COL_*, and SLAB_*
    - cube_test 7 calendar days after finish date of FTG, PLB, every COL_*, and SLAB_*
    - slab_level_check at finish date of every SLAB_*
    - brickwork_plumb at finish date of every BW_*
    
    Injections (if enabled):
    - SLAB_F1 cube_test fails -> NCR closed after 9 days
    - COL_F2 reinforcement_check fails -> NCR closed after 20 days
    - SLAB_F3 slab_level_check fails -> NCR still open
    """
    if activities is None:
        activities = load_activities()
    if config is None:
        config = load_config()

    if eval_date is None:
        eval_date = config["calendar"]["data_date"]
    elif isinstance(eval_date, str):
        eval_date = date.fromisoformat(eval_date)

    start_date = config["calendar"]["start_date"]
    act_dates = get_actual_dates(sim, activities, start_date)
    injections_on = is_injections_enabled(sim, injections_enabled)

    # Define inspection candidates
    rebar_acts = ["FTG", "PLB"] + [r["id"] for _, r in activities.iterrows() if r["id"].startswith("COL_") or r["id"].startswith("SLAB_")]
    cube_acts = list(rebar_acts)
    slab_acts = [r["id"] for _, r in activities.iterrows() if r["id"].startswith("SLAB_")]
    bw_acts = [r["id"] for _, r in activities.iterrows() if r["id"].startswith("BW_")]

    candidates: List[Dict[str, Any]] = []

    # 1. Reinforcement checks
    for aid in rebar_acts:
        if aid in act_dates:
            dt = act_dates[aid]["start_date"]
            candidates.append({
                "activity_id": aid,
                "check_type": "reinforcement_check",
                "inspection_date": dt,
            })

    # 2. Cube tests (finish + 7 days)
    for aid in cube_acts:
        if aid in act_dates:
            f_dt = act_dates[aid]["finish_date"]
            dt = f_dt + timedelta(days=7)
            candidates.append({
                "activity_id": aid,
                "check_type": "cube_test",
                "inspection_date": dt,
            })

    # 3. Slab level checks
    for aid in slab_acts:
        if aid in act_dates:
            dt = act_dates[aid]["finish_date"]
            candidates.append({
                "activity_id": aid,
                "check_type": "slab_level_check",
                "inspection_date": dt,
            })

    # 4. Brickwork plumb checks
    for aid in bw_acts:
        if aid in act_dates:
            dt = act_dates[aid]["finish_date"]
            candidates.append({
                "activity_id": aid,
                "check_type": "brickwork_plumb",
                "inspection_date": dt,
            })

    # Sort candidates by inspection_date then activity_id
    candidates.sort(key=lambda x: (x["inspection_date"], x["activity_id"], x["check_type"]))

    # Filter to inspections dated on or before eval_date
    inspections = []
    ncrs = []
    ncr_counter = 1
    insp_counter = 1

    for cand in candidates:
        dt = cand["inspection_date"]
        if dt > eval_date:
            continue

        aid = cand["activity_id"]
        chk = cand["check_type"]
        insp_id = f"QC-{insp_counter:03d}"
        insp_counter += 1

        is_fail = False
        fail_desc = ""
        closure_days: Optional[int] = None

        if injections_on:
            qc_fail_cfg = config.get("injections", {}).get("qc_failures", [])
            for qcf in qc_fail_cfg:
                if qcf.get("activity") == aid and qcf.get("test") == chk:
                    is_fail = True
                    fail_desc = qcf.get("detail", qcf.get("why", "Quality check non-conformance"))
                    closure_days = qcf.get("ncr_closed_days")
                    break

        result = "Fail" if is_fail else "Pass"
        ncr_id = f"NCR-{ncr_counter:03d}" if is_fail else ""

        inspections.append({
            "inspection_id": insp_id,
            "activity_id": aid,
            "check_type": chk,
            "inspection_date": dt,
            "result": result,
            "ncr_id": ncr_id,
        })

        if is_fail:
            ncr_counter += 1
            raised_dt = dt
            closed_dt = (raised_dt + timedelta(days=closure_days)) if closure_days is not None else None

            if closed_dt is not None and closed_dt <= eval_date:
                st = "Closed"
                d_open = (closed_dt - raised_dt).days
            else:
                st = "Open"
                d_open = (eval_date - raised_dt).days

            ncrs.append({
                "ncr_id": ncr_id,
                "inspection_id": insp_id,
                "activity_id": aid,
                "check_type": chk,
                "raised_date": raised_dt,
                "closed_date": closed_dt,
                "status": st,
                "days_open": d_open,
                "description": fail_desc,
            })

    return pd.DataFrame(inspections), pd.DataFrame(ncrs)


def ncr_log_at(
    eval_date: Any,
    sim: Any,
    activities: Optional[pd.DataFrame] = None,
    config: Optional[Dict[str, Any]] = None,
    injections_enabled: Optional[bool] = None,
) -> pd.DataFrame:
    """Return NCR log evaluated at eval_date."""
    _, ncrs_df = build_inspections(sim, activities, config, eval_date, injections_enabled)
    return ncrs_df


def quality_summary(
    eval_date: Any,
    sim: Any,
    activities: Optional[pd.DataFrame] = None,
    config: Optional[Dict[str, Any]] = None,
    injections_enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """Compute summary quality metrics up to eval_date."""
    inspections_df, ncrs_df = build_inspections(sim, activities, config, eval_date, injections_enabled)
    total_insp = len(inspections_df)
    passes = int((inspections_df["result"] == "Pass").sum()) if total_insp > 0 else 0
    failures = total_insp - passes
    pass_rate = float(passes) / float(total_insp) if total_insp > 0 else 1.0

    open_ncrs = int((ncrs_df["status"] == "Open").sum()) if not ncrs_df.empty else 0
    closed_ncrs = ncrs_df[ncrs_df["status"] == "Closed"] if not ncrs_df.empty else pd.DataFrame()
    avg_closure_days = float(closed_ncrs["days_open"].mean()) if not closed_ncrs.empty else 0.0

    return {
        "eval_date": str(eval_date),
        "total_inspections": total_insp,
        "passes": passes,
        "failures": failures,
        "pass_rate": round(pass_rate, 4),
        "open_ncrs": open_ncrs,
        "closed_ncrs": len(closed_ncrs),
        "average_closure_days": round(avg_closure_days, 1),
    }
