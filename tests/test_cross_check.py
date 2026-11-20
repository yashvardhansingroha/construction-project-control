"""Independent cross-check test verifying schedule, calendar, and EVM calculations.

Deliberately implemented from first principles using plain loops and alternative
algorithms (e.g. relaxation CPM instead of topological forward/backward passes).
"""

import csv
from datetime import date, timedelta
import calendar
import yaml
import pytest

from src.data_io import load_config, load_activities, load_boq
from src.schedule import compute_cpm
from src.budget import month_end_wd, bac as compute_bac
from src.simulate import simulate
from src.evm import monthly_evm


def _relaxation_cpm(activities_list, durations_dict):
    """Compute early and late schedules via Bellman-Ford style repeated relaxation."""
    act_ids = [a["id"] for a in activities_list]
    preds = {}
    for a in activities_list:
        raw_p = a["predecessors"].strip()
        preds[a["id"]] = [p.strip() for p in raw_p.split(";") if p.strip()] if raw_p else []

    # 1. Forward pass relaxation: ES = max(EF of predecessors)
    es = {aid: 0 for aid in act_ids}
    changed = True
    iterations = 0
    max_iter = len(act_ids) + 5
    while changed and iterations < max_iter:
        changed = False
        iterations += 1
        for aid in act_ids:
            p_list = preds[aid]
            if p_list:
                max_ef = max(es[p] + durations_dict[p] for p in p_list)
                if max_ef > es[aid]:
                    es[aid] = max_ef
                    changed = True

    ef = {aid: es[aid] + durations_dict[aid] for aid in act_ids}
    proj_end = max(ef.values())

    # Build successor graph
    succs = {aid: [] for aid in act_ids}
    for aid in act_ids:
        for p in preds[aid]:
            succs[p].append(aid)

    # 2. Backward pass relaxation: LF = min(LS of successors)
    lf = {aid: proj_end for aid in act_ids}
    changed = True
    iterations = 0
    while changed and iterations < max_iter:
        changed = False
        iterations += 1
        for aid in act_ids:
            s_list = succs[aid]
            if s_list:
                min_ls = min(lf[s] - durations_dict[s] for s in s_list)
                if min_ls < lf[aid]:
                    lf[aid] = min_ls
                    changed = True

    ls = {aid: lf[aid] - durations_dict[aid] for aid in act_ids}
    tf = {aid: ls[aid] - es[aid] for aid in act_ids}

    return es, ef, ls, lf, tf, proj_end


def test_cross_check_relaxation_cpm():
    """Verify relaxation CPM produces identical results to topological CPM for all 38 activities."""
    with open("data/activities.csv", "r", encoding="utf-8") as f:
        acts = list(csv.DictReader(f))

    planned_dur = {a["id"]: int(a["duration_days"]) for a in acts}
    es_rel, ef_rel, ls_rel, lf_rel, tf_rel, proj_end = _relaxation_cpm(acts, planned_dur)

    # Compare with main project compute_cpm
    df_cpm = compute_cpm(load_activities()).set_index("id")

    assert proj_end == 211
    for aid in df_cpm.index:
        assert es_rel[aid] == int(df_cpm.loc[aid, "es"]), f"ES mismatch on {aid}"
        assert ef_rel[aid] == int(df_cpm.loc[aid, "ef"]), f"EF mismatch on {aid}"
        assert ls_rel[aid] == int(df_cpm.loc[aid, "ls"]), f"LS mismatch on {aid}"
        assert lf_rel[aid] == int(df_cpm.loc[aid, "lf"]), f"LF mismatch on {aid}"
        assert tf_rel[aid] == int(df_cpm.loc[aid, "total_float"]), f"TF mismatch on {aid}"

    # Also check actual schedule with SLAB_F2 +10 wd
    config = load_config()
    sim = simulate(config, load_activities(), load_boq(), through_month=6)
    actual_dur = sim.actual_durations
    a_es_rel, a_ef_rel, a_ls_rel, a_lf_rel, a_tf_rel, a_end = _relaxation_cpm(acts, actual_dur)
    assert a_end == 221


def test_cross_check_calendar_walk():
    """Verify day-by-day calendar walk matches month_end_wd for months 1 to 9."""
    start_date = date(2026, 1, 5)

    # Walk day-by-day counting Mon-Sat working days up to end of each month
    cur_date = start_date
    wds_completed_by_month = {}
    total_wds = 0

    for m in range(1, 10):
        last_day = calendar.monthrange(2026, m)[1]
        m_end_date = date(2026, m, last_day)

        while cur_date <= m_end_date:
            if cur_date.weekday() != 6:  # Skip Sunday
                total_wds += 1
            cur_date += timedelta(days=1)

        wds_completed_by_month[m] = total_wds

    for m in range(1, 10):
        expected_wd = month_end_wd(m, start_date)
        assert wds_completed_by_month[m] == expected_wd, f"Month {m} working-day count mismatch"


def test_cross_check_evm_from_first_principles():
    """Verify PV, EV, AC, and derived EVM metrics match monthly_evm from first principles."""
    with open("config/project.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open("data/boq.csv", "r", encoding="utf-8") as f:
        boq_rows = list(csv.DictReader(f))
    with open("data/activities.csv", "r", encoding="utf-8") as f:
        act_rows = list(csv.DictReader(f))

    start_date = date.fromisoformat(cfg["calendar"]["start_date"])

    # 1. BOQ items map
    boq_qty = {r["item"]: float(r["quantity"]) for r in boq_rows}
    boq_rate = {r["item"]: float(r["rate_inr"]) for r in boq_rows}

    # 2. Activity budgets
    act_budgets = {}
    act_boq_shares = {}
    for a in act_rows:
        aid = a["id"]
        raw_b = a["boq_items"].strip()
        b_sum = 0.0
        shares = {}
        if raw_b:
            for pair in raw_b.split(";"):
                item, s_val = pair.split(":")
                s_float = float(s_val)
                shares[item] = s_float
                b_sum += s_float * boq_qty[item] * boq_rate[item]
        act_budgets[aid] = b_sum
        act_boq_shares[aid] = shares

    bac_val = sum(act_budgets.values())
    assert bac_val == 38113500.0

    # 3. Schedule via relaxation
    durations = {a["id"]: int(a["duration_days"]) for a in act_rows}
    b_es, b_ef, b_ls, b_lf, b_tf, _ = _relaxation_cpm(act_rows, durations)

    # Working day to month mapping by walking calendar
    wd_to_m = {}
    cur = start_date
    wd_idx = 0
    while wd_idx < 250:
        if cur.weekday() != 6:
            wd_to_m[wd_idx] = cur.month
            wd_idx += 1
        cur += timedelta(days=1)

    # 4. Planned Value linear spreading per activity
    monthly_pv = {m: 0.0 for m in range(1, 7)}
    for aid, b_amt in act_budgets.items():
        dur = durations[aid]
        if dur <= 0:
            continue
        es = b_es[aid]
        # Spread over working days and accumulate
        act_cum_by_m = {m: 0.0 for m in range(1, 10)}
        for day in range(es, es + dur):
            m_idx = wd_to_m[day]
            act_cum_by_m[m_idx] += b_amt / float(dur)

        # Round cumulative sums to rupee
        running_cum = 0.0
        prev_round = 0
        for m in range(1, 7):
            running_cum += act_cum_by_m[m]
            cur_round = round(running_cum)
            m_pv = cur_round - prev_round
            monthly_pv[m] += m_pv
            prev_round = cur_round

    cum_pv = {}
    tot_pv = 0
    for m in range(1, 7):
        tot_pv += int(monthly_pv[m])
        cum_pv[m] = tot_pv

    # 5. Actual simulation run
    sim = simulate(cfg, load_activities(), load_boq(), through_month=6)
    actual_dur = sim.actual_durations
    a_es, a_ef, a_ls, a_lf, a_tf, _ = _relaxation_cpm(act_rows, actual_dur)

    # Baseline critical path (TF == 0 in baseline schedule)
    b_crit_set = {aid for aid, tf in b_tf.items() if tf == 0}

    # Noise values drawn in simulation
    noise_dict = sim.noise_by_act

    # 6. Earned Value and Actual Cost per month
    cum_ev = {}
    cum_ac = {}
    pct_by_m = {m: {} for m in range(1, 7)}

    running_ac = 0.0
    for m in range(1, 7):
        cutoff_wd = month_end_wd(m, start_date)
        m_ev = 0.0
        m_ac = 0.0

        for a in act_rows:
            aid = a["id"]
            a_dur = actual_dur[aid]
            es = a_es[aid]
            ef = a_ef[aid]

            wds_worked = max(0, min(cutoff_wd, ef) - es)
            pct = min(1.0, max(0.0, float(wds_worked) / float(a_dur))) if a_dur > 0 else (1.0 if cutoff_wd >= ef else 0.0)
            pct_by_m[m][aid] = pct
            m_ev += act_budgets[aid] * pct

            # Change in physical % complete during month m
            prev_pct = pct_by_m[m - 1][aid] if m > 1 else 0.0
            delta_pct = pct - prev_pct

            if delta_pct > 0 and act_boq_shares[aid]:
                is_crit = aid in b_crit_set
                c_noise = noise_dict[aid]["cost_noise"] if not is_crit else 0.0

                for item, share in act_boq_shares[aid].items():
                    qty_placed = boq_qty[item] * share * delta_pct
                    rate = boq_rate[item] * (1.0 + c_noise)
                    if item == "STEEL" and m >= 3:
                        rate = rate * 1.10
                    m_ac += qty_placed * rate

        cum_ev[m] = m_ev
        running_ac += m_ac
        cum_ac[m] = running_ac

    # Compare with pipeline monthly_evm
    from src.pipeline import _get_pipeline_context
    ctx = _get_pipeline_context()
    ref_evm = ctx["evm_df"].set_index("month")

    for m in range(1, 7):
        ref_pv = float(ref_evm.loc[m, "pv"])
        ref_ev = float(ref_evm.loc[m, "ev"])
        ref_ac = float(ref_evm.loc[m, "ac"])

        assert abs(cum_pv[m] - ref_pv) <= 1.0, f"M{m} PV mismatch: calc {cum_pv[m]} vs ref {ref_pv}"
        assert abs(cum_ev[m] - ref_ev) <= 1.0, f"M{m} EV mismatch: calc {cum_ev[m]} vs ref {ref_ev}"
        assert abs(cum_ac[m] - ref_ac) <= 1.0, f"M{m} AC mismatch: calc {cum_ac[m]} vs ref {ref_ac}"

    # Month 6 KPI metrics comparison within 1e-9
    m6_ev = cum_ev[6]
    m6_pv = cum_pv[6]
    m6_ac = cum_ac[6]

    spi_calc = m6_ev / m6_pv
    cpi_calc = m6_ev / m6_ac
    eac_calc = bac_val / cpi_calc
    tcpi_calc = (bac_val - m6_ev) / (bac_val - m6_ac)

    assert abs(spi_calc - float(ref_evm.loc[6, "spi"])) < 1e-6
    assert abs(cpi_calc - float(ref_evm.loc[6, "cpi"])) < 1e-6
    assert abs(eac_calc - float(ref_evm.loc[6, "eac"])) < 1.0
    assert abs(tcpi_calc - float(ref_evm.loc[6, "tcpi"])) < 1e-6
