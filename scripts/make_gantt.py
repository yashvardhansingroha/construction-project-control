"""Script to generate and export baseline project schedule Gantt chart."""

import sys
from pathlib import Path

# Add repository root to sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.data_io import load_activities, load_config
from src.schedule import add_dates, compute_cpm
from src.charts import gantt_chart


def main() -> None:
    """Load activities and calendar configuration, compute baseline CPM, and export Gantt chart."""
    config = load_config()
    activities = load_activities()
    start_date = config["calendar"]["start_date"]

    cpm_df = compute_cpm(activities)
    cpm_with_dates = add_dates(cpm_df, start_date)

    out_path = repo_root / "outputs" / "charts" / "gantt_baseline.png"
    gantt_chart(
        cpm_with_dates,
        out_path,
        title="G+4 Residential Building: Baseline Schedule (Synthetic)",
    )
    print(f"Baseline Gantt chart written to: {out_path}")


if __name__ == "__main__":
    main()
