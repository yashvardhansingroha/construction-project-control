"""Unit tests for warning flag rules, reason detection, and top-5 ranking."""

from datetime import date
import copy
import pytest
from src.flags import RULES_TEXT, get_top_issues, evaluate_flags
from src.data_io import load_config, load_activities, load_boq
from src.simulate import simulate


def test_milestone_slip_thresholds():
    """Verify milestone_slip rule: >5 wd amber, >=10 wd red, <=5 wd no flag."""
    def check_milestone_slip(slip_days: int):
        if slip_days >= 10:
            return "red"
        elif slip_days > 5:
            return "amber"
        return None

    assert check_milestone_slip(10) == "red"
    assert check_milestone_slip(12) == "red"
    assert check_milestone_slip(6) == "amber"
    assert check_milestone_slip(9) == "amber"
    assert check_milestone_slip(5) is None
    assert check_milestone_slip(0) is None


def test_critical_behind_thresholds_and_reasons():
    """Verify critical_behind rule: >50 pts red, >5 pts amber, and reason classification."""
    def check_critical_behind(diff_pts: float):
        if diff_pts > 50.0:
            return "red"
        elif diff_pts > 5.0:
            return "amber"
        return None

    assert check_critical_behind(51.0) == "red"
    assert check_critical_behind(75.0) == "red"
    assert check_critical_behind(50.0) == "amber"
    assert check_critical_behind(6.0) == "amber"
    assert check_critical_behind(5.0) is None
    assert check_critical_behind(0.0) is None

    # Reason classification
    def get_reason(start_delay: int, planned_dur: int, actual_dur: int):
        if start_delay > 0 and actual_dur == planned_dur:
            return f"started late by {start_delay} wd (knock-on)"
        return "progressing slower than planned"

    assert get_reason(0, 9, 19) == "progressing slower than planned"
    assert get_reason(10, 8, 8) == "started late by 10 wd (knock-on)"


def test_spi_cpi_thresholds():
    """Verify SPI/CPI project thresholds: <0.90 red, <0.95 amber, >=0.95 no flag."""
    def check_index(val: float):
        if val < 0.90:
            return "red"
        elif val < 0.95:
            return "amber"
        return None

    assert check_index(0.89) == "red"
    assert check_index(0.90) == "amber"
    assert check_index(0.94) == "amber"
    assert check_index(0.95) is None
    assert check_index(1.00) is None


def test_activity_cost_thresholds():
    """Verify activity_cost rule: |cost_variance_pct| > 5.0% amber, <= 5.0% no flag."""
    def check_act_cost(cv_pct: float):
        if abs(cv_pct) > 5.0:
            return "amber"
        return None

    assert check_act_cost(5.1) == "amber"
    assert check_act_cost(-5.1) == "amber"
    assert check_act_cost(5.0) is None
    assert check_act_cost(-5.0) is None
    assert check_act_cost(0.0) is None


def test_item_cost_thresholds():
    """Verify item_cost rule: >15% red, >5% amber, <=5% no flag."""
    def check_item_cost(var_pct: float):
        if var_pct > 15.0:
            return "red"
        elif var_pct > 5.0:
            return "amber"
        return None

    assert check_item_cost(15.1) == "red"
    assert check_item_cost(15.0) == "amber"
    assert check_item_cost(10.0) == "amber"
    assert check_item_cost(5.1) == "amber"
    assert check_item_cost(5.0) is None
    assert check_item_cost(0.0) is None


def test_material_shortfall_thresholds():
    """Verify material_shortfall rule: >20% red, <=20% amber, 0% no flag."""
    def check_shortfall(sf: float, req: float):
        if sf > 0.0 and req > 0.0:
            pct = (sf / req) * 100.0
            return "red" if pct > 20.0 else "amber"
        return None

    assert check_shortfall(30.0, 100.0) == "red"
    assert check_shortfall(20.1, 100.0) == "red"
    assert check_shortfall(20.0, 100.0) == "amber"
    assert check_shortfall(5.0, 100.0) == "amber"
    assert check_shortfall(0.0, 100.0) is None


def test_ncr_ageing_thresholds():
    """Verify ncr_ageing rule: >14 days open -> amber if closed by month end, red if still open."""
    def check_ncr(days_open: int, closed_by_month_end: bool):
        if days_open > 14:
            return "amber" if closed_by_month_end else "red"
        return None

    assert check_ncr(15, closed_by_month_end=True) == "amber"
    assert check_ncr(20, closed_by_month_end=True) == "amber"
    assert check_ncr(15, closed_by_month_end=False) == "red"
    assert check_ncr(56, closed_by_month_end=False) == "red"
    assert check_ncr(14, closed_by_month_end=True) is None
    assert check_ncr(14, closed_by_month_end=False) is None
    assert check_ncr(9, closed_by_month_end=True) is None


def test_payment_flags_thresholds():
    """Verify payment flags: Held bill red, Pending >30 days amber, Paid >30 days amber."""
    def check_bill(status: str, days_pending: int, days_to_pay: int):
        if status == "Held":
            return "red"
        if status == "Pending" and days_pending > 30:
            return "amber"
        if status == "Paid" and days_to_pay > 30:
            return "amber"
        return None

    assert check_bill("Held", days_pending=30, days_to_pay=0) == "red"
    assert check_bill("Pending", days_pending=31, days_to_pay=0) == "amber"
    assert check_bill("Pending", days_pending=30, days_to_pay=0) is None
    assert check_bill("Paid", days_pending=0, days_to_pay=45) == "amber"
    assert check_bill("Paid", days_pending=0, days_to_pay=21) is None


def test_top_issues_priority_and_deduplication():
    """Verify top issues ranking follows category priority and at most one issue per category."""
    sample_flags = [
        {"category": "milestone_slip", "where": "M_ROOF", "severity": "red", "magnitude_num": 10.0, "what": "Roof slip"},
        {"category": "milestone_slip", "where": "M_HANDOVER", "severity": "red", "magnitude_num": 10.0, "what": "Handover slip"},
        {"category": "spi", "where": "Project", "severity": "red", "magnitude_num": 17.5, "what": "SPI low"},
        {"category": "critical_behind", "where": "BW_F4", "severity": "red", "magnitude_num": 75.0, "what": "BW_F4 behind"},
        {"category": "critical_behind", "where": "PLUMB_RI", "severity": "amber", "magnitude_num": 33.3, "what": "PLUMB behind"},
        {"category": "payment", "where": "RA-05", "severity": "red", "magnitude_num": 30.0, "what": "RA-05 held"},
        {"category": "ncr_ageing", "where": "NCR-003", "severity": "red", "magnitude_num": 56.0, "what": "NCR open"},
        {"category": "item_cost", "where": "STEEL", "severity": "amber", "magnitude_num": 10.0, "what": "STEEL +10%"},
    ]

    top = get_top_issues(sample_flags, limit=5)
    assert len(top) == 5
    cats = [f["category"] for f in top]
    assert cats == ["milestone_slip", "spi", "critical_behind", "ncr_ageing", "payment"]
    assert top[0]["where"] == "M_HANDOVER"
    assert "also moves M_ROOF" in top[0]["what"]


def test_dynamic_threshold_flag_text():
    """Verify that flag text dynamically formats threshold values from config."""
    config_base = load_config()
    activities = load_activities()
    boq = load_boq()
    sim = simulate(config_base, activities, boq, through_month=6)

    # 1. Default config: spi_amber is 0.95
    flags_default = evaluate_flags(month=3, sim=sim, activities=activities, boq=boq, config=config_base)
    spi_flags_def = [f for f in flags_default if f["category"] == "spi"]
    assert len(spi_flags_def) == 1
    assert "below 0.95 threshold" in spi_flags_def[0]["what"]

    # 2. Modified config: set spi_amber to 0.92
    config_mod = copy.deepcopy(config_base)
    config_mod["thresholds"]["spi_amber"] = 0.92
    flags_mod = evaluate_flags(month=3, sim=sim, activities=activities, boq=boq, config=config_mod)
    spi_flags_mod = [f for f in flags_mod if f["category"] == "spi"]
    assert len(spi_flags_mod) == 1
    assert "below 0.92 threshold" in spi_flags_mod[0]["what"]

