"""Acceptance tests verifying exact detection of all injected project issues and negative control."""

from datetime import date
import pytest

from src.data_io import load_config, load_activities, load_boq, load_coefficients
from src.simulate import simulate
from src.schedule import compute_cpm, add_dates, wd_to_date
from src.budget import month_end_wd
from src.evm import schedule_forecast
from src.flags import evaluate_flags, get_top_issues
from src.materials import material_status
from src.payments import bills_at
from src.quality import build_inspections, ncr_log_at


def test_injected_issue_1_slab_delay():
    """Verify slab delay:
    - Month 3 has critical_behind for SLAB_F2 with reason 'progressing slower than planned'
    - Month 6 has critical_behind for BW_F4 with reason 'started late by 10 wd (knock-on)'
    - Month 6 has red milestone_slip for M_HANDOVER with magnitude 10 wd
    - CPM forecast handover moves from 7 Sep to 18 Sep 2026
    """
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()
    start_date = config["calendar"]["start_date"]

    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    # 1. Month 3 critical_behind for SLAB_F2
    flags_m3 = evaluate_flags(3, sim, config, activities, boq, coeffs)
    slab_flags = [f for f in flags_m3 if f["category"] == "critical_behind" and f["where"] == "SLAB_F2"]
    assert len(slab_flags) == 1
    assert slab_flags[0]["reason"] == "progressing slower than planned"
    assert "shuttering material" in slab_flags[0]["action"]

    # 2. Month 6 critical_behind for BW_F4
    flags_m6 = evaluate_flags(6, sim, config, activities, boq, coeffs)
    bw_flags = [f for f in flags_m6 if f["category"] == "critical_behind" and f["where"] == "BW_F4"]
    assert len(bw_flags) == 1
    assert bw_flags[0]["reason"] == "started late by 10 wd (knock-on)"
    assert "remaining float" in bw_flags[0]["action"]

    # 3. Month 6 red milestone_slip for M_HANDOVER with magnitude 10 wd
    handover_flags = [f for f in flags_m6 if f["category"] == "milestone_slip" and f["where"] == "M_HANDOVER"]
    assert len(handover_flags) == 1
    assert handover_flags[0]["severity"] == "red"
    assert handover_flags[0]["magnitude"] == "10 wd"

    # 4. CPM forecast handover moves from 7 Sep 2026 to 18 Sep 2026
    cpm_df = compute_cpm(activities)
    cpm_with_dates = add_dates(cpm_df, start_date)
    f_info = schedule_forecast(
        cpm_with_dates=cpm_with_dates,
        activities=activities,
        status_dict=sim.status_at(6),
        start_date=start_date,
        spi=0.825,
        data_date_wd=month_end_wd(6, start_date),
    )
    assert f_info["baseline_handover_date"] == "2026-09-07"
    assert f_info["cpm_handover_date"] == "2026-09-18"
    assert f_info["cpm_delay_wd"] == 10


def test_injected_issue_2_steel_escalation():
    """Verify steel price escalation:
    - item_cost amber for STEEL in months 3, 4, 5, 6
    - not in months 1-2
    """
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()
    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    for m in range(1, 7):
        fl = evaluate_flags(m, sim, config, activities, boq, coeffs)
        steel_flags = [f for f in fl if f["category"] == "item_cost" and f["where"] == "STEEL"]
        if m in [1, 2]:
            assert len(steel_flags) == 0, f"Month {m} should not have STEEL cost flag"
        else:
            assert len(steel_flags) == 1, f"Month {m} must have STEEL cost flag"
            assert steel_flags[0]["severity"] == "amber"
            assert steel_flags[0]["magnitude"] == "+10.0%"


def test_injected_issue_3_cement_shortage():
    """Verify cement shortage:
    - red material_shortfall for cement in month 4
    - no cement shortfall flag in any other month
    - no other material has a shortfall flag in month 4
    """
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()
    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    for m in range(1, 7):
        fl = evaluate_flags(m, sim, config, activities, boq, coeffs)
        shortfall_flags = [f for f in fl if f["category"] == "material_shortfall"]
        if m == 4:
            assert len(shortfall_flags) == 1, "Month 4 must have exactly 1 material shortfall flag"
            assert shortfall_flags[0]["where"] == "cement_bags"
            assert shortfall_flags[0]["severity"] == "red"
            assert shortfall_flags[0]["magnitude"] == "30.0%"
        else:
            cement_sf = [f for f in shortfall_flags if f["where"] == "cement_bags"]
            assert len(cement_sf) == 0, f"Month {m} should not have cement shortfall flag"


def test_injected_issue_4_quality_ncrs():
    """Verify QC inspections and NCR ageing:
    - exactly 3 NCRs
    - SLAB_F1 NCR is never flagged (closed in 9 days)
    - COL_F2 NCR flagged amber in month 5
    - SLAB_F3 NCR flagged red in months 5 and 6
    """
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()
    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    # 1. Exactly 3 NCRs
    ncrs_df = ncr_log_at(date(2026, 6, 30), sim, activities, config)
    assert len(ncrs_df) == 3
    assert set(ncrs_df["ncr_id"]) == {"NCR-001", "NCR-002", "NCR-003"}

    # 2. Check flags across months 1..6
    for m in range(1, 7):
        fl = evaluate_flags(m, sim, config, activities, boq, coeffs)
        ncr1_flags = [f for f in fl if f["category"] == "ncr_ageing" and f["where"] == "NCR-001"]
        ncr2_flags = [f for f in fl if f["category"] == "ncr_ageing" and f["where"] == "NCR-002"]
        ncr3_flags = [f for f in fl if f["category"] == "ncr_ageing" and f["where"] == "NCR-003"]

        # SLAB_F1 NCR is never flagged
        assert len(ncr1_flags) == 0, f"NCR-001 should never be flagged (month {m})"

        # COL_F2 NCR flagged amber in month 5 only
        if m == 5:
            assert len(ncr2_flags) == 1, "NCR-002 must be flagged in month 5"
            assert ncr2_flags[0]["severity"] == "amber"
            assert ncr2_flags[0]["magnitude"] == "20 days"
        else:
            assert len(ncr2_flags) == 0, f"NCR-002 should not be flagged in month {m}"

        # SLAB_F3 NCR flagged red in months 5 and 6
        if m in [5, 6]:
            assert len(ncr3_flags) == 1, f"NCR-003 must be flagged red in month {m}"
            assert ncr3_flags[0]["severity"] == "red"
        else:
            assert len(ncr3_flags) == 0, f"NCR-003 should not be flagged in month {m}"


def test_injected_issue_5_payment_delays():
    """Verify payment issues:
    - RA-05 red Held flag in month 6
    - RA-03 amber 'paid late' flag in month 5
    """
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()
    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    # RA-05 red Held in month 6
    flags_m6 = evaluate_flags(6, sim, config, activities, boq, coeffs)
    ra05_flags = [f for f in flags_m6 if f["category"] == "payment" and f["where"] == "RA-05"]
    assert len(ra05_flags) == 1
    assert ra05_flags[0]["severity"] == "red"
    assert "held" in ra05_flags[0]["what"].lower()

    # RA-03 amber paid late in month 5
    flags_m5 = evaluate_flags(5, sim, config, activities, boq, coeffs)
    ra03_flags = [f for f in flags_m5 if f["category"] == "payment" and f["where"] == "RA-03"]
    assert len(ra03_flags) == 1
    assert ra03_flags[0]["severity"] == "amber"
    assert "paid late" in ra03_flags[0]["what"].lower()
    assert ra03_flags[0]["magnitude"] == "45 days"


def test_month_6_top_5_issues():
    """Verify Month 6 top 5 issues ranking:
    month-6 top 5 = [milestone_slip M_HANDOVER, spi, critical_behind, ncr_ageing NCR-003, payment RA-05]
    Also verify cascade text and action text at months 3 and 6 (review fixes a & b).
    """
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()
    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    # Month 3: Slabs remain, cascade lists unachieved M_ROOF, M_STRUCTURE, M_FINISH
    flags_m3 = evaluate_flags(3, sim, config, activities, boq, coeffs)
    top3 = get_top_issues(flags_m3, limit=5)
    m3_handover = top3[0]
    assert m3_handover["where"] == "M_HANDOVER"
    assert "also moves M_ROOF / M_STRUCTURE / M_FINISH" in m3_handover["what"]
    assert "shuttering material" in m3_handover["action"]

    # Month 6: Structure complete, only unachieved M_FINISH is listed
    flags_m6 = evaluate_flags(6, sim, config, activities, boq, coeffs)
    top5 = get_top_issues(flags_m6, limit=5)

    assert len(top5) == 5
    categories = [f["category"] for f in top5]
    assert categories == ["milestone_slip", "spi", "critical_behind", "ncr_ageing", "payment"]
    assert top5[0]["where"] == "M_HANDOVER"
    assert "also moves M_FINISH" in top5[0]["what"]
    assert "M_ROOF" not in top5[0]["what"]
    assert "Recover on finishes" in top5[0]["action"]
    assert top5[1]["where"] == "Project"
    assert top5[2]["where"] == "BW_F4"
    assert top5[3]["where"] == "NCR-003"
    assert top5[4]["where"] == "RA-05"
    assert "Held: Held:" not in top5[4]["what"]
    assert all(f["severity"] == "red" for f in top5)


def test_negative_control_all_injections_off():
    """Verify negative control with injections_enabled=False:
    - zero red flags in every month 1-6
    - zero NCRs
    - no Held bill
    - no material shortfall
    """
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    coeffs = load_coefficients()

    sim_off = simulate(config, activities, boq, through_month=6, injections_enabled=False)

    # 1. Check flags for every month 1-6: zero red flags
    amber_counts = {}
    for m in range(1, 7):
        fl = evaluate_flags(m, sim_off, config, activities, boq, coeffs, injections_enabled=False)
        red_flags = [f for f in fl if f["severity"] == "red"]
        amber_flags = [f for f in fl if f["severity"] == "amber"]
        assert len(red_flags) == 0, f"Month {m} has {len(red_flags)} unexpected red flags: {red_flags}"
        amber_counts[m] = len(amber_flags)

    # 2. Zero NCRs
    ncrs_df = ncr_log_at(date(2026, 6, 30), sim_off, activities, config, injections_enabled=False)
    assert len(ncrs_df) == 0

    # 3. No Held bill
    bills_df = bills_at(date(2026, 6, 30), sim_off, config, boq, injections_enabled=False)
    held_bills = bills_df[bills_df["status"] == "Held"]
    assert len(held_bills) == 0

    # 4. No shortfall in any month
    for m in range(1, 7):
        m_stat = material_status(m, sim_off, config, activities, boq, coeffs, injections_enabled=False)
        shortfalls = m_stat[m_stat["shortfall"] > 0]
        assert len(shortfalls) == 0, f"Month {m} has unexpected shortfall: {shortfalls}"
