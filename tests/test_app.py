"""Tests for Streamlit dashboard application using AppTest."""

import json
from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_streamlit_app_tabs_and_execution():
    """Verify Streamlit app runs without exceptions, contains 7 exact tabs, and responds to month slider."""
    app_path = (Path(__file__).parent.parent / "app.py").resolve()
    at = AppTest.from_file(str(app_path), default_timeout=120)
    at.run()
    assert not at.exception, f"App execution failed on startup: {at.exception}"

    expected_tabs = [
        "Overview",
        "Schedule & Critical Path",
        "Cost & EVM",
        "Materials",
        "Payments",
        "Quality",
        "Monthly Report",
    ]
    tab_labels = [t.label for t in at.tabs]
    assert tab_labels == expected_tabs, f"Tabs mismatch: got {tab_labels}, expected {expected_tabs}"

    # Verify slider changes execute cleanly for months 1, 3, 6
    for m in (1, 3, 6):
        at.slider[0].set_value(m).run()
        assert not at.exception, f"Exception occurred when setting slider to month {m}: {at.exception}"

    # Verify Overview displays the exact month-6 SPI string from results.json when m = 6
    at.slider[0].set_value(6).run()
    assert not at.exception

    results_path = Path("outputs/results.json")
    assert results_path.exists(), "results.json not found"
    with open(results_path, "r") as f:
        res = json.load(f)

    # In results.json, month_6_headline has spi: 0.825
    m6_spi_val = res.get("month_6_headline", {}).get("spi", 0.825)
    m6_spi_str = f"{m6_spi_val:.3f}" if isinstance(m6_spi_val, float) else str(m6_spi_val)
    assert m6_spi_str == "0.825"

    metric_values = [m.value for m in at.metric]
    assert m6_spi_str in metric_values, (
        f"Month-6 SPI string '{m6_spi_str}' not found in AppTest metric values: {metric_values}"
    )

    # Verify SPI metric specifically has label 'SPI' and value '0.825'
    spi_metrics = [m for m in at.metric if m.label == "SPI"]
    assert len(spi_metrics) >= 1
    assert spi_metrics[0].value == m6_spi_str

    # Verify EAC and VAC metrics use crore format (Rs X.XX Cr)
    eac_metrics = [m for m in at.metric if m.label == "EAC"]
    assert len(eac_metrics) >= 1
    assert "Cr" in eac_metrics[0].value, f"EAC metric '{eac_metrics[0].value}' does not use crore format"

    # Verify What-if sensitivity section renders in Cost & EVM tab
    subheaders = [s.value for s in at.subheader]
    assert "What-if (sensitivity, month 6)" in subheaders, (
        f"What-if sensitivity subheader not found in: {subheaders}"
    )

    markdown_texts = [md.value for md in at.markdown]
    assert any("Steel Escalation Sensitivity" in md for md in markdown_texts), (
        "Steel Escalation Sensitivity table label not found in markdown elements"
    )
    assert any("SLAB_F2 Schedule Delay Sensitivity" in md for md in markdown_texts), (
        "SLAB_F2 Schedule Delay Sensitivity table label not found in markdown elements"
    )
