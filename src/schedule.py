"""Critical Path Method (CPM) scheduling, calendar date mappings, and forecast engine."""

from datetime import date, timedelta
from typing import Any, Dict, List, Union
import pandas as pd


class ScheduleError(ValueError):
    """Base class for schedule network errors."""
    pass


class CycleError(ScheduleError):
    """Raised when a cycle is detected in the activity dependency graph."""
    pass


class MissingPredecessorError(ScheduleError):
    """Raised when an activity lists a predecessor that does not exist."""
    pass


def _pred_list(preds: Any) -> List[str]:
    """Parse predecessors input (list, string, or None/NaN) into a clean list of IDs."""
    if preds is None or (isinstance(preds, float) and pd.isna(preds)):
        return []
    if isinstance(preds, (list, tuple)):
        return [str(p).strip() for p in preds if str(p).strip()]
    if isinstance(preds, str):
        return [p.strip() for p in preds.split(";") if p.strip()]
    return []


def topological_order(activities: pd.DataFrame) -> List[str]:
    """Sort activities in topological order using Kahn's algorithm.

    Raises:
        MissingPredecessorError: If any predecessor ID is missing from activities.
        CycleError: If a dependency cycle is detected.
    """
    all_ids = set(activities["id"])

    # Validate that all referenced predecessors exist
    for _, row in activities.iterrows():
        act_id = row["id"]
        preds = _pred_list(row["predecessors"])
        for p in preds:
            if p not in all_ids:
                raise MissingPredecessorError(
                    f"Activity '{act_id}' lists predecessor '{p}', which does not exist"
                )

    # Build adjacency lists and compute in-degrees
    # In-degree counts the number of unfinished predecessors for each activity
    in_degree: Dict[str, int] = {row["id"]: 0 for _, row in activities.iterrows()}
    successors: Dict[str, List[str]] = {row["id"]: [] for _, row in activities.iterrows()}

    for _, row in activities.iterrows():
        act_id = row["id"]
        preds = _pred_list(row["predecessors"])
        in_degree[act_id] = len(preds)
        for p in preds:
            successors[p].append(act_id)

    # Initialize queue with activities having zero predecessors (in-degree 0)
    queue: List[str] = [act_id for act_id, deg in in_degree.items() if deg == 0]
    order: List[str] = []

    # Process activities level by level
    while queue:
        curr = queue.pop(0)
        order.append(curr)
        for succ in successors[curr]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # If not all activities are processed, a cycle exists
    if len(order) < len(activities):
        cycle_candidates = [act_id for act_id, deg in in_degree.items() if deg > 0]
        raise CycleError(f"Cycle detected among: {', '.join(cycle_candidates)}")

    return order


def compute_cpm(activities: pd.DataFrame) -> pd.DataFrame:
    """Compute early/late starts, finishes, total float, and critical path.

    Returns DataFrame with columns:
    id, duration_days, es, ef, ls, lf, total_float, is_critical
    """
    order = topological_order(activities)

    # Build activity data dictionary
    act_data: Dict[str, Dict[str, Any]] = {}
    for _, row in activities.iterrows():
        preds = _pred_list(row["predecessors"])
        act_data[row["id"]] = {
            "duration": int(row["duration_days"]),
            "predecessors": preds,
            "successors": [],
        }

    for act_id, data in act_data.items():
        for p in data["predecessors"]:
            act_data[p]["successors"].append(act_id)

    # 1. Forward pass
    # Formula: ES = max(EF of predecessors), 0 if no predecessors
    # Formula: EF = ES + duration
    es: Dict[str, int] = {}
    ef: Dict[str, int] = {}
    for act_id in order:
        p_list = act_data[act_id]["predecessors"]
        if not p_list:
            es[act_id] = 0
        else:
            es[act_id] = max(ef[p] for p in p_list)
        ef[act_id] = es[act_id] + act_data[act_id]["duration"]

    # Project duration = maximum EF across all activities
    project_end = max(ef.values()) if ef else 0

    # 2. Backward pass
    # Formula: LF = min(LS of successors), project_end if no successors
    # Formula: LS = LF - duration
    lf: Dict[str, int] = {}
    ls: Dict[str, int] = {}
    for act_id in reversed(order):
        s_list = act_data[act_id]["successors"]
        if not s_list:
            lf[act_id] = project_end
        else:
            lf[act_id] = min(ls[s] for s in s_list)
        ls[act_id] = lf[act_id] - act_data[act_id]["duration"]

    # 3. Float and critical path
    # Formula: Total Float TF = LS - ES = LF - EF
    # Formula: is_critical = (TF == 0)
    rows = []
    for act_id in order:
        dur = act_data[act_id]["duration"]
        tf = ls[act_id] - es[act_id]
        is_crit = (tf == 0)
        rows.append({
            "id": act_id,
            "duration_days": dur,
            "es": es[act_id],
            "ef": ef[act_id],
            "ls": ls[act_id],
            "lf": lf[act_id],
            "total_float": tf,
            "is_critical": is_crit,
        })

    return pd.DataFrame(rows)


def critical_path(cpm_df: pd.DataFrame) -> List[str]:
    """Return critical activity IDs in topological order."""
    return list(cpm_df[cpm_df["is_critical"]]["id"])


def wd_to_date(n: int, start_date: Union[str, date]) -> date:
    """Convert working-day index (0-based) to calendar date, skipping Sundays.

    Mon-Sat calendar: 6 working days per 7-day calendar week.
    n = 0 corresponds to start_date.
    """
    n = int(n)
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if n < 0:
        raise ValueError(f"Working day index n must be non-negative, got {n}")

    # If start_date falls on Sunday, advance to Monday
    curr = start_date
    if curr.weekday() == 6:
        curr += timedelta(days=1)

    # 6 working days = 1 full week (7 calendar days)
    weeks = int(n // 6)
    remainder_days = int(n % 6)

    curr += timedelta(days=int(weeks * 7))

    # Advance remaining working days skipping Sunday (weekday 6)
    added = 0
    while added < remainder_days:
        curr += timedelta(days=1)
        if curr.weekday() != 6:
            added += 1

    return curr


def date_to_wd(d: Union[str, date], start_date: Union[str, date]) -> int:
    """Convert calendar date to working-day index (0-based) relative to start_date, skipping Sundays."""
    if isinstance(d, str):
        d = date.fromisoformat(d)
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if d < start_date:
        raise ValueError(f"Date {d} is before start_date {start_date}")

    total_calendar_days = (d - start_date).days
    weeks = total_calendar_days // 7

    # 6 working days per full calendar week
    wd = weeks * 6

    # Iterate through days in partial week
    curr = start_date + timedelta(days=weeks * 7)
    while curr < d:
        if curr.weekday() != 6:
            wd += 1
        curr += timedelta(days=1)

    return wd


def add_dates(cpm_df: pd.DataFrame, start_date: Union[str, date]) -> pd.DataFrame:
    """Add calendar start_date and finish_date to CPM DataFrame based on working days."""
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)

    start_dates = []
    finish_dates = []

    for _, row in cpm_df.iterrows():
        es_val = int(row["es"])
        ef_val = int(row["ef"])
        dur = int(row["duration_days"])

        if dur > 0:
            # Start on the first working day; finish on the day work completes
            # Formula: start = wd_to_date(ES), finish = wd_to_date(EF - 1)
            s_date = wd_to_date(es_val, start_date)
            f_date = wd_to_date(ef_val - 1, start_date)
        else:
            # Milestone: instantaneous point in time
            # Formula: milestone date = wd_to_date(EF - 1) if EF > 0 else start_date
            if ef_val > 0:
                m_date = wd_to_date(ef_val - 1, start_date)
            else:
                m_date = start_date
            s_date = m_date
            f_date = m_date

        start_dates.append(s_date)
        finish_dates.append(f_date)

    out_df = cpm_df.copy()
    out_df["start_date"] = start_dates
    out_df["finish_date"] = finish_dates
    return out_df


def forecast_cpm(
    activities: pd.DataFrame,
    status: Dict[str, Dict[str, Any]],
    data_date_wd: int,
) -> pd.DataFrame:
    """Compute forecasted CPM schedule given actual activity progress at data date.

    Status dict maps activity id -> dict with keys:
    - state: "done", "in_progress", or "not_started"
    - actual_start: int working day
    - actual_finish: int working day (if done)
    - remaining_days: int working days (if in_progress)
    """
    order = topological_order(activities)

    act_data: Dict[str, Dict[str, Any]] = {}
    for _, row in activities.iterrows():
        preds = _pred_list(row["predecessors"])
        act_data[row["id"]] = {
            "duration": int(row["duration_days"]),
            "predecessors": preds,
            "successors": [],
        }

    for act_id, data in act_data.items():
        for p in data["predecessors"]:
            act_data[p]["successors"].append(act_id)

    # 1. Forward pass with progress state
    es: Dict[str, int] = {}
    ef: Dict[str, int] = {}
    dur_eff: Dict[str, int] = {}

    for act_id in order:
        st = status.get(act_id, {"state": "not_started"})
        state = st.get("state", "not_started")

        if state == "done":
            # Done: ES = actual_start, EF = actual_finish
            es[act_id] = int(st["actual_start"])
            ef[act_id] = int(st["actual_finish"])
            dur_eff[act_id] = ef[act_id] - es[act_id]
        elif state == "in_progress":
            # In progress: ES = actual_start, EF = data_date_wd + remaining_days
            es[act_id] = int(st["actual_start"])
            rem = int(st.get("remaining_days", 0))
            ef[act_id] = data_date_wd + rem
            dur_eff[act_id] = ef[act_id] - es[act_id]
        else:
            # Not started: ES = max(data_date_wd, max EF of predecessors)
            # Formula: EF = ES + duration
            p_list = act_data[act_id]["predecessors"]
            if not p_list:
                pred_ef = data_date_wd
            else:
                pred_ef = max(ef[p] for p in p_list)
            es[act_id] = max(data_date_wd, pred_ef)
            dur = act_data[act_id]["duration"]
            ef[act_id] = es[act_id] + dur
            dur_eff[act_id] = dur

    project_end = max(ef.values()) if ef else 0

    # 2. Backward pass
    # Formula: LF = min(LS of successors), project_end if no successors
    # Formula: LS = LF - effective duration
    lf: Dict[str, int] = {}
    ls: Dict[str, int] = {}
    for act_id in reversed(order):
        s_list = act_data[act_id]["successors"]
        if not s_list:
            lf[act_id] = project_end
        else:
            lf[act_id] = min(ls[s] for s in s_list)
        ls[act_id] = lf[act_id] - dur_eff[act_id]

    rows = []
    for act_id in order:
        dur = act_data[act_id]["duration"]
        # Formula: Total Float = LF - EF
        # Note: Total float for completed activities (state == 'done') is not meaningful as they are history.
        tf = lf[act_id] - ef[act_id]
        is_crit = (tf == 0)
        rows.append({
            "id": act_id,
            "duration_days": dur,
            "es": es[act_id],
            "ef": ef[act_id],
            "ls": ls[act_id],
            "lf": lf[act_id],
            "total_float": tf,
            "is_critical": is_crit,
        })

    return pd.DataFrame(rows)
