"""Running Account (RA) bills, payment deductions, and payment tracking.
"""
from datetime import date, timedelta
import calendar
from typing import Dict, Any, Optional
import pandas as pd

from src.data_io import load_config, load_boq


def compute_bill_amounts(gross: float, retention_pct: float = 5.0, tds_pct: float = 2.0) -> Dict[str, int]:
    """Compute rounded deductions and net payable amount.
    
    Retention = round(gross * retention_pct / 100)
    TDS = round(gross * tds_pct / 100)
    net_payable = gross - retention - TDS (exact whole rupee identity)
    """
    gross_int = int(round(gross))
    retention = int(round(gross_int * (retention_pct / 100.0)))
    tds = int(round(gross_int * (tds_pct / 100.0)))
    net_payable = gross_int - retention - tds
    return {
        "gross": gross_int,
        "retention": retention,
        "tds": tds,
        "net_payable": net_payable,
    }


def is_injections_enabled(sim: Any, injections_enabled: Optional[bool] = None) -> bool:
    """Determine whether injections are active from flag or SimResult."""
    if injections_enabled is not None:
        return injections_enabled
    if hasattr(sim, "injections_enabled"):
        return bool(sim.injections_enabled)
    return bool(getattr(sim, "injections_applied", []))


def generate_bills(
    sim: Any,
    config: Optional[Dict[str, Any]] = None,
    boq: Optional[pd.DataFrame] = None,
    injections_enabled: Optional[bool] = None,
) -> pd.DataFrame:
    """Generate RA bills for all simulated months."""
    if config is None:
        config = load_config()
    if boq is None:
        boq = load_boq()

    start_date = config["calendar"]["start_date"]
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    year = start_date.year
    retention_pct = float(config.get("payments", {}).get("retention_pct", 5.0))
    tds_pct = float(config.get("payments", {}).get("tds_pct", 2.0))
    cert_days = int(config.get("payments", {}).get("certification_days", 7))
    pay_days = int(config.get("payments", {}).get("payment_days_after_certification", 14))

    boq_rate_map = boq.set_index("item")["rate_inr"].to_dict()

    through_month = int(sim.ac_monthly["month"].max()) if not sim.ac_monthly.empty else 6
    injections_on = is_injections_enabled(sim, injections_enabled)

    bills = []
    cum_retention = 0

    for m in range(1, through_month + 1):
        m_ac = sim.ac_monthly[sim.ac_monthly["month"] == m]
        gross_val = float(m_ac["amount"].sum())
        base_val = sum(float(row["quantity"]) * float(boq_rate_map[row["item"]]) for _, row in m_ac.iterrows())

        amounts = compute_bill_amounts(gross_val, retention_pct, tds_pct)
        gross_int = amounts["gross"]
        work_at_boq = int(round(base_val))
        price_var = gross_int - work_at_boq
        retention = amounts["retention"]
        tds = amounts["tds"]
        net_payable = amounts["net_payable"]
        cum_retention += retention

        # Dates
        last_day = calendar.monthrange(year, m)[1]
        sub_date = date(year, m, last_day)
        cert_date = sub_date + timedelta(days=cert_days)

        # Injections
        is_held = False
        hold_reason = ""
        paid_date: Optional[date] = None

        if injections_on and m == 3:
            # RA-03 paid late, 45 days after submission
            paid_date = sub_date + timedelta(days=45)
        elif injections_on and m == 5:
            # RA-05 held because of the open NCR on SLAB_F3
            is_held = True
            hold_reason = "Held: open NCR on SLAB_F3 (slab level check failed)"
            paid_date = None
        else:
            paid_date = cert_date + timedelta(days=pay_days)

        bills.append({
            "bill_no": f"RA-{m:02d}",
            "month": m,
            "gross_amount": gross_int,
            "work_at_boq_rates": work_at_boq,
            "price_variation": price_var,
            "retention": retention,
            "tds": tds,
            "net_payable": net_payable,
            "submitted_date": sub_date,
            "certified_date": cert_date,
            "paid_date": paid_date,
            "is_held": is_held,
            "hold_reason": hold_reason,
            "cumulative_retention": cum_retention,
        })

    return pd.DataFrame(bills)


def bills_at(
    eval_date: Any,
    sim: Any,
    config: Optional[Dict[str, Any]] = None,
    boq: Optional[pd.DataFrame] = None,
    injections_enabled: Optional[bool] = None,
) -> pd.DataFrame:
    """Evaluate RA bills status as of eval_date.
    
    Status values:
    - Held: held bill
    - Paid: paid_date <= eval_date
    - Pending: not yet paid as of eval_date
    """
    if isinstance(eval_date, str):
        eval_date = date.fromisoformat(eval_date)

    bills_df = generate_bills(sim, config, boq, injections_enabled)
    rows = []

    for _, row in bills_df.iterrows():
        b = row.to_dict()
        sub_date = b["submitted_date"]
        p_date = b["paid_date"]
        is_held = b["is_held"]

        if is_held:
            status = "Held"
            days_pending = (eval_date - sub_date).days if eval_date >= sub_date else 0
            days_to_pay = None
        elif p_date is not None and p_date <= eval_date:
            status = "Paid"
            days_pending = 0
            days_to_pay = (p_date - sub_date).days
        else:
            status = "Pending"
            days_pending = (eval_date - sub_date).days if eval_date >= sub_date else 0
            days_to_pay = None

        b["status"] = status
        b["days_pending"] = days_pending
        b["days_to_pay"] = days_to_pay
        rows.append(b)

    return pd.DataFrame(rows)
