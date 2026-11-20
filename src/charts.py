"""Visualization utilities for project control: Gantt charts, S-curves, and progress graphics."""

from pathlib import Path
from typing import Optional, Union
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd


def gantt_chart(
    cpm_df_with_dates: pd.DataFrame,
    path: Union[str, Path],
    forecast_df: Optional[pd.DataFrame] = None,
    title: str = "Project Schedule Gantt Chart (Synthetic)",
) -> None:
    """Generate and save a publication-quality Gantt chart.

    Args:
        cpm_df_with_dates: DataFrame with id, duration_days, is_critical, start_date, finish_date.
        path: File path to save the chart PNG.
        forecast_df: Optional forecast DataFrame with same columns to compare against baseline.
        title: Title string (must include '(Synthetic)').
    """
    if "(Synthetic)" not in title:
        title = f"{title} (Synthetic)"

    # Ensure output parent directory exists
    save_path = Path(path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    df = cpm_df_with_dates.copy()
    n_activities = len(df)

    # Figure height scales gracefully with number of activities (A4 readable width)
    fig_height = max(8.0, n_activities * 0.32)
    fig, ax = plt.subplots(figsize=(13.0, fig_height))

    y_positions = list(range(n_activities))
    labels = list(df["id"])

    # Color palette
    color_critical = "#b22222"     # Deep crimson for critical path
    color_noncritical = "#78909c"  # Blue-grey for floating tasks
    color_milestone = "#d32f2f"    # Red diamond for critical milestones

    for idx, (_, row) in enumerate(df.iterrows()):
        y = idx
        is_crit = bool(row["is_critical"])
        dur = int(row["duration_days"])
        s_date = row["start_date"]
        f_date = row["finish_date"]

        s_num = mdates.date2num(s_date)
        f_num = mdates.date2num(f_date)
        # Span inclusive of start and finish days
        span_days = max(1.0, f_num - s_num + 1.0)

        bar_color = color_critical if is_crit else color_noncritical

        if forecast_df is None:
            # Baseline-only rendering
            if dur == 0:
                ax.scatter(
                    f_num,
                    y,
                    marker="D",
                    s=70,
                    color=color_milestone if is_crit else "#455a64",
                    zorder=5,
                    edgecolors="#212121",
                    linewidth=0.8,
                )
            else:
                ax.barh(
                    y,
                    width=span_days,
                    left=s_num,
                    height=0.55,
                    color=bar_color,
                    edgecolor="#37474f",
                    linewidth=0.6,
                    zorder=3,
                )
        else:
            # Comparison view: baseline as outline bar, forecast as filled bar
            if dur > 0:
                ax.barh(
                    y,
                    width=span_days,
                    left=s_num,
                    height=0.6,
                    fill=False,
                    edgecolor="#263238",
                    linewidth=1.2,
                    linestyle="--",
                    zorder=2,
                    label="Baseline" if idx == 0 else "",
                )

            # Draw forecast bar
            f_row = forecast_df[forecast_df["id"] == row["id"]].iloc[0]
            f_s_num = mdates.date2num(f_row["start_date"])
            f_f_num = mdates.date2num(f_row["finish_date"])
            f_span = max(1.0, f_f_num - f_s_num + 1.0)
            f_crit = bool(f_row["is_critical"])
            f_color = color_critical if f_crit else color_noncritical

            if int(f_row["duration_days"]) == 0:
                ax.scatter(
                    f_f_num,
                    y,
                    marker="D",
                    s=70,
                    color=color_milestone if f_crit else "#455a64",
                    zorder=5,
                    edgecolors="#212121",
                )
            else:
                ax.barh(
                    y,
                    width=f_span,
                    left=f_s_num,
                    height=0.42,
                    color=f_color,
                    alpha=0.85,
                    edgecolor="#212121",
                    linewidth=0.5,
                    zorder=4,
                    label="Forecast" if idx == 0 else "",
                )

    # Invert y-axis so the first activity starts at the top
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=9, family="monospace")
    ax.invert_yaxis()

    # Format calendar x-axis
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))

    ax.grid(True, which="major", axis="x", linestyle="-", alpha=0.3, color="#90a4ae")
    ax.grid(True, which="minor", axis="x", linestyle=":", alpha=0.15, color="#b0bec5")
    ax.grid(True, which="major", axis="y", linestyle="-", alpha=0.1, color="#cfd8dc")

    ax.set_title(title, fontsize=12, fontweight="bold", pad=14)
    ax.set_xlabel("Calendar Date (Mon-Sat Working Calendar)", fontsize=10, labelpad=8)

    # Custom legend in upper-right corner
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=color_critical, edgecolor="#37474f", label="Critical Work (TF = 0)"),
        Patch(facecolor=color_noncritical, edgecolor="#37474f", label="Non-Critical Work (TF > 0)"),
        Line2D([0], [0], marker="D", color="w", markerfacecolor=color_milestone, markersize=8, label="Milestone"),
    ]
    if forecast_df is not None:
        legend_elements.append(
            Line2D([0], [0], color="#263238", linestyle="--", linewidth=1.5, label="Baseline Outline")
        )

    ax.legend(handles=legend_elements, loc="upper right", framealpha=0.9, fontsize=9)

    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def s_curve_chart(
    monthly_evm_df: pd.DataFrame,
    pv_full_df: pd.DataFrame,
    path: Union[str, Path],
    title: str = "Project S-Curve: Planned Value, Earned Value & Actual Cost (Synthetic)",
) -> None:
    """Generate and save publication-quality EVM S-curve chart.

    Plots baseline PV across the full project lifecycle, and EV and AC for months 1-6.
    """
    if "(Synthetic)" not in title:
        title = f"{title} (Synthetic)"

    save_path = Path(path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11.0, 6.5))

    # Baseline PV across full duration
    pv_x = [0] + list(pv_full_df["month"])
    pv_y = [0.0] + list(pv_full_df["cum_pv_inr"] / 1e7)  # In Crores INR

    # Actuals through Month 6
    ev_x = [0] + list(monthly_evm_df["month"])
    ev_y = [0.0] + list(monthly_evm_df["ev"] / 1e7)
    ac_x = [0] + list(monthly_evm_df["month"])
    ac_y = [0.0] + list(monthly_evm_df["ac"] / 1e7)

    # Plot lines with styling
    ax.plot(
        pv_x,
        pv_y,
        marker="o",
        markersize=5,
        linewidth=2.2,
        color="#1565c0",
        label="Planned Value (PV Baseline)",
        zorder=3,
    )
    ax.plot(
        ev_x,
        ev_y,
        marker="s",
        markersize=6,
        linewidth=2.2,
        color="#2e7d32",
        label="Earned Value (EV Physical)",
        zorder=4,
    )
    ax.plot(
        ac_x,
        ac_y,
        marker="^",
        markersize=6,
        linewidth=2.2,
        color="#c62828",
        label="Actual Cost (AC Incurred)",
        zorder=4,
    )

    # Vertical line indicating status / data date at Month 6
    max_m = int(monthly_evm_df["month"].max())
    ax.axvline(
        x=max_m,
        color="#37474f",
        linestyle="--",
        linewidth=1.2,
        alpha=0.7,
        label=f"Data Date (Month {max_m})",
        zorder=2,
    )

    ax.set_title(title, fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel("Project Month (2026 Calendar Months)", fontsize=10, labelpad=8)
    ax.set_ylabel("Cumulative Amount (INR Crores)", fontsize=10, labelpad=8)

    ax.set_xticks(pv_x)
    month_labels = ["Start"] + [f"M{m}" for m in pv_full_df["month"]]
    ax.set_xticklabels(month_labels, fontsize=9)

    # Format y-axis currency in Crores
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda val, pos: f"₹{val:.2f} Cr"))
    ax.grid(True, linestyle="-", alpha=0.3, color="#90a4ae")

    ax.legend(loc="upper left", framealpha=0.9, fontsize=9.5)

    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def pdf_scurve_chart(
    monthly_evm_df: pd.DataFrame,
    pv_full_df: pd.DataFrame,
    path: Union[str, Path],
    month: int = 6,
) -> None:
    """Generate a compact S-curve chart tailored for embedding in the 1-page PDF report."""
    save_path = Path(path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(6.8, 1.8), dpi=150)

    # 1. PV across whole project
    pv_x = [0] + list(pv_full_df["month"])
    pv_y = [0.0] + [float(val) / 1e7 for val in pv_full_df["cum_pv_inr"]]

    # 2. EV and AC up to month
    evm_sub = monthly_evm_df[monthly_evm_df["month"] <= month]
    ev_x = [0] + list(evm_sub["month"])
    ev_y = [0.0] + [float(val) / 1e7 for val in evm_sub["ev"]]
    ac_x = [0] + list(evm_sub["month"])
    ac_y = [0.0] + [float(val) / 1e7 for val in evm_sub["ac"]]

    ax.plot(pv_x, pv_y, marker="o", markersize=3.5, linewidth=1.6, color="#1565c0", label="PV (Planned)", zorder=3)
    ax.plot(ev_x, ev_y, marker="s", markersize=3.5, linewidth=1.6, color="#2e7d32", label="EV (Earned)", zorder=4)
    ax.plot(ac_x, ac_y, marker="^", markersize=3.5, linewidth=1.6, color="#c62828", label="AC (Actual)", zorder=4)

    # Cutoff line
    ax.axvline(x=month, color="#546e7a", linestyle="--", linewidth=1.0, alpha=0.8, label=f"M{month} Cutoff")

    ax.set_xticks(pv_x)
    month_labels = ["0"] + [f"M{m}" for m in pv_full_df["month"]]
    ax.set_xticklabels(month_labels, fontsize=7)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda val, pos: f"Rs {val:.1f} Cr"))
    ax.tick_params(axis="both", labelsize=7)
    ax.grid(True, linestyle="-", alpha=0.3, color="#b0bec5")

    ax.set_ylabel("Cum. Spend", fontsize=7.5, labelpad=4)
    ax.legend(loc="upper left", framealpha=0.85, fontsize=7, ncol=4)

    plt.tight_layout(pad=0.4)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
