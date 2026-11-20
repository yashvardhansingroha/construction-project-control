"""Tests for workbook generation, dynamic Excel formulas, formatting, and 1-page PDF reports."""

from datetime import date, datetime
from pathlib import Path
import openpyxl
import pypdf
import pytest

from src.data_io import load_activities, load_boq, load_config
from src.budget import activity_budgets, bac, monthly_pv
from src.schedule import compute_cpm, add_dates
from src.simulate import simulate
from src.evm import monthly_evm
from src.report import format_inr, write_workbook, build_pdf

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_format_inr():
    """Verify Indian rupee formatting with comma grouping and negative signs."""
    assert format_inr(18743829) == "Rs 1,87,43,829"
    assert format_inr(930000) == "Rs 9,30,000"
    assert format_inr(-449012) == "-Rs 4,49,012"
    assert format_inr(0) == "Rs 0"
    assert format_inr(None) == "Rs 0"
    assert format_inr(100) == "Rs 100"
    assert format_inr(1000) == "Rs 1,000"
    assert format_inr(100000) == "Rs 1,00,000"
    assert format_inr(10000000) == "Rs 1,00,00,000"
    assert format_inr(-10000000) == "-Rs 1,00,00,000"


def test_workbook_structure_and_sheets(tmp_path):
    """Verify workbook opens, 8 sheets exist in exact order, README mentions Synthetic, freeze panes set."""
    wb_path = tmp_path / "test_wb.xlsx"
    write_workbook(wb_path)

    wb = openpyxl.load_workbook(wb_path, data_only=False)
    expected_sheets = [
        "README", "Schedule", "BOQ_Budget", "Monthly_EVM",
        "Flags", "Materials", "RA_Bills", "QC_Log"
    ]
    assert wb.sheetnames == expected_sheets

    # README mentions Synthetic
    ws_readme = wb["README"]
    readme_text = " ".join(str(cell.value) for row in ws_readme.iter_rows() for cell in row if cell.value)
    assert "synthetic" in readme_text.lower()

    # Freeze panes set on every data sheet
    data_sheets = ["Schedule", "BOQ_Budget", "Monthly_EVM", "Flags", "Materials", "RA_Bills", "QC_Log"]
    for s_name in data_sheets:
        ws = wb[s_name]
        assert ws.freeze_panes is not None, f"Freeze panes not set on {s_name}"
        assert ws.freeze_panes in ["A2", "B2"], f"Unexpected freeze pane {ws.freeze_panes} on {s_name}"


def _eval_evm_cell_formula(formula: str, row_idx: int, ws) -> float:
    """Evaluate an EVM Excel formula string using the worksheet cell values."""
    f = formula.strip().lstrip("=")
    bac_val = float(ws["N1"].value)
    pv_val = float(ws[f"B{row_idx}"].value)
    ev_val = float(ws[f"C{row_idx}"].value)
    ac_val = float(ws[f"D{row_idx}"].value)

    if f == f"C{row_idx}-B{row_idx}":
        return ev_val - pv_val
    elif f == f"C{row_idx}-D{row_idx}":
        return ev_val - ac_val
    elif f == f'IF(B{row_idx}=0,"",C{row_idx}/B{row_idx})':
        return ev_val / pv_val if pv_val != 0 else None
    elif f == f'IF(D{row_idx}=0,"",C{row_idx}/D{row_idx})':
        return ev_val / ac_val if ac_val != 0 else None
    elif f == f'IF(H{row_idx}="",$N$1,$N$1/H{row_idx})':
        cpi = ev_val / ac_val if ac_val != 0 else None
        return bac_val / cpi if cpi is not None else bac_val
    elif f == f"I{row_idx}-D{row_idx}":
        cpi = ev_val / ac_val if ac_val != 0 else None
        eac = bac_val / cpi if cpi is not None else bac_val
        return eac - ac_val
    elif f == f"$N$1-I{row_idx}":
        cpi = ev_val / ac_val if ac_val != 0 else None
        eac = bac_val / cpi if cpi is not None else bac_val
        return bac_val - eac
    elif f == f'IF($N$1-D{row_idx}=0,"",($N$1-C{row_idx})/($N$1-D{row_idx}))':
        denom = bac_val - ac_val
        return (bac_val - ev_val) / denom if denom != 0 else None
    else:
        raise ValueError(f"Unrecognized EVM formula at row {row_idx}: {formula}")


def test_monthly_evm_formulas_and_evaluation(tmp_path):
    """Verify Monthly_EVM formulas in rows 2-7, single BAC cell in row 1, and evaluation matches monthly_evm."""
    wb_path = tmp_path / "test_wb.xlsx"
    write_workbook(wb_path)

    wb = openpyxl.load_workbook(wb_path, data_only=False)
    ws = wb["Monthly_EVM"]

    # BAC cell check: single labelled cell in row 1, not duplicated in row 2
    assert ws["M1"].value == "BAC (INR)"
    assert ws["N1"].value == 38113500
    assert ws["M2"].value is None, "BAC label must not appear in row 2"
    assert ws["N2"].value is None, "BAC value must not appear in row 2"

    # Load baseline calculation for comparison
    activities = load_activities()
    boq = load_boq()
    budgets_df = activity_budgets(activities, boq)
    bac_val = bac(activities, boq)
    cpm_df = compute_cpm(activities)
    cpm_dates = add_dates(cpm_df, "2026-01-05")
    pv_df = monthly_pv(cpm_dates, budgets_df, "2026-01-05")
    config = load_config()
    sim = simulate(config, activities, boq, through_month=6)
    evm_df = monthly_evm(pv_df, sim, budgets_df, bac_val)

    metric_cols = [
        ("sv", 5), ("cv", 6), ("spi", 7), ("cpi", 8),
        ("eac", 9), ("etc", 10), ("vac", 11), ("tcpi", 12)
    ]

    for idx, r in enumerate(range(2, 8)):
        expected_row = evm_df.iloc[idx]
        for metric_name, col_idx in metric_cols:
            cell_formula = ws.cell(r, col_idx).value
            assert isinstance(cell_formula, str) and cell_formula.startswith("="), (
                f"Cell ({r}, {col_idx}) value {cell_formula} is not an Excel formula string"
            )
            # Evaluate formula in Python from the cell values
            eval_val = _eval_evm_cell_formula(cell_formula, r, ws)
            expected_val = expected_row[metric_name]
            if expected_val is None:
                assert eval_val is None
            else:
                assert eval_val == pytest.approx(expected_val, rel=1e-6, abs=1e-6), (
                    f"Row {r} metric {metric_name}: evaluated {eval_val} != expected {expected_val}"
                )


def test_workbook_date_cell_types(tmp_path):
    """Verify that dates in Schedule, RA_Bills, and QC_Log are stored as real date/datetime instances."""
    wb_path = tmp_path / "test_wb.xlsx"
    write_workbook(wb_path)

    wb = openpyxl.load_workbook(wb_path, data_only=False)

    # 1. Schedule dates (columns 11, 12, 13, 14)
    ws_sched = wb["Schedule"]
    for col_idx in [11, 12, 13, 14]:
        val = ws_sched.cell(2, col_idx).value
        assert isinstance(val, (date, datetime)), f"Schedule col {col_idx} is {type(val)}, expected date/datetime"

    # 2. RA_Bills dates (columns 9, 10 for submitted and certified dates)
    ws_ra = wb["RA_Bills"]
    for col_idx in [9, 10]:
        val = ws_ra.cell(2, col_idx).value
        assert isinstance(val, (date, datetime)), f"RA_Bills col {col_idx} is {type(val)}, expected date/datetime"

    # 3. QC_Log dates (inspection date col 4, raised date in NCR table col 5)
    ws_qc = wb["QC_Log"]
    val_insp = ws_qc.cell(2, 4).value
    assert isinstance(val_insp, (date, datetime)), f"QC_Log insp date is {type(val_insp)}, expected date/datetime"


def test_boq_and_ra_formulas(tmp_path):
    """Verify BOQ_Budget sum formula and RA_Bills net payable formula."""
    wb_path = tmp_path / "test_wb.xlsx"
    write_workbook(wb_path)

    wb = openpyxl.load_workbook(wb_path, data_only=False)

    # 1. BOQ_Budget
    ws_boq = wb["BOQ_Budget"]
    # Check item amount formulas =D{r}*E{r}
    for r in range(2, ws_boq.max_row):
        amt_f = ws_boq.cell(r, 6).value
        assert amt_f == f"=D{r}*E{r}", f"BOQ row {r} amount formula unexpected: {amt_f}"

    total_f = ws_boq.cell(ws_boq.max_row, 6).value
    assert isinstance(total_f, str) and total_f.startswith("=SUM("), f"BOQ total formula unexpected: {total_f}"

    # 2. RA_Bills
    ws_ra = wb["RA_Bills"]
    for r in range(2, 8):
        net_f = ws_ra.cell(r, 8).value
        assert net_f == f"=C{r}-F{r}-G{r}", f"RA bill row {r} net payable formula unexpected: {net_f}"


def test_pdf_single_page_months_1_3_6(tmp_path):
    """Verify executive PDF report fits strictly on 1 page for months 1, 3, and 6."""
    for m in [1, 3, 6]:
        pdf_path = tmp_path / f"report_month_{m:02d}.pdf"
        build_pdf(m, pdf_path)
        assert pdf_path.exists()
        reader = pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == 1, f"Month {m} PDF has {len(reader.pages)} pages, expected exactly 1"


def test_pdf_month_6_content(tmp_path):
    """Verify month-6 PDF report contains key required strings, config NCR detail, and no invented numbers."""
    pdf_path = tmp_path / "report_month_06.pdf"
    build_pdf(6, pdf_path)

    reader = pypdf.PdfReader(str(pdf_path))
    assert len(reader.pages) == 1
    page_text = reader.pages[0].extract_text()

    # Check key figures and IDs
    assert "0.825" in page_text, "Month-6 SPI (0.825) not found in PDF text"
    assert "0.977" in page_text, "Month-6 CPI (0.977) not found in PDF text"
    assert "Rs 3,90,26,515" in page_text, "Month-6 EAC formatted amount not found in PDF text"
    assert "18 Sep 2026" in page_text, "CPM forecast handover date (18 Sep 2026) not found in PDF text"
    assert "07 Sep 2026" in page_text, "Baseline handover date (07 Sep 2026) not found in PDF text"
    assert "Synthetic" in page_text, "'Synthetic' keyword not found in PDF text"
    assert "RA-05" in page_text, "RA-05 held bill not found in PDF text"
    assert "NCR-003" in page_text, "NCR-003 open NCR not found in PDF text"

    # Report content checks:
    # 1. Config NCR detail present for open NCR-003
    assert "Slab top level outside the specified tolerance" in page_text, "NCR-003 config detail not found"
    # 2. Hardcoded invented number removed
    assert "14mm" not in page_text, "Invented number 14mm must not appear in PDF text"
    # 3. Closed NCR details must not appear in open NCR table
    assert "7-day cube strength" not in page_text, "Closed NCR-001 detail should not appear in open NCRs"
    assert "Rebar spacing" not in page_text, "Closed NCR-002 detail should not appear in open NCRs"
    # 4. Milestones status contains 'Achieved'
    assert "Achieved" in page_text, "'Achieved' milestone status not found in PDF text"
    # 5. Dynamic SLAB_F2 duration check (expected 19 wd vs planned 9 wd)
    assert "19 wd vs planned 9 wd" in page_text, "Dynamic duration '19 wd vs planned 9 wd' not found in PDF text"
    assert "All flags this month" in page_text, "'All flags this month' not found in PDF text"
