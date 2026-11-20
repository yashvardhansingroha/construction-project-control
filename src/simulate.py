"""Monthly progress and actual cost simulation engine with injected project issues."""

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

from src.budget import activity_item_budget, month_end_wd
from src.schedule import compute_cpm, critical_path


@dataclass
class SimResult:
    """Simulation results holding actual schedule, progress, cost, and forecast status."""
    actual_durations: Dict[str, int]
    pct_complete: pd.DataFrame
    ac_monthly: pd.DataFrame
    status_by_month: Dict[int, Dict[str, Dict[str, Any]]]
    injections_applied: List[str]
    noise_by_act: Optional[Dict[str, Dict[str, float]]] = None

    def status_at(self, m: int) -> Dict[str, Dict[str, Any]]:
        """Return activity progress dictionary formatted for forecast_cpm at end of month m."""
        return self.status_by_month[m]


def simulate(
    config: Dict[str, Any],
    activities: pd.DataFrame,
    boq: pd.DataFrame,
    through_month: int = 6,
    injections_enabled: Optional[bool] = None,
) -> SimResult:
    """Simulate monthly actual schedule progress and actual costs with documented issues.

    Noise draws happen first in activities.csv order for all activities to guarantee
    exact random sequence reproducibility whether injections are enabled or disabled.
    """
    seed = int(config.get("seed", 42))
    rng = np.random.default_rng(seed)

    progress_sd = float(config["noise"]["progress_sd"])
    cost_sd = float(config["noise"]["cost_sd"])
    clip_pct = float(config["noise"]["cost_noise_clip_pct"]) / 100.0

    # 1. Noise draws happen first, in activities.csv order, for every activity
    noise_by_act: Dict[str, Dict[str, float]] = {}
    for _, row in activities.iterrows():
        act_id = row["id"]
        d_noise = float(rng.normal(0, progress_sd))
        c_noise = float(rng.normal(0, cost_sd))
        c_noise_clipped = float(np.clip(c_noise, -clip_pct, clip_pct))
        noise_by_act[act_id] = {
            "dur_noise": d_noise,
            "cost_noise": c_noise_clipped,
        }

    # Resolve master injections switch
    if injections_enabled is None:
        injections_enabled = bool(config.get("injections", {}).get("injections_enabled", True))

    injections_cfg = config.get("injections", {})
    slab_delay_cfg = injections_cfg.get("slab_delay", {})
    steel_escalation_cfg = injections_cfg.get("steel_escalation", {})

    apply_slab_delay = injections_enabled and slab_delay_cfg.get("enabled", False)
    apply_steel_escalation = injections_enabled and steel_escalation_cfg.get("enabled", False)

    injections_applied: List[str] = []
    if apply_slab_delay:
        extra_days = int(slab_delay_cfg.get("extra_working_days", 10))
        target_act = slab_delay_cfg.get("activity", "SLAB_F2")
        injections_applied.append(f"slab_delay: +{extra_days} wd on {target_act}")

    if apply_steel_escalation:
        uplift = float(steel_escalation_cfg.get("rate_uplift_pct", 10))
        from_m = int(steel_escalation_cfg.get("from_month", 3))
        injections_applied.append(f"steel_escalation: +{uplift:.0f}% on STEEL from month {from_m}")

    # Determine baseline critical path
    base_cpm = compute_cpm(activities)
    base_crit_ids = set(critical_path(base_cpm))

    # 2. Actual durations
    # Critical activities keep planned duration (no noise).
    # Non-critical work activities: max(1, round(planned * (1 + dur_noise))).
    actual_durations: Dict[str, int] = {}
    for _, row in activities.iterrows():
        act_id = row["id"]
        planned_dur = int(row["duration_days"])
        act_type = row["type"]

        if act_type == "milestone":
            dur = 0
        elif act_id in base_crit_ids:
            dur = planned_dur
        elif act_type == "work":
            # Non-critical work activity gets progress noise
            noise_factor = 1.0 + noise_by_act[act_id]["dur_noise"]
            dur = max(1, int(round(planned_dur * noise_factor)))
        else:
            # Non-critical curing activity (if any) keeps planned
            dur = planned_dur

        if apply_slab_delay and act_id == slab_delay_cfg.get("activity", "SLAB_F2"):
            dur += int(slab_delay_cfg.get("extra_working_days", 10))

        actual_durations[act_id] = dur

    # 3. Actual schedule: run compute_cpm on actual durations
    actual_acts_df = activities.copy()
    actual_acts_df["duration_days"] = [actual_durations[aid] for aid in actual_acts_df["id"]]
    actual_cpm = compute_cpm(actual_acts_df)
    actual_cpm_map = actual_cpm.set_index("id").to_dict(orient="index")

    start_date = config["calendar"]["start_date"]

    # 4. Physical % complete per activity at end of month m (1..through_month)
    # Physical % complete = working days worked by then / actual duration, clipped to [0, 1]
    pct_dict: Dict[str, Dict[int, float]] = {row["id"]: {} for _, row in activities.iterrows()}
    status_by_month: Dict[int, Dict[str, Dict[str, Any]]] = {}

    for m in range(1, through_month + 1):
        cutoff_wd = month_end_wd(m, start_date)
        status_m: Dict[str, Dict[str, Any]] = {}

        for _, row in activities.iterrows():
            act_id = row["id"]
            act_type = row["type"]
            dur = actual_durations[act_id]
            es_val = int(actual_cpm_map[act_id]["es"])
            ef_val = int(actual_cpm_map[act_id]["ef"])

            if act_type == "milestone" or dur == 0:
                pct = 1.0 if cutoff_wd >= ef_val else 0.0
                if cutoff_wd >= ef_val:
                    status_m[act_id] = {"state": "done", "actual_start": es_val, "actual_finish": ef_val}
                else:
                    status_m[act_id] = {"state": "not_started"}
            else:
                if cutoff_wd <= es_val:
                    pct = 0.0
                    status_m[act_id] = {"state": "not_started"}
                elif cutoff_wd >= ef_val:
                    pct = 1.0
                    status_m[act_id] = {"state": "done", "actual_start": es_val, "actual_finish": ef_val}
                else:
                    days_worked = cutoff_wd - es_val
                    pct = min(1.0, max(0.0, float(days_worked) / float(dur)))
                    remaining = max(1, dur - days_worked)
                    status_m[act_id] = {
                        "state": "in_progress",
                        "actual_start": es_val,
                        "remaining_days": remaining,
                    }

            pct_dict[act_id][m] = pct

        status_by_month[m] = status_m

    pct_complete_df = pd.DataFrame.from_dict(pct_dict, orient="index")
    pct_complete_df.index.name = "id"

    # 5. Actual cost calculation
    # Work is paid by quantity placed: Quantity placed in month m = planned qty * (change in % complete)
    # Actual rate = baseline rate * (1 + cost_noise if non-critical else 0) * (1 + 0.10 if STEEL & m>=3 & escalation)
    item_budget_df = activity_item_budget(activities, boq)
    ac_rows: List[Dict[str, Any]] = []

    for m in range(1, through_month + 1):
        for _, item_row in item_budget_df.iterrows():
            act_id = item_row["activity_id"]
            item_key = item_row["item"]
            planned_qty = float(item_row["quantity"])
            base_rate = float(item_row["rate_inr"])

            curr_pct = pct_dict[act_id][m]
            prev_pct = pct_dict[act_id][m - 1] if m > 1 else 0.0
            delta_pct = max(0.0, curr_pct - prev_pct)

            if delta_pct <= 0.0:
                continue

            qty_placed = planned_qty * delta_pct

            # Rate adjustments
            if act_id in base_crit_ids:
                cost_noise = 0.0
            else:
                cost_noise = noise_by_act[act_id]["cost_noise"]

            steel_rate_uplift = 0.0
            if apply_steel_escalation and item_key == "STEEL" and m >= int(steel_escalation_cfg.get("from_month", 3)):
                steel_rate_uplift = float(steel_escalation_cfg.get("rate_uplift_pct", 10)) / 100.0

            actual_rate = base_rate * (1.0 + cost_noise) * (1.0 + steel_rate_uplift)
            amount = qty_placed * actual_rate

            ac_rows.append({
                "activity": act_id,
                "activity_id": act_id,
                "item": item_key,
                "month": m,
                "quantity": qty_placed,
                "rate": actual_rate,
                "amount": amount,
            })

    ac_monthly_df = pd.DataFrame(ac_rows)

    return SimResult(
        actual_durations=actual_durations,
        pct_complete=pct_complete_df,
        ac_monthly=ac_monthly_df,
        status_by_month=status_by_month,
        injections_applied=injections_applied,
        noise_by_act=noise_by_act,
    )
