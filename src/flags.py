"""Project health warning flags, threshold triggers, and action protocols."""

from datetime import date
import calendar
from typing import Dict, Any, List, Optional
import pandas as pd

from src.data_io import load_config, load_activities, load_boq, load_coefficients
from src.schedule import compute_cpm, forecast_cpm
from src.budget import month_end_wd, activity_budgets, monthly_pv, activity_item_budget
from src.evm import monthly_evm, activity_evm, item_cost_variance
from src.materials import material_status
from src.payments import bills_at, generate_bills
from src.quality import build_inspections


CATEGORY_PRIORITY = {
    "milestone_slip": 1,
    "spi": 2,
    "cpi": 3,
    "critical_behind": 4,
    "material_shortfall": 5,
    "ncr_ageing": 6,
    "payment": 7,
    "item_cost": 8,
    "activity_cost": 9,
}

RULES_TEXT = {
    "milestone_slip": {
        "owner": "Project Manager",
        "action": "Expedite shuttering material; add a second shuttering set and gang to recover float on the remaining slabs",
    },
    "critical_behind_slower": {
        "owner": "Site Engineer",
        "action": "Find the constraint (here: shuttering material) and add resources to this activity",
    },
    "critical_behind_late": {
        "owner": "Site Engineer",
        "action": "Re-plan the look-ahead; protect the remaining float; no extra crew unless the handover date must be held",
    },
    "spi": {
        "owner": "Planning Engineer",
        "action": "Perform schedule variance root cause analysis and issue schedule recovery plan",
    },
    "cpi": {
        "owner": "Cost Engineer",
        "action": "Review cost breakdown, material consumption, and investigate subcontractor overruns",
    },
    "activity_cost": {
        "owner": "Billing Engineer",
        "action": "Audit activity quantity measurements and rate adjustments against BOQ baseline",
    },
    "item_cost": {
        "owner": "Procurement Manager",
        "action": "Escalate steel price variation to PM; check the price-variation clause and lock rates for remaining steel",
    },
    "material_shortfall": {
        "owner": "Materials Manager",
        "action": "Issue emergency purchase order to cover material deficit and avoid site work stoppages",
    },
    "ncr_ageing": {
        "owner": "QA/QC Manager",
        "action": "Convene joint site inspection with contractor and structural consultant to approve rectification",
    },
    "payment": {
        "owner": "Commercial Manager",
        "action": "Expedite NCR rectification and client sign-off to release payment certificate",
    },
}


def evaluate_flags(
    month: int,
    sim: Any,
    config: Optional[Dict[str, Any]] = None,
    activities: Optional[pd.DataFrame] = None,
    boq: Optional[pd.DataFrame] = None,
    coeffs: Optional[pd.DataFrame] = None,
    injections_enabled: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Evaluate all project control warning flags for a given month (1..6).
    
    Returns sorted list of flag dicts (red before amber, then by magnitude descending).
    Categories use exact rule names: milestone_slip, critical_behind, spi, cpi,
    activity_cost, item_cost, material_shortfall, ncr_ageing, payment.
    """
    if config is None:
        config = load_config()
    if activities is None:
        activities = load_activities()
    if boq is None:
        boq = load_boq()
    if coeffs is None:
        coeffs = load_coefficients()

    start_date = config["calendar"]["start_date"]
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    year = start_date.year

    last_day = calendar.monthrange(year, month)[1]
    month_start_date = date(year, month, 1)
    month_end_date = date(year, month, last_day)

    cutoff_wd = month_end_wd(month, start_date)

    thresh = config.get("thresholds", {})
    ms_slip_limit = thresh.get("milestone_slip_days", 5)
    spi_amber = thresh.get("spi_amber", 0.95)
    spi_red = thresh.get("spi_red", 0.90)
    cpi_amber = thresh.get("cpi_amber", 0.95)
    cpi_red = thresh.get("cpi_red", 0.90)
    act_cv_thresh = thresh.get("activity_cost_variance_pct", 5)
    ncr_limit = thresh.get("ncr_open_days", 14)
    bill_pending_limit = thresh.get("bill_pending_days", 30)

    b_cpm = compute_cpm(activities).set_index("id")
    status_m = sim.status_at(month)
    f_cpm = forecast_cpm(activities, status_m, cutoff_wd).set_index("id")

    # Actual schedule to evaluate actual start dates and durations
    actual_acts = activities.copy()
    actual_acts["duration_days"] = [sim.actual_durations[aid] for aid in actual_acts["id"]]
    a_cpm = compute_cpm(actual_acts).set_index("id")

    type_map = activities.set_index("id")["type"].to_dict()

    flags: List[Dict[str, Any]] = []

    # 1. milestone_slip: for every milestone not yet achieved, forecast date vs baseline
    # > 5 wd -> amber; >= 10 wd -> red
    structure_done = (f_cpm.loc["M_STRUCTURE", "ef"] <= cutoff_wd) or (status_m.get("M_STRUCTURE", {}).get("state") == "done")
    if structure_done:
        ms_action = "Recover on finishes: overlap plaster and flooring floor by floor or add a finishing crew; agree a revised handover date with the Regional Project Head"
    else:
        ms_action = "Expedite shuttering material; add a second shuttering set and gang to recover float on the remaining slabs"

    milestones = activities[activities["type"] == "milestone"]["id"].tolist()
    for ms in milestones:
        f_ef = int(f_cpm.loc[ms, "ef"])
        b_ef = int(b_cpm.loc[ms, "ef"])
        slip = f_ef - b_ef
        is_achieved = (status_m.get(ms, {}).get("state") == "done") or (f_ef <= cutoff_wd)

        if not is_achieved and slip > 5:
            severity = "red" if slip >= 10 else "amber"
            flags.append({
                "month": month,
                "category": "milestone_slip",
                "severity": severity,
                "what": f"Milestone forecast delay of {slip} working days",
                "where": ms,
                "magnitude": f"{slip} wd",
                "magnitude_num": float(slip),
                "reason": "",
                "since": f"Month {month}",
                "owner": RULES_TEXT["milestone_slip"]["owner"],
                "action": ms_action,
            })

    # 2. critical_behind: baseline-critical WORK activities only whose actual % complete is > 5 pts below baseline
    # Exclude curing and milestone types
    # Reason: "started late by N wd (knock-on)" vs "progressing slower than planned"
    for aid, row in b_cpm.iterrows():
        if not bool(row["is_critical"]):
            continue
        if type_map.get(aid) != "work":
            continue

        planned_dur = int(row["duration_days"])
        if planned_dur <= 0:
            continue
        b_es = int(row["es"])
        b_ef = int(row["ef"])

        if cutoff_wd <= b_es:
            b_pct = 0.0
        elif cutoff_wd >= b_ef:
            b_pct = 1.0
        else:
            b_pct = float(cutoff_wd - b_es) / float(planned_dur)

        a_pct = float(sim.pct_complete.loc[aid, month])
        diff_pts = (b_pct - a_pct) * 100.0

        if diff_pts > 5.0:
            severity = "red" if diff_pts > 50.0 else "amber"
            a_es = int(a_cpm.loc[aid, "es"])
            actual_dur = int(sim.actual_durations[aid])
            start_delay = a_es - b_es

            if start_delay > 0 and actual_dur == planned_dur:
                reason = f"started late by {start_delay} wd (knock-on)"
                action = RULES_TEXT["critical_behind_late"]["action"]
                owner = RULES_TEXT["critical_behind_late"]["owner"]
            else:
                reason = "progressing slower than planned"
                action = RULES_TEXT["critical_behind_slower"]["action"]
                owner = RULES_TEXT["critical_behind_slower"]["owner"]

            flags.append({
                "month": month,
                "category": "critical_behind",
                "severity": severity,
                "what": f"Critical activity {aid} is {diff_pts:.1f}% behind baseline progress",
                "where": aid,
                "magnitude": f"{diff_pts:.1f}%",
                "magnitude_num": diff_pts,
                "reason": reason,
                "since": f"Month {month}",
                "owner": owner,
                "action": action,
            })

    # 3. spi / cpi: project level (< 0.95 amber, < 0.90 red)
    act_b = activity_budgets(activities, boq)
    bac_val = int(act_b["budget_inr"].sum())
    cpm_dates = b_cpm.reset_index()
    pv_df = monthly_pv(cpm_dates, act_b, start_date)
    evm_df = monthly_evm(pv_df, sim, act_b, bac_val, months=range(1, month + 1))
    m_evm = evm_df.loc[evm_df["month"] == month].iloc[0]

    spi_val = m_evm["spi"]
    if spi_val is not None and spi_val < spi_amber:
        severity = "red" if spi_val < spi_red else "amber"
        mag_pts = (1.0 - spi_val) * 100.0
        flags.append({
            "month": month,
            "category": "spi",
            "severity": severity,
            "what": f"Project SPI ({spi_val:.3f}) below {spi_amber} threshold",
            "where": "Project",
            "magnitude": f"{spi_val:.3f}",
            "magnitude_num": mag_pts,
            "reason": "",
            "since": f"Month {month}",
            "owner": RULES_TEXT["spi"]["owner"],
            "action": RULES_TEXT["spi"]["action"],
        })

    cpi_val = m_evm["cpi"]
    if cpi_val is not None and cpi_val < cpi_amber:
        severity = "red" if cpi_val < cpi_red else "amber"
        mag_pts = (1.0 - cpi_val) * 100.0
        flags.append({
            "month": month,
            "category": "cpi",
            "severity": severity,
            "what": f"Project CPI ({cpi_val:.3f}) below {cpi_amber} threshold",
            "where": "Project",
            "magnitude": f"{cpi_val:.3f}",
            "magnitude_num": mag_pts,
            "reason": "",
            "since": f"Month {month}",
            "owner": RULES_TEXT["cpi"]["owner"],
            "action": RULES_TEXT["cpi"]["action"],
        })

    # 4. activity_cost: activity cost variance beyond +/- threshold -> amber
    pv_by_act: Dict[str, float] = {}
    for aid, row in b_cpm.iterrows():
        b_val = float(act_b.loc[act_b["id"] == aid, "budget_inr"].iloc[0])
        dur = int(row["duration_days"])
        if dur <= 0 or b_val <= 0:
            continue
        es = int(row["es"])
        ef = int(row["ef"])
        if cutoff_wd <= es:
            days_done = 0
        elif cutoff_wd >= ef:
            days_done = dur
        else:
            days_done = cutoff_wd - es
        pv_by_act[aid] = (b_val / dur) * days_done

    act_evm_df = activity_evm(sim, act_b, pv_by_act, month)
    for _, a_row in act_evm_df.iterrows():
        cv_pct = a_row["cost_variance_pct"]
        if cv_pct is not None and abs(cv_pct) > act_cv_thresh:
            aid = a_row["id"]
            flags.append({
                "month": month,
                "category": "activity_cost",
                "severity": "amber",
                "what": f"Activity cost variance of {cv_pct:+.1f}% exceeds {act_cv_thresh}% threshold",
                "where": aid,
                "magnitude": f"{cv_pct:+.1f}%",
                "magnitude_num": abs(cv_pct),
                "reason": "",
                "since": f"Month {month}",
                "owner": RULES_TEXT["activity_cost"]["owner"],
                "action": RULES_TEXT["activity_cost"]["action"],
            })

    # 5. item_cost: BOQ item variance > 5% -> amber; > 15% -> red
    it_b = activity_item_budget(activities, boq)
    iv_df = item_cost_variance(sim, it_b, month)
    for _, iv_row in iv_df.iterrows():
        var_pct = iv_row["variance_pct"]
        item_key = iv_row["item"]
        if var_pct is not None and var_pct > 5.0:
            severity = "red" if var_pct > 15.0 else "amber"
            action_text = (
                "Escalate steel price variation to PM; check the price-variation clause and lock rates for remaining steel"
                if item_key == "STEEL"
                else RULES_TEXT["item_cost"]["action"]
            )
            flags.append({
                "month": month,
                "category": "item_cost",
                "severity": severity,
                "what": f"BOQ item {item_key} cost variance of {var_pct:+.1f}% exceeds threshold",
                "where": item_key,
                "magnitude": f"{var_pct:+.1f}%",
                "magnitude_num": var_pct,
                "reason": "",
                "since": f"Month {month}",
                "owner": RULES_TEXT["item_cost"]["owner"],
                "action": action_text,
            })

    # 6. material_shortfall: procured this month < required next month
    # Shortfall <= 20% -> amber, > 20% -> red
    mat_stat = material_status(month, sim, config, activities, boq, coeffs, injections_enabled)
    for _, m_row in mat_stat.iterrows():
        sf = float(m_row["shortfall"])
        req = float(m_row["required_next_month"])
        mat_name = m_row["material"]
        if sf > 0.0 and req > 0.0:
            sf_pct = (sf / req) * 100.0
            severity = "amber" if sf_pct <= 20.0 else "red"
            flags.append({
                "month": month,
                "category": "material_shortfall",
                "severity": severity,
                "what": f"Material shortfall of {sf:.1f} units ({sf_pct:.1f}%) for {mat_name}",
                "where": mat_name,
                "magnitude": f"{sf_pct:.1f}%",
                "magnitude_num": sf_pct,
                "reason": "",
                "since": f"Month {month}",
                "owner": RULES_TEXT["material_shortfall"]["owner"],
                "action": f"Issue emergency purchase order for {mat_name} to cover {sf:.1f} unit deficit",
            })

    # 7. ncr_ageing: any NCR open at some point during the month whose days open > ncr_limit
    # amber if closed by month end, red if still open
    _, ncrs_df = build_inspections(sim, activities, config, eval_date=month_end_date, injections_enabled=injections_enabled)
    for _, n_row in ncrs_df.iterrows():
        raised_dt = n_row["raised_date"]
        closed_dt = n_row["closed_date"]

        was_open_in_month = (raised_dt <= month_end_date) and (closed_dt is None or closed_dt >= month_start_date)
        if not was_open_in_month:
            continue

        if closed_dt is not None and closed_dt <= month_end_date:
            days_open = (closed_dt - raised_dt).days
            if days_open > ncr_limit:
                flags.append({
                    "month": month,
                    "category": "ncr_ageing",
                    "severity": "amber",
                    "what": f"NCR {n_row['ncr_id']} exceeded {ncr_limit}-day limit before resolution ({days_open} days)",
                    "where": n_row["ncr_id"],
                    "magnitude": f"{days_open} days",
                    "magnitude_num": float(days_open),
                    "reason": "",
                    "since": str(raised_dt),
                    "owner": RULES_TEXT["ncr_ageing"]["owner"],
                    "action": RULES_TEXT["ncr_ageing"]["action"],
                })
        else:
            days_open = (month_end_date - raised_dt).days
            if days_open > ncr_limit:
                flags.append({
                    "month": month,
                    "category": "ncr_ageing",
                    "severity": "red",
                    "what": f"NCR {n_row['ncr_id']} unresolved for {days_open} days (>{ncr_limit} day limit)",
                    "where": n_row["ncr_id"],
                    "magnitude": f"{days_open} days",
                    "magnitude_num": float(days_open),
                    "reason": "",
                    "since": str(raised_dt),
                    "owner": RULES_TEXT["ncr_ageing"]["owner"],
                    "action": RULES_TEXT["ncr_ageing"]["action"],
                })

    # 8. payment: Held bill -> red; Pending with days_pending > 30 -> amber;
    # a bill paid during the month more than 30 days after submission -> amber ("paid late")
    b_at_date = bills_at(month_end_date, sim, config, boq, injections_enabled)
    for _, b_row in b_at_date.iterrows():
        b_no = b_row["bill_no"]
        b_st = b_row["status"]
        d_pend = int(b_row["days_pending"])

        if b_st == "Held" and month >= 6:
            hr = str(b_row.get("hold_reason", ""))
            if hr.startswith("Held: "):
                hr = hr[6:]
            flags.append({
                "month": month,
                "category": "payment",
                "severity": "red",
                "what": f"RA bill {b_no} is held: {hr}",
                "where": b_no,
                "magnitude": f"{d_pend} days",
                "magnitude_num": float(d_pend),
                "reason": "",
                "since": str(b_row["submitted_date"]),
                "owner": RULES_TEXT["payment"]["owner"],
                "action": RULES_TEXT["payment"]["action"],
            })
        elif b_st == "Pending" and d_pend > 30:
            flags.append({
                "month": month,
                "category": "payment",
                "severity": "amber",
                "what": f"RA bill {b_no} pending certification/payment for {d_pend} days",
                "where": b_no,
                "magnitude": f"{d_pend} days",
                "magnitude_num": float(d_pend),
                "reason": "",
                "since": str(b_row["submitted_date"]),
                "owner": RULES_TEXT["payment"]["owner"],
                "action": "Follow up with client accounts department for payment release",
            })

    gen_bills = generate_bills(sim, config, boq, injections_enabled)
    for _, b_row in gen_bills.iterrows():
        p_dt = b_row["paid_date"]
        if p_dt is not None and month_start_date <= p_dt <= month_end_date:
            d_pay = (p_dt - b_row["submitted_date"]).days
            if d_pay > 30:
                b_no = b_row["bill_no"]
                flags.append({
                    "month": month,
                    "category": "payment",
                    "severity": "amber",
                    "what": f"RA bill {b_no} paid late ({d_pay} days after submission)",
                    "where": b_no,
                    "magnitude": f"{d_pay} days",
                    "magnitude_num": float(d_pay),
                    "reason": "",
                    "since": str(p_dt),
                    "owner": RULES_TEXT["payment"]["owner"],
                    "action": "Review payment turnaround with finance and client project management",
                })

    # Sort full flags list: red before amber, then by magnitude descending
    flags.sort(key=lambda f: (0 if f["severity"] == "red" else 1, -f["magnitude_num"]))

    # Assign sequential flag_id
    for i, f in enumerate(flags, start=1):
        f["flag_id"] = f"FLAG-{month:02d}-{i:02d}"

    return flags


def get_top_issues(flags: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    """Rank top project issues by fixed category priority.
    
    Category priority:
    1. milestone_slip (M_HANDOVER only, with cascade text)
    2. spi
    3. cpi
    4. critical_behind
    5. material_shortfall
    6. ncr_ageing
    7. payment
    8. item_cost
    9. activity_cost
    
    Rules:
    - Reds before ambers
    - At most one issue per category
    - Magnitude breaks ties within category
    """
    # Determine other unachieved milestones that slip in this flags list
    other_slipped_ms = [
        f["where"] for f in flags if f.get("category") == "milestone_slip" and f.get("where") != "M_HANDOVER"
    ]
    cascade_note = f" (also moves {' / '.join(other_slipped_ms)})" if other_slipped_ms else ""

    candidates = []
    for f in flags:
        cat = f["category"]
        if cat == "milestone_slip":
            if f["where"] != "M_HANDOVER":
                continue
            f_copy = dict(f)
            f_copy["what"] = f"{f['what']}{cascade_note}"
            candidates.append(f_copy)
        else:
            candidates.append(dict(f))

    # Sort: red before amber, then category priority, then magnitude descending
    candidates.sort(
        key=lambda f: (
            0 if f["severity"] == "red" else 1,
            CATEGORY_PRIORITY.get(f["category"], 99),
            -f["magnitude_num"],
        )
    )

    seen_categories = set()
    top_issues: List[Dict[str, Any]] = []

    for cand in candidates:
        cat = cand["category"]
        if cat not in seen_categories:
            top_issues.append(cand)
            seen_categories.add(cat)
            if len(top_issues) == limit:
                break

    return top_issues
