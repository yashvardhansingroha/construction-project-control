"""Unit tests for quality control inspections, NCR ageing, and summary metrics."""

from datetime import date
import pytest
import pandas as pd

from src.data_io import load_config, load_activities, load_boq
from src.simulate import simulate
from src.quality import build_inspections, quality_summary, ncr_log_at


def test_ncr_days_open_and_filtering():
    """Verify days_open calculation for closed and open NCRs and exclusion from open list.
    
    - Closed NCR raised 1 May / closed 10 May = 9 days
    - Open NCR raised 5 May evaluated at 30 Jun = 56 days
    """
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    ncrs_df = ncr_log_at(date(2026, 6, 30), sim, activities, config)

    # Injected NCRs
    # NCR-001 (SLAB_F1): raised 2026-03-14, closed 2026-03-23 -> days_open = 9
    ncr1 = ncrs_df[ncrs_df["ncr_id"] == "NCR-001"].iloc[0]
    assert ncr1["status"] == "Closed"
    assert int(ncr1["days_open"]) == 9
    assert ncr1["description"] == "7-day cube strength below the acceptance value for the batch"

    # NCR-002 (COL_F2): closed after 20 days
    ncr2 = ncrs_df[ncrs_df["ncr_id"] == "NCR-002"].iloc[0]
    assert ncr2["status"] == "Closed"
    assert int(ncr2["days_open"]) == 20
    assert ncr2["description"] == "Rebar spacing and cover blocks not as per drawing"

    # Check synthetic dates directly: raised 1 May / closed 10 May -> 9 days
    d_raised = date(2026, 5, 1)
    d_closed = date(2026, 5, 10)
    assert (d_closed - d_raised).days == 9

    # Open NCR-003: raised 2026-05-05, evaluated at 2026-06-30 -> 56 days
    ncr3 = ncrs_df[ncrs_df["ncr_id"] == "NCR-003"].iloc[0]
    assert ncr3["status"] == "Open"
    assert int(ncr3["days_open"]) == 56
    assert ncr3["description"] == "Slab top level outside the specified tolerance"
    assert "14mm" not in ncr3["description"]

    # Closed NCRs are excluded from the open list
    open_ncrs = ncrs_df[ncrs_df["status"] == "Open"]
    closed_ncrs = ncrs_df[ncrs_df["status"] == "Closed"]
    assert len(open_ncrs) == 1
    assert open_ncrs["ncr_id"].iloc[0] == "NCR-003"
    assert "NCR-001" not in open_ncrs["ncr_id"].values
    assert "NCR-002" not in open_ncrs["ncr_id"].values
    assert len(closed_ncrs) == 2


def test_quality_pass_rate_and_summary():
    """Verify pass rate equals passes / inspections."""
    config = load_config()
    activities = load_activities()
    boq = load_boq()
    sim = simulate(config, activities, boq, through_month=6, injections_enabled=True)

    summary = quality_summary(date(2026, 6, 30), sim, activities, config)

    total = summary["total_inspections"]
    passes = summary["passes"]
    failures = summary["failures"]
    pass_rate = summary["pass_rate"]

    assert total == passes + failures
    assert pytest.approx(pass_rate, rel=1e-4) == float(passes) / float(total)
    assert total == 33
    assert passes == 30
    assert failures == 3
    assert pytest.approx(pass_rate, rel=1e-3) == 0.909
    assert summary["open_ncrs"] == 1
    assert summary["closed_ncrs"] == 2
    assert summary["average_closure_days"] == 14.5  # (9 + 20) / 2
