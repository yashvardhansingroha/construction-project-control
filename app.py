"""Construction Project Control Dashboard (Synthetic).

Interactive Streamlit application providing earned value management, critical path
scheduling, material inventory tracking, payment certifications, quality logs, and
executive reporting downloads.
"""

from datetime import date
from pathlib import Path
import calendar
import pandas as pd
import streamlit as st

from src.data_io import load_config, load_activities, load_boq, load_coefficients
from src.schedule import compute_cpm, add_dates, critical_path, forecast_cpm, wd_to_date
from src.budget import monthly_pv, activity_budgets, activity_item_budget, bac, month_end_wd
from src.simulate import simulate
from src.evm import monthly_evm, activity_evm, item_cost_variance
from src.materials import baseline_requirement_by_month
from src.quality import build_inspections
from src.pipeline import month_view, _get_pipeline_context
from src.charts import gantt_chart, s_curve_chart
from src.report import format_inr, format_date_str, build_pdf, write_workbook
from typing import Any, Dict, List, Optional, Tuple, Union


def format_crore(val: Optional[Union[int, float]]) -> str:
    """Format rupee amount in crores with 2 decimal places (e.g., 'Rs 3.90 Cr', '-Rs 0.09 Cr')."""
    if val is None:
        return "-"
    cr = float(val) / 1e7
    if cr < 0:
        return f"-Rs {abs(cr):.2f} Cr"
    return f"Rs {cr:.2f} Cr"


# -----------------------------------------------------------------------------
# Streamlit Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Construction Project Control (Synthetic)",
    layout="wide",
)


# -----------------------------------------------------------------------------
# Cached Data Loaders
# -----------------------------------------------------------------------------
@st.cache_data
def get_month_view_cached(m: int) -> dict:
    """Fetch complete project control state dictionary for month m."""
    return month_view(m)


@st.cache_data
def get_sensitivity_data_cached() -> dict:
    """Retrieve what-if sensitivity analysis data."""
    from src.sensitivity import get_or_run_sensitivity
    return get_or_run_sensitivity()


@st.cache_data
def get_baseline_schedule_data():
    """Compute and cache baseline CPM schedule with calendar dates."""
    ctx = _get_pipeline_context()
    return ctx["cpm_df"], ctx["cpm_with_dates"], ctx["crit_path_ids"], ctx["start_date"], ctx["activities"]


@st.cache_data
def get_baseline_materials():
    """Compute baseline monthly requirement per material across full lifecycle."""
    ctx = _get_pipeline_context()
    return baseline_requirement_by_month(
        activities=ctx["activities"],
        boq=ctx["boq"],
        cpm_with_dates=ctx["cpm_with_dates"],
        start_date=ctx["start_date"],
        coeffs=ctx["coeffs"],
    )


@st.cache_data
def get_gantt_chart_image(m: int) -> str:
    """Generate and cache baseline vs forecast Gantt comparison chart for month m."""
    out_path = Path(f"outputs/charts/gantt_month_{m:02d}.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ctx = _get_pipeline_context()
    status_m = ctx["sim_result"].status_at(m)
    cutoff_wd = month_end_wd(m, ctx["start_date"])
    f_cpm = forecast_cpm(ctx["activities"], status_m, cutoff_wd)
    f_cpm_dates = add_dates(f_cpm, ctx["start_date"])
    gantt_chart(
        cpm_df_with_dates=ctx["cpm_with_dates"],
        path=out_path,
        forecast_df=f_cpm_dates,
        title=f"Schedule Status Month {m}: Baseline vs Forecast (Synthetic)",
    )
    return str(out_path)


@st.cache_data
def get_scurve_chart_image(m: int) -> str:
    """Generate and cache S-curve chart through month m."""
    out_path = Path(f"outputs/charts/s_curve_month_{m:02d}.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ctx = _get_pipeline_context()
    evm_df = ctx["evm_df"]
    pv_full_df = ctx["pv_full_df"]
    s_curve_chart(
        monthly_evm_df=evm_df.loc[evm_df["month"] <= m],
        pv_full_df=pv_full_df,
        path=out_path,
        title=f"Project S-Curve through Month {m} (Synthetic)",
    )
    return str(out_path)


@st.cache_data
def get_activity_evm_df(m: int) -> pd.DataFrame:
    """Compute activity-level EVM metrics for month m."""
    ctx = _get_pipeline_context()
    sim = ctx["sim_result"]
    budgets_df = ctx["budgets_df"]
    cutoff_wd = month_end_wd(m, ctx["start_date"])
    b_cpm = ctx["cpm_df"].set_index("id")

    pv_by_act = {}
    for aid, row in b_cpm.iterrows():
        b_val = float(budgets_df.loc[budgets_df["id"] == aid, "budget_inr"].iloc[0])
        dur = int(row["duration_days"])
        if dur <= 0:
            pv_by_act[aid] = 0.0
            continue
        es = int(row["es"])
        ef = int(row["ef"])
        worked_wds = max(0, min(cutoff_wd, ef) - es)
        frac = min(1.0, max(0.0, float(worked_wds) / float(dur)))
        pv_by_act[aid] = round(b_val * frac)

    return activity_evm(sim, budgets_df, pv_by_act, m)


@st.cache_data
def get_item_cost_variance_df(m: int) -> pd.DataFrame:
    """Compute BOQ item variance for month m."""
    ctx = _get_pipeline_context()
    return item_cost_variance(ctx["sim_result"], ctx["item_budget_df"], month=m)


@st.cache_data
def get_inspections_data(m: int):
    """Retrieve full inspection log and NCR log up to month-m cutoff."""
    ctx = _get_pipeline_context()
    year = ctx["start_date"].year
    last_day = calendar.monthrange(year, m)[1]
    m_end = date(year, m, last_day)
    return build_inspections(ctx["sim_result"], ctx["activities"], ctx["config"], eval_date=m_end)


@st.cache_data
def get_pdf_bytes(m: int) -> bytes:
    """Generate executive PDF report for month m and return file bytes."""
    pdf_path = Path(f"outputs/report_month_{m:02d}.pdf")
    build_pdf(m, pdf_path)
    with open(pdf_path, "rb") as f:
        return f.read()


@st.cache_data
def get_workbook_bytes() -> bytes:
    """Generate full Excel workbook and return file bytes."""
    wb_path = Path("outputs/workbook.xlsx")
    if not wb_path.exists():
        write_workbook(wb_path)
    with open(wb_path, "rb") as f:
        return f.read()


# -----------------------------------------------------------------------------
# Sidebar Navigation & Controls
# -----------------------------------------------------------------------------
st.sidebar.title("Construction Project Control")
m = st.sidebar.slider("Status month", 1, 6, 6)
st.sidebar.caption("Synthetic data: illustrative rates, quantities and events")

mv = get_month_view_cached(m)
data_date_fmt = format_date_str(mv["month_date"])
st.sidebar.info(f"**Data Date:** {data_date_fmt}")


# -----------------------------------------------------------------------------
# Main Application Tabs
# -----------------------------------------------------------------------------
tab_overview, tab_schedule, tab_cost, tab_materials, tab_payments, tab_quality, tab_report = st.tabs([
    "Overview",
    "Schedule & Critical Path",
    "Cost & EVM",
    "Materials",
    "Payments",
    "Quality",
    "Monthly Report",
])


# =============================================================================
# Tab 1: Overview
# =============================================================================
with tab_overview:
    st.caption("Synthetic data: illustrative rates, quantities and events.")

    # Status Banner (Colored text RED/AMBER/GREEN matching PDF sentence)
    st_color = (
        "#c62828" if mv["overall_status"] == "RED"
        else ("#e65100" if mv["overall_status"] == "AMBER" else "#2e7d32")
    )
    st.markdown(
        f"<div style='padding: 10px 14px; border-left: 5px solid {st_color}; "
        f"background-color: #f8f9fa; margin-bottom: 15px;'>"
        f"<span style='font-size: 16px; font-weight: bold; color: {st_color};'>{mv['status_line']}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Core Metric Cards: SPI, CPI, EAC, VAC, Forecast Handover (with delay)
    hd = mv["headline"]
    sf = mv["schedule_forecast"]
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    with col_m1:
        st.metric("SPI", f"{hd['spi']:.3f}" if hd["spi"] is not None else "-")
    with col_m2:
        st.metric("CPI", f"{hd['cpi']:.3f}" if hd["cpi"] is not None else "-")
    with col_m3:
        st.metric("EAC", format_crore(hd["eac"]))
    with col_m4:
        st.metric("VAC", format_crore(hd["vac"]))
    with col_m5:
        ho_str = format_date_str(sf["cpm_handover_date"])
        d_wd = sf["cpm_delay_wd"]
        d_lbl = f"+{d_wd} wd delay" if d_wd > 0 else "On schedule"
        st.metric("Forecast Handover", ho_str, delta=d_lbl, delta_color="inverse" if d_wd > 0 else "normal")

    st.divider()

    # Active Flag Counts by Severity
    red_count = sum(1 for f in mv["flags"] if f["severity"] == "red")
    amber_count = sum(1 for f in mv["flags"] if f["severity"] == "amber")
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        st.metric("Red Severity Flags", red_count)
    with col_f2:
        st.metric("Amber Severity Flags", amber_count)
    with col_f3:
        st.metric("Total Warning Flags", red_count + amber_count)

    # Top 5 Priority Issues Table
    st.subheader("Top Priority Project Issues & Corrective Actions")
    top5_rows = []
    for iss in mv["top_5_issues"]:
        top5_rows.append({
            "Severity": iss["severity"].upper(),
            "Issue Description": iss["what"],
            "Where": iss["where"],
            "Lead Owner": iss["owner"],
            "Corrective Action": iss["action"],
        })
    st.table(pd.DataFrame(top5_rows))

    # Full Expandable Flags List (Filtered by Category)
    with st.expander("Full Project Control Flags Register (Filterable)", expanded=False):
        all_cats = sorted(list(set(f["category"] for f in mv["flags"])))
        selected_cat = st.selectbox("Filter flags by category", ["All"] + all_cats)
        active_flags = (
            mv["flags"] if selected_cat == "All"
            else [f for f in mv["flags"] if f["category"] == selected_cat]
        )
        flags_data = []
        for f in active_flags:
            flags_data.append({
                "Flag ID": f.get("flag_id", "-"),
                "Severity": f["severity"].upper(),
                "Category": f["category"],
                "Description": f["what"],
                "Where": f["where"],
                "Magnitude": f["magnitude"],
                "Owner": f["owner"],
                "Corrective Action": f["action"],
            })
        st.dataframe(pd.DataFrame(flags_data), use_container_width=True, hide_index=True)


# =============================================================================
# Tab 2: Schedule & Critical Path
# =============================================================================
with tab_schedule:
    st.caption("Synthetic data: illustrative rates, quantities and events.")

    # Gantt Chart Image (Baseline outline vs forecast at month m, critical in red)
    st.subheader(f"Project Schedule Gantt Chart (Month {m})")
    gantt_img_path = get_gantt_chart_image(m)
    st.image(gantt_img_path, use_container_width=True)

    # Milestone Table: baseline vs forecast vs slip
    st.subheader("Project Milestones Performance")
    ms_records = []
    for ms in mv["schedule_forecast"]["milestones"]:
        ms_records.append({
            "Milestone ID": ms["id"],
            "Name": ms["name"],
            "Baseline Date": format_date_str(ms["baseline_date"]),
            "Forecast Date": format_date_str(ms["forecast_date"]),
            "Status": ms.get("status_text", ms.get("status", "Forecast")),
            "Slip (wd)": f"+{ms['slip_wd']} wd" if ms["slip_wd"] > 0 else "0 wd",
        })
    st.dataframe(pd.DataFrame(ms_records), use_container_width=True, hide_index=True)

    # CPM Table (ES, EF, LS, LF, float, critical) with "critical only" checkbox
    st.subheader("Baseline CPM (planned)")
    cpm_df, cpm_with_dates, crit_path_ids, start_dt, acts = get_baseline_schedule_data()
    show_crit_only = st.checkbox("Show critical path activities only", value=False)
    cpm_view = cpm_with_dates.copy()
    if show_crit_only:
        cpm_view = cpm_view[cpm_view["is_critical"] == True]

    cpm_display = pd.DataFrame({
        "Activity ID": cpm_view["id"],
        "Duration (wd)": cpm_view["duration_days"],
        "Early Start (ES)": cpm_view["es"],
        "Early Finish (EF)": cpm_view["ef"],
        "Late Start (LS)": cpm_view["ls"],
        "Late Finish (LF)": cpm_view["lf"],
        "Total Float": cpm_view["total_float"],
        "Critical": cpm_view["is_critical"].map(lambda x: "Yes" if x else "No"),
        "Start Date": cpm_view["start_date"].map(lambda d: format_date_str(d)),
        "Finish Date": cpm_view["finish_date"].map(lambda d: format_date_str(d)),
    })
    st.dataframe(cpm_display, use_container_width=True, hide_index=True)

    # Critical Path Ordered List
    st.subheader("Critical Path Activity Sequence")
    st.code(" -> ".join(crit_path_ids), language="text")


# =============================================================================
# Tab 3: Cost & EVM
# =============================================================================
with tab_cost:
    st.caption("Synthetic data: illustrative rates, quantities and events.")

    # S-curve to Month m
    st.subheader(f"Earned Value S-Curve: Planned, Earned & Actuals (Through Month {m})")
    scurve_img_path = get_scurve_chart_image(m)
    st.image(scurve_img_path, use_container_width=True)

    # EVM Table: Months 1..m
    st.subheader(f"Cumulative EVM Performance History (Months 1 to {m})")
    evm_hist = pd.DataFrame(mv["monthly_evm"])
    evm_hist_display = pd.DataFrame({
        "Month": evm_hist["month"],
        "PV (INR)": evm_hist["pv"].map(format_inr),
        "EV (INR)": evm_hist["ev"].map(format_inr),
        "AC (INR)": evm_hist["ac"].map(format_inr),
        "SV (INR)": evm_hist["sv"].map(format_inr),
        "CV (INR)": evm_hist["cv"].map(format_inr),
        "SPI": evm_hist["spi"].map(lambda v: f"{v:.3f}" if v is not None else "-"),
        "CPI": evm_hist["cpi"].map(lambda v: f"{v:.3f}" if v is not None else "-"),
        "EAC (INR)": evm_hist["eac"].map(format_inr),
        "EAC Comb. (INR)": evm_hist["eac_combined"].map(format_inr),
        "ETC (INR)": evm_hist["etc"].map(format_inr),
        "VAC (INR)": evm_hist["vac"].map(format_inr),
        "TCPI": evm_hist["tcpi"].map(lambda v: f"{v:.3f}" if v is not None else "-"),
    })
    st.dataframe(evm_hist_display, use_container_width=True, hide_index=True)

    # Activity Cost Table for Month m (PV, EV, AC, CV, CPI, variance %)
    st.subheader(f"Activity Cost & EVM Status (Month {m})")
    act_evm_raw = get_activity_evm_df(m)
    act_evm_display = pd.DataFrame({
        "Activity ID": act_evm_raw["id"],
        "PV (INR)": act_evm_raw["pv"].map(format_inr),
        "EV (INR)": act_evm_raw["ev"].map(format_inr),
        "AC (INR)": act_evm_raw["ac"].map(format_inr),
        "CV (INR)": act_evm_raw["cv"].map(format_inr),
        "CPI": act_evm_raw["cpi"].map(lambda v: f"{v:.3f}" if v is not None else "-"),
        "Variance %": act_evm_raw["cost_variance_pct"].map(lambda v: f"{v:+.1f}%" if v is not None else "-"),
    })
    st.dataframe(act_evm_display, use_container_width=True, hide_index=True)

    # BOQ Item Variance Table for Month m
    st.subheader(f"BOQ Item Cost Variance (Month {m})")
    item_var_raw = get_item_cost_variance_df(m)
    item_var_display = pd.DataFrame({
        "BOQ Item": item_var_raw["item"],
        "Quantity Placed": item_var_raw["quantity"].map(lambda v: f"{v:,.1f}"),
        "Earned Value (INR)": item_var_raw["earned_value"].map(format_inr),
        "Actual Cost (INR)": item_var_raw["actual_cost"].map(format_inr),
        "Variance (INR)": (item_var_raw["actual_cost"] - item_var_raw["earned_value"]).map(format_inr),
        "Variance %": item_var_raw["variance_pct"].map(lambda v: f"{v:+.2f}%"),
    })
    st.dataframe(item_var_display, use_container_width=True, hide_index=True)

    # Explanation Paragraph on EAC vs EAC_combined
    st.markdown("""
    **EAC Methodology & Forecast Interpretation:**
    
    The standard Estimate at Completion formulation, $\\text{EAC} = \\text{BAC} / \\text{CPI}$, assumes that future work 
    will proceed at the cumulative cost efficiency rate ($\\text{CPI}$) established to date. This provides an unbiased 
    estimate when schedule delays do not impose subsequent monetary penalties. In contrast, the combined forecast, 
    $\\text{EAC}_{\\text{combined}} = \\text{AC} + (\\text{BAC} - \\text{EV}) / (\\text{CPI} \\times \\text{SPI})$, 
    explicitly compounds both cost and schedule inefficiencies. When a project is behind schedule ($\\text{SPI} < 1$), 
    accelerating remaining work or sustaining extended site overhead unavoidably increases actual costs. Consequently, 
    $\\text{EAC}_{\\text{combined}}$ provides an upper-bound, risk-adjusted financial projection for executive management.
    """)

    # What-if (Sensitivity Analysis, Month 6)
    st.subheader("What-if (sensitivity, month 6)")
    st.markdown(
        "Sensitivity analysis explores how variations in steel price escalation (5% to 15%) and "
        "structural slab delays (5 to 15 working days on SLAB_F2) impact final cost forecasts (EAC, VAC) "
        "and project handover completion dates."
    )

    sens_data = get_sensitivity_data_cached()

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown("**Steel Escalation Sensitivity** *(SLAB_F2 delay held at 10 wd)*")
        steel_df = pd.DataFrame(sens_data["steel_sensitivity"])
        steel_disp = pd.DataFrame({
            "Steel Uplift": steel_df["steel_uplift_pct"].map(lambda v: f"{v}%"),
            "Slab Delay": steel_df["slab_delay_wd"].map(lambda v: f"{v} wd"),
            "SPI": steel_df["spi"].map(lambda v: f"{v:.3f}"),
            "CPI": steel_df["cpi"].map(lambda v: f"{v:.3f}"),
            "EAC (INR)": steel_df["eac"].map(format_inr),
            "VAC (INR)": steel_df["vac"].map(format_inr),
            "Forecast Handover": steel_df["cpm_handover_date"].map(format_date_str),
            "Delay": steel_df["cpm_delay_wd"].map(lambda v: f"+{v} wd"),
        })
        st.dataframe(steel_disp, use_container_width=True, hide_index=True)

    with col_s2:
        st.markdown("**SLAB_F2 Schedule Delay Sensitivity** *(Steel uplift held at 10%)*")
        slab_df = pd.DataFrame(sens_data["slab_delay_sensitivity"])
        slab_disp = pd.DataFrame({
            "Slab Delay": slab_df["slab_delay_wd"].map(lambda v: f"{v} wd"),
            "Steel Uplift": slab_df["steel_uplift_pct"].map(lambda v: f"{v}%"),
            "SPI": slab_df["spi"].map(lambda v: f"{v:.3f}"),
            "CPI": slab_df["cpi"].map(lambda v: f"{v:.3f}"),
            "EAC (INR)": slab_df["eac"].map(format_inr),
            "VAC (INR)": slab_df["vac"].map(format_inr),
            "Forecast Handover": slab_df["cpm_handover_date"].map(format_date_str),
            "Delay": slab_df["cpm_delay_wd"].map(lambda v: f"+{v} wd"),
        })
        st.dataframe(slab_disp, use_container_width=True, hide_index=True)


# =============================================================================
# Tab 4: Materials
# =============================================================================
with tab_materials:
    st.caption("Synthetic data: illustrative rates, quantities and events.")

    # Month-m Stock Status Table
    st.subheader(f"Material Inventory & Stock Ledger (Month {m})")
    mat_stat_df = pd.DataFrame(mv["material_status"])
    mat_names_map = {
        "cement_bags": "Cement (bags)",
        "steel_kg": "Steel (kg)",
        "sand_cum": "Sand (cum)",
        "aggregate_cum": "Aggregate (cum)",
        "bricks": "Bricks (nos)",
    }
    mat_stat_display = pd.DataFrame({
        "Material": mat_stat_df["material"].map(lambda k: mat_names_map.get(k, k)),
        "Required Next Month": mat_stat_df["required_next_month"].map(lambda v: f"{v:,.1f}"),
        "Procured This Month": mat_stat_df["procured_this_month"].map(lambda v: f"{v:,.1f}"),
        "Shortfall": mat_stat_df["shortfall"].map(lambda v: f"{v:,.1f}"),
        "Surplus": mat_stat_df["surplus"].map(lambda v: f"{v:,.1f}"),
        "Opening Stock": mat_stat_df["opening_stock"].map(lambda v: f"{v:,.1f}"),
        "Consumed": mat_stat_df["consumed"].map(lambda v: f"{v:,.1f}"),
        "Closing Stock": mat_stat_df["closing_stock"].map(lambda v: f"{v:,.1f}"),
    })
    st.dataframe(mat_stat_display, use_container_width=True, hide_index=True)

    # Next-Month Purchase Plan
    next_m = m + 1
    st.subheader(f"Procurement Purchase Plan (Forecast Need for Month {next_m})")
    plan_rows = [
        {"Material": mat_names_map.get(k, k), "Forecast Quantity Required": f"{v:,.1f}"}
        for k, v in mv["next_month_plan"].items()
    ]
    st.dataframe(pd.DataFrame(plan_rows), use_container_width=True, hide_index=True)

    # Bar Chart of Baseline Requirement by Month per Material
    st.subheader("Baseline Material Consumption Schedule")
    base_mats_df = get_baseline_materials()
    mat_options = list(mat_names_map.keys())
    selected_mat_key = st.selectbox(
        "Select material for baseline requirement schedule",
        mat_options,
        format_func=lambda k: mat_names_map.get(k, k),
    )
    chart_data = base_mats_df.set_index("month")[[selected_mat_key]].rename(
        columns={selected_mat_key: mat_names_map.get(selected_mat_key, selected_mat_key)}
    )
    st.bar_chart(chart_data)


# =============================================================================
# Tab 5: Payments
# =============================================================================
with tab_payments:
    st.caption("Synthetic data: illustrative rates, quantities and events.")

    # Retention Held Metric
    cum_ret = sum(b["retention"] for b in mv["ra_bills"] if b.get("month", 0) <= m)
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.metric("Cumulative Retention Held to Date", format_inr(cum_ret))
    with col_p2:
        total_billed = sum(b["gross_amount"] for b in mv["ra_bills"] if b.get("month", 0) <= m)
        st.metric("Total Billed Gross to Date", format_inr(total_billed))

    # RA Bills Table at Month-End Date
    st.subheader(f"Running Account (RA) Bills Register (As of {data_date_fmt})")
    bills_raw = pd.DataFrame(mv["ra_bills"])
    bills_display = pd.DataFrame({
        "Bill No": bills_raw["bill_no"],
        "Month": bills_raw["month"],
        "Gross (INR)": bills_raw["gross_amount"].map(format_inr),
        "Work at BOQ Rates": bills_raw["work_at_boq_rates"].map(format_inr),
        "Price Variation": bills_raw["price_variation"].map(format_inr),
        "Retention (5%)": bills_raw["retention"].map(format_inr),
        "TDS (2%)": bills_raw["tds"].map(format_inr),
        "Net Payable (INR)": bills_raw["net_payable"].map(format_inr),
        "Submitted Date": bills_raw["submitted_date"].map(format_date_str),
        "Certified Date": bills_raw["certified_date"].map(format_date_str),
        "Paid Date": bills_raw["paid_date"].map(format_date_str),
        "Status": bills_raw["status"],
        "Days Pending": bills_raw["days_pending"],
        "Hold Reason": bills_raw["hold_reason"].fillna("-"),
    })
    st.dataframe(bills_display, use_container_width=True, hide_index=True)

    # Payment Flags
    st.subheader("Payment & Commercial Warning Flags")
    pay_flags = [f for f in mv["flags"] if f["category"] == "payment"]
    if pay_flags:
        pay_flags_rows = []
        for f in pay_flags:
            pay_flags_rows.append({
                "Severity": f["severity"].upper(),
                "Description": f["what"],
                "Where": f["where"],
                "Days Pending": f["magnitude"],
                "Lead Owner": f["owner"],
                "Corrective Action": f["action"],
            })
        st.dataframe(pd.DataFrame(pay_flags_rows), use_container_width=True, hide_index=True)
    else:
        st.info(f"No payment flags or billing delays active for Month {m}.")


# =============================================================================
# Tab 6: Quality
# =============================================================================
with tab_quality:
    st.caption("Synthetic data: illustrative rates, quantities and events.")

    qc = mv["qc_summary"]
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        st.metric("Total Inspections", qc["total_inspections"])
    with q2:
        st.metric("Quality Pass Rate", f"{qc['pass_rate'] * 100:.1f}%")
    with q3:
        st.metric("Open NCRs", qc["open_ncrs"])
    with q4:
        avg_d = f"{qc['average_closure_days']:.1f} days" if qc.get("average_closure_days") is not None else "N/A"
        st.metric("Avg NCR Closure Time", avg_d)

    st.divider()

    # Inspection Log with Result Filter
    st.subheader("Site Quality Inspection Log")
    inspections_df, ncrs_df = get_inspections_data(m)
    res_filter = st.selectbox("Filter inspections by result", ["All", "Pass", "Fail"])
    filtered_insp = inspections_df.copy()
    if res_filter != "All":
        filtered_insp = filtered_insp[filtered_insp["result"] == res_filter]

    insp_display = pd.DataFrame({
        "Inspection ID": filtered_insp["inspection_id"],
        "Date": filtered_insp["inspection_date"].map(format_date_str),
        "Activity": filtered_insp["activity_id"],
        "Check Type": filtered_insp["check_type"],
        "Result": filtered_insp["result"],
        "NCR ID": filtered_insp["ncr_id"].fillna("").map(lambda v: v if v else "-"),
    })
    st.dataframe(insp_display, use_container_width=True, hide_index=True)

    # NCR Log
    st.subheader("Non-Conformance Report (NCR) Register")
    if not ncrs_df.empty:
        ncr_display = pd.DataFrame({
            "NCR ID": ncrs_df["ncr_id"],
            "Inspection ID": ncrs_df["inspection_id"],
            "Activity": ncrs_df["activity_id"],
            "Check Type": ncrs_df["check_type"],
            "Non-Conformance Detail": ncrs_df["description"],
            "Raised Date": ncrs_df["raised_date"].map(format_date_str),
            "Closed Date": ncrs_df["closed_date"].map(lambda d: format_date_str(d) if d is not None else "Open"),
            "Status": ncrs_df["status"],
            "Days Open": ncrs_df["days_open"],
        })
        st.dataframe(ncr_display, use_container_width=True, hide_index=True)
    else:
        st.info("No non-conformance reports recorded.")


# =============================================================================
# Tab 7: Monthly Report
# =============================================================================
with tab_report:
    st.caption("Synthetic data: illustrative rates, quantities and events.")

    st.subheader("One-page report for the Regional Project Head")
    st.write(
        "Download the official executive 1-page PDF progress report or the complete "
        "audit-ready Excel workbook featuring live dynamic EVM and budget formulas."
    )

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        pdf_data = get_pdf_bytes(m)
        st.download_button(
            label=f"Download Month {m} PDF Report (1-Page Executive)",
            data=pdf_data,
            file_name=f"report_month_{m:02d}.pdf",
            mime="application/pdf",
        )
    with col_d2:
        wb_data = get_workbook_bytes()
        st.download_button(
            label="Download Complete Project Excel Workbook",
            data=wb_data,
            file_name="workbook.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
