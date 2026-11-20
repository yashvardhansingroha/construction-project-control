"""Budget generation, BOQ item cost allocations, and monthly Planned Value (PV) S-curve."""

from datetime import date
from typing import Dict, List, Tuple, Union
import pandas as pd

from src.schedule import date_to_wd, wd_to_date


def activity_item_budget(activities: pd.DataFrame, boq: pd.DataFrame) -> pd.DataFrame:
    """Generate detailed budget breakdown with one row per (activity, BOQ item).

    Columns: activity_id, item, share, quantity, rate_inr, amount_inr
    """
    boq_map = boq.set_index("item").to_dict(orient="index")

    rows = []
    for _, act in activities.iterrows():
        act_id = act["id"]
        boq_items = act["boq_items"]
        if not boq_items or not isinstance(boq_items, dict):
            continue

        for item_key, share_val in boq_items.items():
            boq_row = boq_map[item_key]
            total_qty = float(boq_row["quantity"])
            rate = float(boq_row["rate_inr"])

            # Quantity allocated to this activity = share * total BOQ quantity
            item_qty = float(share_val) * total_qty
            # Cost amount = allocated quantity * BOQ unit rate
            amount = item_qty * rate

            rows.append({
                "activity_id": act_id,
                "item": item_key,
                "share": float(share_val),
                "quantity": item_qty,
                "rate_inr": rate,
                "amount_inr": amount,
            })

    return pd.DataFrame(rows)


def activity_budgets(activities: pd.DataFrame, boq: pd.DataFrame) -> pd.DataFrame:
    """Compute total budget in INR per activity.

    Milestones and curing activities have budget 0.
    Returns DataFrame with columns: id, budget_inr
    """
    item_df = activity_item_budget(activities, boq)
    if item_df.empty:
        sums: Dict[str, float] = {}
    else:
        sums = item_df.groupby("activity_id")["amount_inr"].sum().to_dict()

    rows = []
    for _, act in activities.iterrows():
        act_id = act["id"]
        budget = float(sums.get(act_id, 0.0))
        rows.append({"id": act_id, "budget_inr": budget})

    return pd.DataFrame(rows)


def bac(activities: pd.DataFrame, boq: pd.DataFrame) -> float:
    """Compute Budget at Completion (BAC), the sum of all activity budgets."""
    budgets_df = activity_budgets(activities, boq)
    return float(budgets_df["budget_inr"].sum())


def month_of_wd(n: int, start_date: Union[str, date]) -> int:
    """Return calendar month index (1-based, Jan 2026 = 1) for working-day index n."""
    n = int(n)
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    d = wd_to_date(n, start_date)
    # Months relative to start_date year and month
    return (d.year - start_date.year) * 12 + (d.month - start_date.month) + 1


def month_end_wd(m: int, start_date: Union[str, date]) -> int:
    """Return number of working days completed by the end of project calendar month m.

    For m = 6 (June 2026), this represents the data date working day count (152).
    """
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)

    cal_year = start_date.year + (start_date.month - 1 + m - 1) // 12
    cal_month = (start_date.month - 1 + m - 1) % 12 + 1

    # Find the last calendar day of the month
    if cal_month == 12:
        last_day = date(cal_year, 12, 31)
    else:
        last_day = date(cal_year, cal_month + 1, 1) - pd.Timedelta(days=1)
        last_day = last_day.date() if hasattr(last_day, "date") else last_day

    # Count all working days (Mon-Sat, skipping Sundays) from start_date through last_day
    total_days = (last_day - start_date).days
    working_days_count = 0
    for day_offset in range(total_days + 1):
        check_date = start_date + pd.Timedelta(days=day_offset)
        # 6 is Sunday in Python weekday convention
        if check_date.weekday() != 6:
            working_days_count += 1

    return working_days_count


def monthly_pv(
    cpm_with_dates: pd.DataFrame,
    budgets: pd.DataFrame,
    start_date: Union[str, date],
) -> pd.DataFrame:
    """Generate time-phased baseline Planned Value (PV) per month and cumulative PV.

    Spreads each activity's budget linearly across its working days.
    Rounding rule: Cumulative PV per activity is rounded to whole rupees, and monthly
    PV = round(cum) - round(previous cum). This guarantees integer equality where
    sum(pv) == BAC to the rupee.
    """
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)

    budget_map = budgets.set_index("id")["budget_inr"].to_dict()

    # Determine project handover completion month
    last_finish = cpm_with_dates["ef"].max()
    max_month = month_of_wd(last_finish - 1, start_date) if last_finish > 0 else 1

    # Track monthly PV sums across all activities
    month_pv_totals: Dict[int, int] = {m: 0 for m in range(1, max_month + 1)}

    for _, row in cpm_with_dates.iterrows():
        act_id = row["id"]
        total_budget = budget_map.get(act_id, 0.0)
        dur = int(row["duration_days"])
        es_val = int(row["es"])
        ef_val = int(row["ef"])

        if total_budget <= 0.0 or dur <= 0:
            continue

        # Count how many working days of this activity fall in each month
        act_days_in_month: Dict[int, int] = {}
        for wd in range(es_val, ef_val):
            m = month_of_wd(wd, start_date)
            act_days_in_month[m] = act_days_in_month.get(m, 0) + 1

        # Spread budget linearly and apply rupee-exact cumulative rounding
        cum_days = 0
        prev_cum_rounded = 0
        for m in sorted(act_days_in_month.keys()):
            cum_days += act_days_in_month[m]
            # Theoretical cumulative fraction of activity budget
            # Formula: cum_amount = total_budget * (cum_days / duration)
            cum_exact = total_budget * (cum_days / dur)
            cum_rounded = int(round(cum_exact))

            month_pv = cum_rounded - prev_cum_rounded
            prev_cum_rounded = cum_rounded
            month_pv_totals[m] = month_pv_totals.get(m, 0) + month_pv

    # Build monthly PV DataFrame
    rows = []
    cumulative_pv = 0
    for m in range(1, max_month + 1):
        m_pv = month_pv_totals[m]
        cumulative_pv += m_pv
        rows.append({
            "month": m,
            "pv_inr": m_pv,
            "cum_pv_inr": cumulative_pv,
        })

    return pd.DataFrame(rows)
