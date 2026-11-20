"""Unit tests for CPM scheduling, error handling, forecast engine, and calendar conversions."""

from datetime import date
import pandas as pd
import pytest

from src.data_io import load_activities, load_config
from src.schedule import (
    CycleError,
    MissingPredecessorError,
    add_dates,
    compute_cpm,
    critical_path,
    date_to_wd,
    forecast_cpm,
    wd_to_date,
)


def test_textbook_network():
    """Textbook 6-activity CPM network with full hand calculation in comments.

    Network specification:
      A: duration=3, predecessors=[]
      B: duration=4, predecessors=[A]
      C: duration=2, predecessors=[A]
      D: duration=5, predecessors=[B]
      E: duration=3, predecessors=[C]
      F: duration=2, predecessors=[D, E]

    Hand calculation:
    -----------------
    1. Forward Pass (Early Start and Early Finish):
       - A: no predecessors -> ES = 0, EF = 0 + 3 = 3
       - B: pred A -> ES = EF(A) = 3, EF = 3 + 4 = 7
       - C: pred A -> ES = EF(A) = 3, EF = 3 + 2 = 5
       - D: pred B -> ES = EF(B) = 7, EF = 7 + 5 = 12
       - E: pred C -> ES = EF(C) = 5, EF = 5 + 3 = 8
       - F: preds D, E -> ES = max(EF(D), EF(E)) = max(12, 8) = 12, EF = 12 + 2 = 14
       Project Duration = max(EF) = 14

    2. Backward Pass (Late Finish and Late Start):
       - F: no successors -> LF = 14, LS = 14 - 2 = 12
       - D: succ F -> LF = LS(F) = 12, LS = 12 - 5 = 7
       - E: succ F -> LF = LS(F) = 12, LS = 12 - 3 = 9
       - B: succ D -> LF = LS(D) = 7, LS = 7 - 4 = 3
       - C: succ E -> LF = LS(E) = 9, LS = 9 - 2 = 7
       - A: succs B, C -> LF = min(LS(B), LS(C)) = min(3, 7) = 3, LS = 3 - 3 = 0

    3. Total Float (TF = LS - ES = LF - EF):
       - A: TF = 0 - 0 = 0 (Critical)
       - B: TF = 3 - 3 = 0 (Critical)
       - C: TF = 7 - 3 = 4 (Float = 4)
       - D: TF = 7 - 7 = 0 (Critical)
       - E: TF = 9 - 5 = 4 (Float = 4)
       - F: TF = 12 - 12 = 0 (Critical)

    Critical Path: [A, B, D, F]
    """
    df = pd.DataFrame([
        {"id": "A", "duration_days": 3, "predecessors": []},
        {"id": "B", "duration_days": 4, "predecessors": ["A"]},
        {"id": "C", "duration_days": 2, "predecessors": ["A"]},
        {"id": "D", "duration_days": 5, "predecessors": ["B"]},
        {"id": "E", "duration_days": 3, "predecessors": ["C"]},
        {"id": "F", "duration_days": 2, "predecessors": ["D", "E"]},
    ])

    res = compute_cpm(df)
    cpm = res.set_index("id")

    # Assert ES and EF
    assert cpm.loc["A", "es"] == 0 and cpm.loc["A", "ef"] == 3
    assert cpm.loc["B", "es"] == 3 and cpm.loc["B", "ef"] == 7
    assert cpm.loc["C", "es"] == 3 and cpm.loc["C", "ef"] == 5
    assert cpm.loc["D", "es"] == 7 and cpm.loc["D", "ef"] == 12
    assert cpm.loc["E", "es"] == 5 and cpm.loc["E", "ef"] == 8
    assert cpm.loc["F", "es"] == 12 and cpm.loc["F", "ef"] == 14

    # Assert LS and LF
    assert cpm.loc["A", "ls"] == 0 and cpm.loc["A", "lf"] == 3
    assert cpm.loc["B", "ls"] == 3 and cpm.loc["B", "lf"] == 7
    assert cpm.loc["C", "ls"] == 7 and cpm.loc["C", "lf"] == 9
    assert cpm.loc["D", "ls"] == 7 and cpm.loc["D", "lf"] == 12
    assert cpm.loc["E", "ls"] == 9 and cpm.loc["E", "lf"] == 12
    assert cpm.loc["F", "ls"] == 12 and cpm.loc["F", "lf"] == 14

    # Assert Total Float
    assert cpm.loc["A", "total_float"] == 0
    assert cpm.loc["B", "total_float"] == 0
    assert cpm.loc["C", "total_float"] == 4
    assert cpm.loc["D", "total_float"] == 0
    assert cpm.loc["E", "total_float"] == 4
    assert cpm.loc["F", "total_float"] == 0

    # Assert Critical Path and Project Duration
    assert critical_path(res) == ["A", "B", "D", "F"]
    assert res["ef"].max() == 14


def test_schedule_errors_and_milestone():
    """Verify cycle detection, missing predecessor error, and milestone handling."""
    # 1. Cycle detection: A -> B -> C -> A
    cycle_df = pd.DataFrame([
        {"id": "A", "duration_days": 3, "predecessors": ["C"]},
        {"id": "B", "duration_days": 4, "predecessors": ["A"]},
        {"id": "C", "duration_days": 2, "predecessors": ["B"]},
    ])
    with pytest.raises(CycleError) as exc_cycle:
        compute_cpm(cycle_df)
    err_msg = str(exc_cycle.value)
    assert "Cycle detected among:" in err_msg
    assert "A" in err_msg and "B" in err_msg and "C" in err_msg

    # 2. Missing predecessor: Activity B lists 'Z'
    missing_df = pd.DataFrame([
        {"id": "A", "duration_days": 3, "predecessors": []},
        {"id": "B", "duration_days": 4, "predecessors": ["A", "Z"]},
    ])
    with pytest.raises(MissingPredecessorError) as exc_missing:
        compute_cpm(missing_df)
    assert "lists predecessor 'Z', which does not exist" in str(exc_missing.value)

    # 3. Zero-duration milestone G placed after F in textbook network
    milestone_df = pd.DataFrame([
        {"id": "A", "duration_days": 3, "predecessors": []},
        {"id": "B", "duration_days": 4, "predecessors": ["A"]},
        {"id": "C", "duration_days": 2, "predecessors": ["A"]},
        {"id": "D", "duration_days": 5, "predecessors": ["B"]},
        {"id": "E", "duration_days": 3, "predecessors": ["C"]},
        {"id": "F", "duration_days": 2, "predecessors": ["D", "E"]},
        {"id": "G", "duration_days": 0, "predecessors": ["F"]},
    ])
    res_m = compute_cpm(milestone_df).set_index("id")
    assert res_m.loc["G", "es"] == 14
    assert res_m.loc["G", "ef"] == 14
    assert res_m.loc["G", "ls"] == 14
    assert res_m.loc["G", "lf"] == 14
    assert res_m.loc["G", "total_float"] == 0
    assert bool(res_m.loc["G", "is_critical"]) is True


def test_textbook_forecast():
    """Verify CPM forecast on textbook network with status at data_date_wd = 6.

    Hand calculation for forecast:
    ------------------------------
    data_date_wd = 6.
    Given status:
      - A: done, actual_start=0, actual_finish=3 -> ES = 0, EF = 3
      - B: in_progress, actual_start=3, remaining_days=4 -> ES = 3, EF = 6 + 4 = 10
      - C: done, actual_start=3, actual_finish=5 -> ES = 3, EF = 5
      - D: not_started, dur=5, pred B -> ES = max(6, EF(B)=10) = 10, EF = 10 + 5 = 15
      - E: not_started, dur=3, pred C -> ES = max(6, EF(C)=5) = 6, EF = 6 + 3 = 9
      - F: not_started, dur=2, preds D, E -> ES = max(6, max(15, 9)) = 15, EF = 15 + 2 = 17

    Project forecast completion = 17 working days.
    """
    df = pd.DataFrame([
        {"id": "A", "duration_days": 3, "predecessors": []},
        {"id": "B", "duration_days": 4, "predecessors": ["A"]},
        {"id": "C", "duration_days": 2, "predecessors": ["A"]},
        {"id": "D", "duration_days": 5, "predecessors": ["B"]},
        {"id": "E", "duration_days": 3, "predecessors": ["C"]},
        {"id": "F", "duration_days": 2, "predecessors": ["D", "E"]},
    ])

    status = {
        "A": {"state": "done", "actual_start": 0, "actual_finish": 3},
        "B": {"state": "in_progress", "actual_start": 3, "remaining_days": 4},
        "C": {"state": "done", "actual_start": 3, "actual_finish": 5},
        "D": {"state": "not_started"},
        "E": {"state": "not_started"},
        "F": {"state": "not_started"},
    }

    res = forecast_cpm(df, status, data_date_wd=6)
    cpm = res.set_index("id")

    # Assertions required by specification
    assert cpm.loc["B", "ef"] == 10
    assert cpm.loc["D", "es"] == 10 and cpm.loc["D", "ef"] == 15
    assert cpm.loc["E", "es"] == 6 and cpm.loc["E", "ef"] == 9
    assert cpm.loc["F", "es"] == 15 and cpm.loc["F", "ef"] == 17
    assert res["ef"].max() == 17


def test_real_project_cpm():
    """Verify CPM on real project baseline activities, float checks, and injected delay sensitivity."""
    activities = load_activities()
    config = load_config()
    start_date = config["calendar"]["start_date"]

    res = compute_cpm(activities)
    cpm = res.set_index("id")

    # Project duration
    proj_duration = res["ef"].max()
    assert proj_duration == 211

    # SLAB_F2 and all structural frame elements (SLAB_*, COL_*, CURE_*) are critical
    assert bool(cpm.loc["SLAB_F2", "is_critical"]) is True

    for act_id in cpm.index:
        if act_id.startswith("SLAB_") or act_id.startswith("COL_") or act_id.startswith("CURE_"):
            assert bool(cpm.loc[act_id, "is_critical"]) is True, f"{act_id} expected critical"

    # Specific total floats
    assert cpm.loc["M_STRUCTURE", "total_float"] == 8
    assert cpm.loc["ELEC_RI", "total_float"] == 2
    assert cpm.loc["DW", "total_float"] == 4
    assert cpm.loc["EXT", "total_float"] == 44
    assert cpm.loc["BW_GF", "total_float"] == 143
    assert cpm.loc["BW_F3", "total_float"] == 83

    # Add dates and check baseline handover date
    res_dates = add_dates(res, start_date).set_index("id")
    assert res_dates.loc["MOB", "start_date"] == date(2026, 1, 5)
    assert res_dates.loc["M_HANDOVER", "finish_date"] == date(2026, 9, 7)

    # Injected delay sensitivity: with SLAB_F2 duration +10 days (9 -> 19)
    delayed_activities = activities.copy()
    idx_f2 = delayed_activities[delayed_activities["id"] == "SLAB_F2"].index[0]
    delayed_activities.loc[idx_f2, "duration_days"] = 19

    delayed_res = compute_cpm(delayed_activities)
    assert delayed_res["ef"].max() == 221


def test_calendar_conversions():
    """Verify working day to calendar date conversions, Sunday skipping, and round-tripping."""
    start = date(2026, 1, 5)  # Monday

    # Working day 0 is the start date itself
    assert wd_to_date(0, start) == date(2026, 1, 5)

    # Working day 6 skips Sunday (2026-01-11) and lands on Monday 2026-01-12
    assert wd_to_date(6, start) == date(2026, 1, 12)

    # Round trip checks
    assert date_to_wd(date(2026, 1, 5), start) == 0
    assert date_to_wd(date(2026, 1, 12), start) == 6

    # Test round-trip across 250 working days (~10 months)
    for n in range(250):
        cal_date = wd_to_date(n, start)
        # Verify no calendar date lands on Sunday
        assert cal_date.weekday() != 6, f"Day index {n} mapped to Sunday {cal_date}"
        # Verify exact round trip
        computed_wd = date_to_wd(cal_date, start)
        assert computed_wd == n, f"Round trip mismatch for n={n}: got {computed_wd}"
