"""Unit tests for Earned Value Management (EVM) metrics, formulas, and edge cases."""

import pytest
from src.evm import evm_metrics


def test_textbook_three_activity_evm():
    """Textbook 3-activity EVM example with full hand arithmetic in comments.

    Hand Calculation:
    -----------------
    Activities:
      X: Budget = 100,000 INR, % complete = 100% -> EV = 100,000
      Y: Budget = 200,000 INR, % complete = 50%  -> EV = 100,000
      Z: Budget = 100,000 INR, % complete = 0%   -> EV = 0
    BAC = 100,000 + 200,000 + 100,000 = 400,000 INR

    Given status at observation date:
      PV = 250,000 INR
      EV = 100,000 + 100,000 + 0 = 200,000 INR
      AC = 220,000 INR

    Computed Metrics:
      SV = EV - PV = 200,000 - 250,000 = -50,000 INR
      CV = EV - AC = 200,000 - 220,000 = -20,000 INR
      SPI = EV / PV = 200,000 / 250,000 = 0.800
      CPI = EV / AC = 200,000 / 220,000 = 10 / 11 = 0.909091 (6 dp)
      EAC = BAC / CPI = 400,000 / (10/11) = 440,000 INR
      EAC_combined = AC + (BAC - EV) / (CPI * SPI)
                   = 220,000 + 200,000 / ((10/11) * 0.8)
                   = 220,000 + 200,000 / (8/11)
                   = 220,000 + 275,000 = 495,000 INR
      ETC = EAC - AC = 440,000 - 220,000 = 220,000 INR
      VAC = BAC - EAC = 400,000 - 440,000 = -40,000 INR
      TCPI = (BAC - EV) / (BAC - AC)
           = (400,000 - 200,000) / (400,000 - 220,000)
           = 200,000 / 180,000 = 10 / 9 = 1.111111 (6 dp)
    """
    bac = 400000.0
    pv = 250000.0
    ev = 200000.0
    ac = 220000.0

    res = evm_metrics(pv=pv, ev=ev, ac=ac, bac=bac)

    assert res["sv"] == -50000.0
    assert res["cv"] == -20000.0
    assert pytest.approx(res["spi"], abs=1e-6) == 0.8
    assert pytest.approx(res["cpi"], abs=1e-6) == 0.909091
    assert pytest.approx(res["eac"], abs=1.0) == 440000.0
    assert pytest.approx(res["eac_combined"], abs=1.0) == 495000.0
    assert pytest.approx(res["etc"], abs=1.0) == 220000.0
    assert pytest.approx(res["vac"], abs=1.0) == -40000.0
    assert pytest.approx(res["tcpi"], abs=1e-6) == 1.111111


def test_evm_edge_cases():
    """Verify EVM edge cases: PV=0, AC=0, and 100% completion."""
    bac = 400000.0

    # 1. Edge Case: PV = 0 -> SPI is None
    res_pv0 = evm_metrics(pv=0.0, ev=0.0, ac=50000.0, bac=bac)
    assert res_pv0["spi"] is None
    assert res_pv0["eac_combined"] is None

    # 2. Edge Case: AC = 0 -> CPI is None and EAC = BAC (no cost data yet, forecast = plan)
    res_ac0 = evm_metrics(pv=100000.0, ev=100000.0, ac=0.0, bac=bac)
    assert res_ac0["cpi"] is None
    assert res_ac0["eac"] == bac
    assert res_ac0["eac_combined"] is None

    # 3. Edge Case: 100% complete (EV = BAC = 400,000, AC = 420,000)
    # TCPI = (BAC - EV) / (BAC - AC) = 0 / -20,000 = 0.0
    # CPI = 400,000 / 420,000 = 0.952381 (6 dp)
    res_done = evm_metrics(pv=400000.0, ev=400000.0, ac=420000.0, bac=bac)
    assert res_done["tcpi"] == 0.0
    assert pytest.approx(res_done["cpi"], abs=1e-6) == 0.952381
    assert res_done["etc"] == 0.0
