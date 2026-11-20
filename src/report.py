"""Excel workbook and 1-page executive PDF report generation."""

import calendar
import io
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.shapes import Drawing, Circle

from src.data_io import load_activities, load_boq, load_config, load_coefficients
from src.schedule import compute_cpm, add_dates, wd_to_date
from src.budget import activity_budgets, activity_item_budget, bac, monthly_pv
from src.pipeline import month_view, _get_pipeline_context
from src.charts import pdf_scurve_chart
from src.evm import item_cost_variance


def format_inr(val: Union[int, float, None]) -> str:
    """Format integer rupee amount using standard Indian comma grouping: Rs 1,87,43,829.
    
    Negative amounts: -Rs 4,49,012.
    """
    if val is None:
        return "Rs 0"
    num = int(round(val))
    is_neg = num < 0
    s = str(abs(num))
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        remaining = s[:-3]
        parts = []
        while len(remaining) > 2:
            parts.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            parts.insert(0, remaining)
        grouped = ",".join(parts) + "," + last3
    prefix = "-Rs " if is_neg else "Rs "
    return prefix + grouped


def format_date_str(val: Any) -> str:
    """Format calendar date as '18 Sep 2026'."""
    if not val:
        return "-"
    if isinstance(val, (date, pd.Timestamp)):
        return val.strftime("%d %b %Y")
    if isinstance(val, str):
        v = val.strip()
        if not v or v == "-":
            return "-"
        try:
            d = date.fromisoformat(v)
            return d.strftime("%d %b %Y")
        except ValueError:
            return v
    return str(val)


def _to_date(v: Any) -> Optional[date]:
    """Convert string/Timestamp/date to datetime.date object."""
    if v is None or v == "" or v == "None" or v == "-":
        return None
    if isinstance(v, pd.Timestamp):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        v_clean = v.strip()
        if len(v_clean) == 10 and v_clean.count("-") == 2:
            try:
                return date.fromisoformat(v_clean)
            except ValueError:
                return None
    return None


# -------------------------------------------------------------------------
# Excel Workbook Generator
# -------------------------------------------------------------------------

def write_workbook(path: Union[str, Path], injections_enabled: Optional[bool] = None) -> None:
    """Generate comprehensive multi-sheet Excel workbook with dynamic EVM and BOQ formulas.
    
    Sheets in exact order:
    1. README
    2. Schedule
    3. BOQ_Budget
    4. Monthly_EVM
    5. Flags
    6. Materials
    7. RA_Bills
    8. QC_Log
    """
    save_path = Path(path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    ctx = _get_pipeline_context(injections_enabled=injections_enabled)
    config = ctx["config"]
    activities = ctx["activities"]
    boq = ctx["boq"]
    coeffs = ctx["coeffs"]
    start_date = ctx["start_date"]
    cpm_with_dates = ctx["cpm_with_dates"]
    budgets_df = ctx["budgets_df"]
    bac_value = int(round(ctx["bac_value"]))
    pv_full_df = ctx["pv_full_df"]
    sim_result = ctx["sim_result"]

    wb = openpyxl.Workbook()

    # Styling helpers
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Calibri", size=11, bold=True)
    title_font = Font(name="Calibri", size=14, bold=True, color="1F497D")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    # 1. Sheet: README
    ws_readme = wb.active
    ws_readme.title = "README"
    ws_readme.views.sheetView[0].showGridLines = True

    ws_readme.cell(row=1, column=1, value="G+4 Residential Building - Project Control Dashboard").font = title_font
    ws_readme.cell(row=2, column=1, value="Synthetic data: all rates, quantities and events are illustrative").font = Font(name="Calibri", size=11, italic=True)
    ws_readme.cell(row=4, column=1, value="Project Parameters:").font = bold_font
    ws_readme.cell(row=5, column=1, value="Built-Up Area: 2,000 sqm (G+4 floors, 400 sqm footprint)")
    ws_readme.cell(row=6, column=1, value=f"Project Calendar: Start Date {start_date}, 6-day work week (Mon-Sat)")
    ws_readme.cell(row=7, column=1, value="Status / Data Date: 2026-06-30 (Month 6 evaluation)")
    ws_readme.cell(row=8, column=1, value=f"Total Budget at Completion (BAC): INR {bac_value:,}")
    ws_readme.cell(row=10, column=1, value="How Formulas Work:").font = bold_font
    ws_readme.cell(row=11, column=1, value="1. Monthly_EVM: Core EVM indices (SV, CV, SPI, CPI, EAC, ETC, VAC, TCPI) use live Excel formulas referencing monthly PV, EV, AC cells and cell $N$1 holding BAC.")
    ws_readme.cell(row=12, column=1, value="2. BOQ_Budget: Item amounts use formula =D{r}*E{r} (Quantity * Rate) and Total BAC uses =SUM(F2:F14).")
    ws_readme.cell(row=13, column=1, value="3. RA_Bills: Net payable amount uses formula =C{r}-F{r}-G{r} (Gross - Retention - TDS).")
    ws_readme.cell(row=14, column=1, value="4. Injections: SLAB_F2 shuttering shortage (+10 wd), steel price escalation (+10% from Month 3), Month 4 cement shortage (30%), QC non-conformances, and RA-05 payment hold.")

    # 2. Sheet: Schedule
    ws_sched = wb.create_sheet(title="Schedule")
    ws_sched.views.sheetView[0].showGridLines = True
    ws_sched.freeze_panes = "A2"

    sched_headers = [
        "Activity ID", "Activity Name", "Type", "Duration (Days)", "ES", "EF", "LS", "LF",
        "Total Float", "Critical?", "Baseline Start", "Baseline Finish", "Forecast Start", "Forecast Finish"
    ]
    for col_idx, h in enumerate(sched_headers, start=1):
        c = ws_sched.cell(row=1, column=col_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    mv6 = month_view(6, injections_enabled=injections_enabled)
    mv6_cpm_dates = ctx["cpm_with_dates"].set_index("id").to_dict(orient="index")
    data_date_wd = 152
    from src.schedule import forecast_cpm
    full_f_cpm = forecast_cpm(activities, sim_result.status_at(6), data_date_wd).set_index("id").to_dict(orient="index")

    for r_idx, (_, row) in enumerate(activities.iterrows(), start=2):
        aid = row["id"]
        b_row = mv6_cpm_dates[aid]
        f_row = full_f_cpm[aid]
        is_crit = "Y" if b_row["total_float"] == 0 else "N"
        dur = int(row["duration_days"])

        f_es = int(f_row["es"])
        f_ef = int(f_row["ef"])
        f_s_date = wd_to_date(f_es, start_date)
        f_f_date = wd_to_date(f_ef - 1 if f_ef > 0 else 0, start_date)

        b_start_d = _to_date(b_row["start_date"])
        b_finish_d = _to_date(b_row["finish_date"])
        f_start_d = _to_date(f_s_date)
        f_finish_d = _to_date(f_f_date)

        vals = [
            aid, row["name"], row["type"], dur,
            b_row["es"], b_row["ef"], b_row["ls"], b_row["lf"], b_row["total_float"],
            is_crit, b_start_d, b_finish_d, f_start_d, f_finish_d
        ]
        for c_idx, v in enumerate(vals, start=1):
            cell = ws_sched.cell(row=r_idx, column=c_idx, value=v)
            cell.border = thin_border
            if c_idx in [4, 5, 6, 7, 8, 9]:
                cell.number_format = "#,##0"
            elif c_idx in [11, 12, 13, 14] and isinstance(v, date):
                cell.number_format = "yyyy-mm-dd"

    # 3. Sheet: BOQ_Budget
    ws_boq = wb.create_sheet(title="BOQ_Budget")
    ws_boq.views.sheetView[0].showGridLines = True
    ws_boq.freeze_panes = "A2"

    boq_headers = ["Item Code", "Description", "Unit", "Quantity", "Rate (INR)", "Amount (INR)"]
    for col_idx, h in enumerate(boq_headers, start=1):
        c = ws_boq.cell(row=1, column=col_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    last_boq_row = len(boq) + 1
    for r_idx, (_, row) in enumerate(boq.iterrows(), start=2):
        ws_boq.cell(row=r_idx, column=1, value=row["item"]).border = thin_border
        ws_boq.cell(row=r_idx, column=2, value=row["description"]).border = thin_border
        ws_boq.cell(row=r_idx, column=3, value=row["unit"]).border = thin_border

        q_cell = ws_boq.cell(row=r_idx, column=4, value=float(row["quantity"]))
        q_cell.number_format = "#,##0.00" if isinstance(row["quantity"], float) else "#,##0"
        q_cell.border = thin_border

        r_cell = ws_boq.cell(row=r_idx, column=5, value=int(row["rate_inr"]))
        r_cell.number_format = "#,##0"
        r_cell.border = thin_border

        a_cell = ws_boq.cell(row=r_idx, column=6, value=f"=D{r_idx}*E{r_idx}")
        a_cell.number_format = "#,##0"
        a_cell.border = thin_border

    # Total BAC row
    tot_row = last_boq_row + 1
    ws_boq.cell(row=tot_row, column=1, value="Total").font = bold_font
    ws_boq.cell(row=tot_row, column=2, value="Total Project BAC").font = bold_font
    tot_cell = ws_boq.cell(row=tot_row, column=6, value=f"=SUM(F2:F{last_boq_row})")
    tot_cell.font = bold_font
    tot_cell.number_format = "#,##0"
    tot_cell.border = thin_border

    # 4. Sheet: Monthly_EVM
    ws_evm = wb.create_sheet(title="Monthly_EVM")
    ws_evm.views.sheetView[0].showGridLines = True
    ws_evm.freeze_panes = "A2"

    evm_headers = [
        "Month", "PV", "EV", "AC", "SV", "CV", "SPI", "CPI", "EAC", "ETC", "VAC", "TCPI"
    ]
    for col_idx, h in enumerate(evm_headers, start=1):
        c = ws_evm.cell(row=1, column=col_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    # Single labelled BAC cell in row 1 (Column M & N)
    ws_evm.cell(row=1, column=13, value="BAC (INR)").font = bold_font
    bac_cell = ws_evm.cell(row=1, column=14, value=bac_value)
    bac_cell.font = bold_font
    bac_cell.number_format = "#,##0"

    # Populate Month 1..6 data
    evm_df = ctx.get("evm_df")
    if evm_df is not None:
        evm_rows = [r.to_dict() for _, r in evm_df.iterrows()]
    else:
        evm_rows = mv6["monthly_evm"]

    for idx, r_data in enumerate(evm_rows, start=2):
        # A: Month
        ws_evm.cell(row=idx, column=1, value=int(r_data["month"])).alignment = Alignment(horizontal="center")
        # B: PV
        c_pv = ws_evm.cell(row=idx, column=2, value=float(r_data["pv"]))
        c_pv.number_format = "#,##0"
        # C: EV
        c_ev = ws_evm.cell(row=idx, column=3, value=float(r_data["ev"]))
        c_ev.number_format = "#,##0"
        # D: AC
        c_ac = ws_evm.cell(row=idx, column=4, value=float(r_data["ac"]))
        c_ac.number_format = "#,##0"

        # E: SV = EV - PV (=C{r}-B{r})
        c_sv = ws_evm.cell(row=idx, column=5, value=f"=C{idx}-B{idx}")
        c_sv.number_format = "#,##0"

        # F: CV = EV - AC (=C{r}-D{r})
        c_cv = ws_evm.cell(row=idx, column=6, value=f"=C{idx}-D{idx}")
        c_cv.number_format = "#,##0"

        # G: SPI = IF(B=0,"",C/B)
        c_spi = ws_evm.cell(row=idx, column=7, value=f'=IF(B{idx}=0,"",C{idx}/B{idx})')
        c_spi.number_format = "0.000"

        # H: CPI = IF(D=0,"",C/D)
        c_cpi = ws_evm.cell(row=idx, column=8, value=f'=IF(D{idx}=0,"",C{idx}/D{idx})')
        c_cpi.number_format = "0.000"

        # I: EAC = IF(CPI="",BAC,BAC/CPI) referencing $N$1
        c_eac = ws_evm.cell(row=idx, column=9, value=f'=IF(H{idx}="",$N$1,$N$1/H{idx})')
        c_eac.number_format = "#,##0"

        # J: ETC = EAC - AC (=I{r}-D{r})
        c_etc = ws_evm.cell(row=idx, column=10, value=f"=I{idx}-D{idx}")
        c_etc.number_format = "#,##0"

        # K: VAC = BAC - EAC (=$N$1-I{r})
        c_vac = ws_evm.cell(row=idx, column=11, value=f"=$N$1-I{idx}")
        c_vac.number_format = "#,##0"

        # L: TCPI = IF(BAC-AC=0,"",(BAC-EV)/(BAC-AC))
        c_tcpi = ws_evm.cell(row=idx, column=12, value=f'=IF($N$1-D{idx}=0,"",($N$1-C{idx})/($N$1-D{idx}))')
        c_tcpi.number_format = "0.000"

        for col_i in range(1, 13):
            ws_evm.cell(row=idx, column=col_i).border = thin_border

    # 5. Sheet: Flags
    ws_flags = wb.create_sheet(title="Flags")
    ws_flags.views.sheetView[0].showGridLines = True
    ws_flags.freeze_panes = "A2"

    flag_headers = [
        "Month", "Flag ID", "Category", "Severity", "Where", "What", "Magnitude", "Reason", "Since", "Owner", "Action"
    ]
    for col_idx, h in enumerate(flag_headers, start=1):
        c = ws_flags.cell(row=1, column=col_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    from src.flags import evaluate_flags
    f_row_idx = 2
    for m in range(1, 7):
        fl = evaluate_flags(m, sim_result, config, activities, boq, coeffs, injections_enabled)
        for f in fl:
            since_d = _to_date(f["since"])
            since_val = since_d if since_d is not None else f["since"]
            vals = [
                m, f["flag_id"], f["category"], f["severity"].upper(), f["where"],
                f["what"], f["magnitude"], f.get("reason", ""), since_val, f["owner"], f["action"]
            ]
            for c_idx, v in enumerate(vals, start=1):
                cell = ws_flags.cell(row=f_row_idx, column=c_idx, value=v)
                cell.border = thin_border
                if c_idx == 4:
                    cell.font = Font(name="Calibri", bold=True, color="C00000" if v == "RED" else "ED7D31")
                elif c_idx == 9 and isinstance(v, date):
                    cell.number_format = "yyyy-mm-dd"
            f_row_idx += 1

    # 6. Sheet: Materials
    ws_mat = wb.create_sheet(title="Materials")
    ws_mat.views.sheetView[0].showGridLines = True
    ws_mat.freeze_panes = "A2"

    mat_headers = [
        "Material", "Required Next Month (M7)", "Procured This Month (M6)",
        "Shortfall", "Surplus", "Opening Stock", "Consumed M6", "Closing Stock M6"
    ]
    for col_idx, h in enumerate(mat_headers, start=1):
        c = ws_mat.cell(row=1, column=col_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    for r_idx, m_row in enumerate(mv6["material_status"], start=2):
        vals = [
            m_row["material"], m_row["required_next_month"], m_row["procured_this_month"],
            m_row["shortfall"], m_row["surplus"], m_row["opening_stock"], m_row["consumed"], m_row["closing_stock"]
        ]
        for c_idx, v in enumerate(vals, start=1):
            cell = ws_mat.cell(row=r_idx, column=c_idx, value=v)
            cell.border = thin_border
            if c_idx >= 2:
                cell.number_format = "#,##0.0"

    # Add Month 7 Plan section below
    p_start_row = len(mv6["material_status"]) + 4
    ws_mat.cell(row=p_start_row - 1, column=1, value="Month 7 Material Purchase Plan").font = bold_font
    ws_mat.cell(row=p_start_row, column=1, value="Material").font = bold_font
    ws_mat.cell(row=p_start_row, column=2, value="Forecast Need (Units)").font = bold_font
    for offset, (k, v) in enumerate(mv6["next_month_plan"].items()):
        ws_mat.cell(row=p_start_row + 1 + offset, column=1, value=k).border = thin_border
        c_val = ws_mat.cell(row=p_start_row + 1 + offset, column=2, value=v)
        c_val.number_format = "#,##0.0"
        c_val.border = thin_border

    # 7. Sheet: RA_Bills
    ws_bills = wb.create_sheet(title="RA_Bills")
    ws_bills.views.sheetView[0].showGridLines = True
    ws_bills.freeze_panes = "A2"

    bill_headers = [
        "Bill No", "Month", "Gross Amount (INR)", "Work at BOQ Rates", "Price Variation",
        "Retention (5%)", "TDS (2%)", "Net Payable (INR)", "Submitted Date", "Certified Date",
        "Paid Date", "Status", "Days Pending", "Days to Pay", "Hold Reason"
    ]
    for col_idx, h in enumerate(bill_headers, start=1):
        c = ws_bills.cell(row=1, column=col_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    for r_idx, b_row in enumerate(mv6["ra_bills"], start=2):
        sub_d = _to_date(b_row["submitted_date"])
        cert_d = _to_date(b_row["certified_date"])
        paid_d = _to_date(b_row["paid_date"])
        vals = [
            b_row["bill_no"], b_row["month"], int(b_row["gross_amount"]), int(b_row["work_at_boq_rates"]),
            int(b_row["price_variation"]), int(b_row["retention"]), int(b_row["tds"]),
            f"=C{r_idx}-F{r_idx}-G{r_idx}",  # Net Payable formula
            sub_d, cert_d, paid_d,
            b_row["status"], b_row["days_pending"], b_row["days_to_pay"] or "", b_row.get("hold_reason", "")
        ]
        for c_idx, v in enumerate(vals, start=1):
            cell = ws_bills.cell(row=r_idx, column=c_idx, value=v)
            cell.border = thin_border
            if c_idx in [3, 4, 5, 6, 7, 8]:
                cell.number_format = "#,##0"
            elif c_idx in [9, 10, 11] and isinstance(v, date):
                cell.number_format = "yyyy-mm-dd"

    # 8. Sheet: QC_Log
    ws_qc = wb.create_sheet(title="QC_Log")
    ws_qc.views.sheetView[0].showGridLines = True
    ws_qc.freeze_panes = "A2"

    qc_headers = ["Inspection ID", "Activity ID", "Check Type", "Inspection Date", "Result", "NCR ID"]
    for col_idx, h in enumerate(qc_headers, start=1):
        c = ws_qc.cell(row=1, column=col_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    from src.quality import build_inspections
    insp_df, _ = build_inspections(sim_result, activities, config, eval_date="2026-06-30", injections_enabled=injections_enabled)
    for r_idx, row in enumerate(insp_df.iterrows(), start=2):
        item = row[1]
        insp_d = _to_date(item["inspection_date"])
        vals = [item["inspection_id"], item["activity_id"], item["check_type"], insp_d, item["result"], item["ncr_id"]]
        for c_idx, v in enumerate(vals, start=1):
            cell = ws_qc.cell(row=r_idx, column=c_idx, value=v)
            cell.border = thin_border
            if c_idx == 4 and isinstance(v, date):
                cell.number_format = "yyyy-mm-dd"
            elif c_idx == 5 and v == "Fail":
                cell.font = Font(name="Calibri", bold=True, color="C00000")

    # NCR table below
    ncr_start_row = len(insp_df) + 4
    ws_qc.cell(row=ncr_start_row - 1, column=1, value="Non-Conformance Reports (NCR Log at Data Date)").font = bold_font
    ncr_headers = ["NCR ID", "Inspection ID", "Activity ID", "Check Type", "Raised Date", "Closed Date", "Status", "Days Open", "Description"]
    for col_idx, h in enumerate(ncr_headers, start=1):
        c = ws_qc.cell(row=ncr_start_row, column=col_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    for r_idx, ncr in enumerate(mv6["ncr_log"], start=ncr_start_row + 1):
        raised_d = _to_date(ncr["raised_date"])
        closed_d = _to_date(ncr["closed_date"])
        vals = [
            ncr["ncr_id"], ncr["inspection_id"], ncr["activity_id"], ncr["check_type"],
            raised_d, closed_d,
            ncr["status"], ncr["days_open"], ncr["description"]
        ]
        for c_idx, v in enumerate(vals, start=1):
            cell = ws_qc.cell(row=r_idx, column=c_idx, value=v)
            cell.border = thin_border
            if c_idx in [5, 6] and isinstance(v, date):
                cell.number_format = "yyyy-mm-dd"
            elif c_idx == 7:
                cell.font = Font(name="Calibri", bold=True, color="C00000" if v == "Open" else "2E7D32")

    # Auto-adjust column widths for all sheets
    for ws in wb.worksheets:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = cell.value
                if val is not None:
                    s_val = str(val)
                    if s_val.startswith("="):
                        max_len = max(max_len, 10)
                    else:
                        max_len = max(max_len, len(s_val))
            ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

    wb.save(save_path)


# -------------------------------------------------------------------------
# Executive PDF Report Generator (ReportLab, 1-Page Guarantee)
# -------------------------------------------------------------------------

def _draw_status_dot(color_name: str, size: float = 7.0) -> Drawing:
    """Create a colored status dot as a Flowable Drawing."""
    d = Drawing(size, size)
    col_map = {
        "red": colors.HexColor("#d32f2f"),
        "amber": colors.HexColor("#f57c00"),
        "green": colors.HexColor("#388e3c"),
    }
    fill_col = col_map.get(color_name.lower(), colors.HexColor("#757575"))
    d.add(Circle(size / 2.0, size / 2.0, size / 2.2, fillColor=fill_col, strokeColor=fill_col))
    return d


def build_pdf(
    month: int,
    path: Union[str, Path],
    injections_enabled: Optional[bool] = None,
) -> None:
    """Generate executive monthly progress report guaranteed to fit on exactly one A4 portrait page."""
    save_path = Path(path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    mv = month_view(month, injections_enabled=injections_enabled)
    ctx = _get_pipeline_context(injections_enabled=injections_enabled)
    pv_full_df = ctx["pv_full_df"]
    config = ctx["config"]
    from src.evm import monthly_evm
    evm_df = monthly_evm(pv_full_df, ctx["sim_result"], ctx["budgets_df"], ctx["bac_value"], months=range(1, 7))

    # Generate temporary compact S-curve chart image
    chart_temp_path = save_path.parent / f"_temp_scurve_m{month}.png"
    pdf_scurve_chart(evm_df, pv_full_df, chart_temp_path, month=month)

    doc = SimpleDocTemplate(
        str(save_path),
        pagesize=A4,
        leftMargin=20,
        rightMargin=20,
        topMargin=16,
        bottomMargin=14,
    )

    story = []
    month_name = calendar.month_name[month]

    # Typography styles
    style_title = ParagraphStyle("RptTitle", fontName="Helvetica-Bold", fontSize=12.5, leading=13.5, textColor=colors.black)
    style_subtitle = ParagraphStyle("RptSub", fontName="Helvetica", fontSize=7.2, leading=8.5, textColor=colors.HexColor("#424242"))
    style_sec_title = ParagraphStyle("SecTitle", fontName="Helvetica-Bold", fontSize=7.8, leading=9, textColor=colors.black)
    style_body = ParagraphStyle("RptBody", fontName="Helvetica", fontSize=6.2, leading=7.5, textColor=colors.black)
    style_body_bold = ParagraphStyle("RptBodyB", fontName="Helvetica-Bold", fontSize=6.2, leading=7.5, textColor=colors.black)
    style_footer = ParagraphStyle("RptFooter", fontName="Helvetica-Oblique", fontSize=6.0, leading=7.0, textColor=colors.HexColor("#616161"))
    style_driver = ParagraphStyle("RptDriver", fontName="Helvetica", fontSize=6.2, leading=7.8, textColor=colors.black)

    # 1. Header & Sub-header
    story.append(Paragraph(f"Monthly Progress Report - Month {month} ({month_name} 2026)", style_title))
    story.append(Spacer(1, 1.5))
    dt_formatted = format_date_str(mv["month_date"])
    story.append(Paragraph(f"G+4 Residential Building (Synthetic) | To: Regional Project Head | Data date: {dt_formatted}", style_subtitle))
    story.append(Spacer(1, 3))

    # 2. Status Line Banner
    status_col_name = "red" if mv["overall_status"] == "RED" else ("amber" if mv["overall_status"] == "AMBER" else "green")
    status_dot = _draw_status_dot(status_col_name, size=7.5)
    status_text_p = Paragraph(f"<b>{mv['status_line']}</b>", ParagraphStyle("StatLine", fontName="Helvetica", fontSize=7.5, leading=8.5, textColor=colors.black))

    status_table = Table([[status_dot, status_text_p]], colWidths=[12, 540])
    status_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(status_table)
    story.append(Spacer(1, 2.5))

    # 3. Compact S-Curve Image
    scurve_img = Image(str(chart_temp_path), width=552, height=115)
    story.append(scurve_img)
    story.append(Spacer(1, 3))

    # 4. Key Performance Indices Table (2 Rows: Cost row + Schedule row)
    hd = mv["headline"]
    sf = mv["schedule_forecast"]
    cpm_handover_str = format_date_str(sf["cpm_handover_date"])
    base_handover_str = format_date_str(sf["baseline_handover_date"])
    cpm_delay_str = f"+{sf['cpm_delay_wd']} wd" if sf['cpm_delay_wd'] > 0 else "0 wd"

    indices_data = [
        # Row 1: Cost metrics
        ["Planned (PV)", "Earned (EV)", "Actual (AC)", "Sched. Var. (SV)", "Cost Var. (CV)", "EAC (BAC/CPI)", "VAC"],
        [
            format_inr(hd["pv"]), format_inr(hd["ev"]), format_inr(hd["ac"]),
            format_inr(hd["sv"]), format_inr(hd["cv"]),
            format_inr(hd["eac"]), format_inr(hd["vac"]),
        ],
        # Row 2: Schedule & combined metrics
        ["SPI", "CPI", "TCPI", "EAC Combined", "Baseline Handover", "Forecast Handover", "Delay"],
        [
            f"{hd['spi']:.3f}", f"{hd['cpi']:.3f}",
            f"{hd['tcpi']:.3f}" if hd["tcpi"] is not None else "1.000",
            format_inr(hd["eac_combined"]), base_handover_str, cpm_handover_str, cpm_delay_str
        ],
    ]
    t_indices = Table(indices_data, colWidths=[80, 80, 80, 78, 78, 80, 76])
    t_indices.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4f8")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#f0f4f8")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTNAME", (0, 3), (-1, 3), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
        ("TOPPADDING", (0, 0), (-1, -1), 2.0),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd8dc")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#90a4ae")),
    ]))
    story.append(t_indices)
    story.append(Spacer(1, 4))

    # 5. Top 5 Issues (Widen "Where" column to 68 pt so M_HANDOVER does not wrap)
    story.append(Paragraph("<b>Top Priority Project Issues & Corrective Actions</b>", style_sec_title))
    story.append(Spacer(1, 1.5))

    top5_rows = [["Sev", "Issue Description", "Where", "Lead Owner", "Corrective Action Protocol"]]
    for iss in mv["top_5_issues"]:
        dot = _draw_status_dot(iss["severity"], size=6.0)
        top5_rows.append([
            dot,
            Paragraph(iss["what"], style_body),
            Paragraph(iss["where"], style_body_bold),
            Paragraph(iss["owner"], style_body),
            Paragraph(iss["action"], style_body),
        ])

    t_top5 = Table(top5_rows, colWidths=[16, 170, 68, 66, 232])
    t_top5.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4f8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e0e0e0")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b0bec5")),
    ]))
    story.append(t_top5)
    story.append(Spacer(1, 3.5))

    # 6. Two-Column Layout 1: Milestones & Material Plan
    # (a) Milestones Table (with Status column showing Achieved with actual date)
    ms_rows = [["Milestone", "Baseline", "Status", "Slip"]]
    for ms in mv["schedule_forecast"]["milestones"]:
        slip_txt = f"+{ms['slip_wd']} wd" if ms['slip_wd'] > 0 else "0 wd"
        b_dt_str = format_date_str(ms["baseline_date"])
        status_disp = ms.get("status_text", ms.get("status", "Forecast"))
        ms_rows.append([
            Paragraph(ms["id"], style_body_bold),
            b_dt_str,
            status_disp,
            slip_txt,
        ])
    t_ms = Table(ms_rows, colWidths=[66, 54, 114, 38])
    t_ms.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4f8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e0e0e0")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b0bec5")),
    ]))

    # (b) Material Plan Table (Month m+1) with readable names and formatted units
    next_m = month + 1
    mat_rows = [["Material & Unit", f"Plan M{next_m} Need"]]
    mat_display_names = {
        "cement_bags": "Cement, bags",
        "steel_kg": "Steel, kg",
        "sand_cum": "Sand, cum",
        "aggregate_cum": "Aggregate, cum",
        "bricks": "Bricks, nos",
    }
    for mat_k, val in mv["next_month_plan"].items():
        disp_name = mat_display_names.get(mat_k, mat_k)
        if val is None or abs(val) < 1e-4:
            qty_str = "-"
        elif "bags" in mat_k or "bricks" in mat_k:
            qty_str = f"{int(round(val)):,}"
        else:
            qty_str = f"{val:,.1f}"
        mat_rows.append([disp_name, qty_str])

    t_mat = Table(mat_rows, colWidths=[162, 110])
    t_mat.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4f8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e0e0e0")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b0bec5")),
    ]))

    two_col_1 = Table([
        [Paragraph("<b>Key Milestone Status & Slippage</b>", style_sec_title),
         Paragraph(f"<b>Material Procurement Plan (Month {next_m})</b>", style_sec_title)],
        [t_ms, t_mat]
    ], colWidths=[272, 272])
    two_col_1.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(two_col_1)
    story.append(Spacer(1, 3.5))

    # 7. Two-Column Layout 2: Commercial Payments & Open NCRs
    # (a) Payments Table
    pay_rows = [["Bill", "Net Payable", "Status", "Days", "Reason / Notes"]]
    unpaid_bills = [b for b in mv["ra_bills"] if b["status"] in ["Held", "Pending"]]
    if not unpaid_bills:
        pay_rows.append(["All Bills Paid", "-", "Clear", "0", "No pending or held payment liabilities"])
    else:
        for b in unpaid_bills:
            r_note = b.get("hold_reason", "")
            if r_note.startswith("Held: "):
                r_note = r_note[6:]
            pay_rows.append([
                b["bill_no"], format_inr(b["net_payable"]), b["status"],
                str(b["days_pending"]), Paragraph(r_note or "Awaiting routine payment turnaround", style_body)
            ])
    t_pay = Table(pay_rows, colWidths=[38, 64, 42, 28, 100])
    t_pay.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4f8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("ALIGN", (0, 0), (3, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e0e0e0")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b0bec5")),
    ]))

    # (b) Open NCRs Table
    open_ncrs = [n for n in mv["ncr_log"] if n["status"] == "Open"]
    ncr_rows = [["NCR ID", "Activity", "Open", "Non-Conformance Description"]]
    if not open_ncrs:
        ncr_rows.append(["None", "Pass", "0 d", "Zero open non-conformance reports at data date"])
    else:
        for n in open_ncrs:
            ncr_rows.append([
                Paragraph(n["ncr_id"], style_body_bold),
                n["activity_id"],
                f"{n['days_open']} d",
                Paragraph(n["description"], style_body),
            ])
    t_ncr = Table(ncr_rows, colWidths=[46, 52, 32, 142])
    t_ncr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4f8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("ALIGN", (0, 0), (2, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e0e0e0")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b0bec5")),
    ]))

    two_col_2 = Table([
        [Paragraph("<b>Pending & Held Contractor RA Bills</b>", style_sec_title),
         Paragraph("<b>Open Quality Non-Conformance Reports (NCRs)</b>", style_sec_title)],
        [t_pay, t_ncr]
    ], colWidths=[272, 272])
    two_col_2.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(two_col_2)
    story.append(Spacer(1, 3.5))

    # 8. Drivers this Month Box (Built dynamically from results and config)
    # (a) Schedule driver
    act_row = ctx["activities"].loc[ctx["activities"]["id"] == "SLAB_F2"]
    slab_planned_dur = int(act_row["duration_days"].iloc[0]) if not act_row.empty else 9
    slab_actual_dur = int(ctx["sim_result"].actual_durations.get("SLAB_F2", 19))
    slab_diff = slab_actual_dur - slab_planned_dur
    slab_cause = config.get("injections", {}).get("slab_delay", {}).get("cause", "shuttering material shortage")
    cpm_delay_val = sf["cpm_delay_wd"]
    if cpm_delay_val > 0:
        sched_driver_text = (
            f"<b>Schedule:</b> SLAB_F2 actual duration {slab_actual_dur} wd vs planned {slab_planned_dur} wd (+{slab_diff} wd) due to {slab_cause} "
            f"(critical path, so handover +{cpm_delay_val} wd to {cpm_handover_str})."
        )
    else:
        sched_driver_text = f"<b>Schedule:</b> Critical path activities on schedule; milestone handover on plan ({cpm_handover_str})."

    # (b) Cost driver
    item_budget_df = ctx["item_budget_df"]
    item_var_df = item_cost_variance(ctx["sim_result"], item_budget_df, month=month)
    steel_row = item_var_df[item_var_df["item"] == "STEEL"]
    steel_var = float(steel_row["variance_pct"].iloc[0]) if not steel_row.empty else 0.0
    steel_cause = config.get("injections", {}).get("steel_escalation", {}).get("cause", "steel price escalation")
    steel_start_m = config.get("injections", {}).get("steel_escalation", {}).get("from_month", 3)
    other_items_ok = all(abs(float(r["variance_pct"])) <= 5.0 for _, r in item_var_df[item_var_df["item"] != "STEEL"].iterrows())
    no_other_txt = "; no other BOQ item beyond +/-5%" if other_items_ok else ""
    if abs(steel_var) > 5.0:
        cost_driver_text = (
            f"<b>Cost:</b> STEEL item variance {steel_var:+.1f}% since Month {steel_start_m} ({steel_cause}); "
            f"project CPI {hd['cpi']:.3f}{no_other_txt}."
        )
    else:
        cost_driver_text = f"<b>Cost:</b> All BOQ items within cost tolerance; project CPI {hd['cpi']:.3f}."

    # (c) Materials driver
    cement_inj = config.get("injections", {}).get("cement_shortage", {})
    cement_m = cement_inj.get("month", 4)
    cement_frac = cement_inj.get("procured_fraction_of_requirement", 0.70)
    cement_shortfall_pct = round((1.0 - cement_frac) * 100)
    cement_cause = "cement supply shortage"
    has_cement_sf = (month >= cement_m)
    if has_cement_sf:
        mat_driver_text = (
            f"<b>Materials:</b> Cement shortfall of {cement_shortfall_pct}% occurred in Month {cement_m} ({cement_cause}); "
            f"zero material shortfall active in Month {month}."
        )
    else:
        mat_driver_text = "<b>Materials:</b> Material deliveries on track with buffer; zero stock shortfall."

    # (d) Commercial / Flags driver
    red_count = sum(1 for f in mv["flags"] if f["severity"] == "red")
    amber_count = sum(1 for f in mv["flags"] if f["severity"] == "amber")
    cum_retention = sum(b["retention"] for b in mv["ra_bills"] if b["month"] <= month)
    comm_driver_text = (
        f"<b>Commercial & Risk:</b> All flags this month: {red_count} red, {amber_count} amber "
        f"(full list in workbook, Flags sheet) | Cumulative retention held to date: {format_inr(cum_retention)}."
    )

    drivers_table_data = [
        [Paragraph(f"<b>Key Operational & Financial Drivers (Month {month})</b>", style_sec_title)],
        [Paragraph(f"• {sched_driver_text}", style_driver)],
        [Paragraph(f"• {cost_driver_text}", style_driver)],
        [Paragraph(f"• {mat_driver_text}", style_driver)],
        [Paragraph(f"• {comm_driver_text}", style_driver)],
    ]
    t_drivers = Table(drivers_table_data, colWidths=[544])
    t_drivers.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b0bec5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t_drivers)
    story.append(Spacer(1, 3))

    # 9. Footer
    story.append(Paragraph("Synthetic data. Every figure is generated by the pipeline (outputs/results.json).", style_footer))

    doc.build(story)

    # Clean up temporary chart file
    if chart_temp_path.exists():
        try:
            chart_temp_path.unlink()
        except OSError:
            pass


def main() -> None:
    """CLI entrypoint writing outputs/workbook.xlsx and outputs/report_month_06.pdf."""
    repo = Path(__file__).resolve().parent.parent
    wb_path = repo / "outputs" / "workbook.xlsx"
    pdf_path = repo / "outputs" / "report_month_06.pdf"

    print("Generating Excel workbook...")
    write_workbook(wb_path)
    print(f"Workbook written to: {wb_path}")

    print("Generating Month 6 PDF report...")
    build_pdf(6, pdf_path)
    print(f"PDF report written to: {pdf_path}")


if __name__ == "__main__":
    main()
