"""Sensitivity and what-if analysis on steel price escalation and schedule delay."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure repo root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.report import format_inr


def run_sensitivity(export_json: bool = True) -> Dict[str, Any]:
    """Execute what-if sensitivity analysis varying steel price uplift and slab delay.
    
    Scenarios:
    1. Steel rate uplift scan: 5%, 10%, 15% with SLAB_F2 delay held at 10 working days.
    2. SLAB_F2 schedule delay scan: 5, 10, 15 working days with steel uplift held at 10%.
    
    Returns:
        Dict with 'steel_sensitivity' and 'slab_delay_sensitivity' scenario lists.
    """
    # Lazy import to avoid circular dependency
    from src.pipeline import run

    # 1. Steel Uplift Sensitivity (holding SLAB_F2 delay at 10 wd)
    steel_records: List[Dict[str, Any]] = []
    for uplift in [5, 10, 15]:
        overrides = {
            "injections": {
                "injections_enabled": True,
                "steel_escalation": {
                    "enabled": True,
                    "rate_uplift_pct": uplift,
                },
                "slab_delay": {
                    "enabled": True,
                    "extra_working_days": 10,
                },
            }
        }
        res = run(config_overrides=overrides, export_outputs=False)
        m6 = res["month_6_headline"]
        sf = res["schedule_forecast"]
        steel_records.append({
            "steel_uplift_pct": uplift,
            "slab_delay_wd": 10,
            "spi": m6["spi"],
            "cpi": m6["cpi"],
            "eac": m6["eac"],
            "vac": m6["vac"],
            "cpm_handover_date": sf["cpm_handover_date"],
            "cpm_delay_wd": sf["cpm_delay_wd"],
        })

    # 2. SLAB_F2 Schedule Delay Sensitivity (holding steel uplift at 10%)
    slab_records: List[Dict[str, Any]] = []
    for delay in [5, 10, 15]:
        overrides = {
            "injections": {
                "injections_enabled": True,
                "slab_delay": {
                    "enabled": True,
                    "extra_working_days": delay,
                },
                "steel_escalation": {
                    "enabled": True,
                    "rate_uplift_pct": 10,
                },
            }
        }
        res = run(config_overrides=overrides, export_outputs=False)
        m6 = res["month_6_headline"]
        sf = res["schedule_forecast"]
        slab_records.append({
            "slab_delay_wd": delay,
            "steel_uplift_pct": 10,
            "spi": m6["spi"],
            "cpi": m6["cpi"],
            "eac": m6["eac"],
            "vac": m6["vac"],
            "cpm_handover_date": sf["cpm_handover_date"],
            "cpm_delay_wd": sf["cpm_delay_wd"],
        })

    sens_results = {
        "steel_sensitivity": steel_records,
        "slab_delay_sensitivity": slab_records,
    }

    if export_json:
        out_path = repo_root / "outputs" / "sensitivity.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(sens_results, f, indent=2, sort_keys=True)

    return sens_results


def get_or_run_sensitivity() -> Dict[str, Any]:
    """Retrieve sensitivity analysis from cached JSON file or run if missing."""
    json_path = repo_root / "outputs" / "sensitivity.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return run_sensitivity(export_json=True)


def print_sensitivity_tables(results: Optional[Dict[str, Any]] = None) -> None:
    """Print formatted sensitivity tables to stdout."""
    if results is None:
        results = get_or_run_sensitivity()

    print("=" * 86)
    print("TABLE 1: STEEL RATE UPLIFT SENSITIVITY (SLAB_F2 Delay = 10 wd)")
    print("=" * 86)
    print(f"{'Steel Uplift':<14} {'Slab Delay':<12} {'SPI':<8} {'CPI':<8} {'EAC (INR)':<15} {'VAC (INR)':<14} {'Forecast Handover':<18} {'Delay':<8}")
    print("-" * 86)
    for r in results["steel_sensitivity"]:
        eac_str = format_inr(r['eac'])
        vac_str = format_inr(r['vac'])
        d_str = f"+{r['cpm_delay_wd']} wd"
        print(f"{r['steel_uplift_pct']}%{'':<11} {r['slab_delay_wd']} wd{'':<6} {r['spi']:.3f}{'':<3} {r['cpi']:.3f}{'':<3} {eac_str:<15} {vac_str:<14} {r['cpm_handover_date']:<18} {d_str:<8}")
    print("=" * 86)
    print()
    print("=" * 86)
    print("TABLE 2: SLAB_F2 SCHEDULE DELAY SENSITIVITY (Steel Rate Uplift = 10%)")
    print("=" * 86)
    print(f"{'Slab Delay':<12} {'Steel Uplift':<14} {'SPI':<8} {'CPI':<8} {'EAC (INR)':<15} {'VAC (INR)':<14} {'Forecast Handover':<18} {'Delay':<8}")
    print("-" * 86)
    for r in results["slab_delay_sensitivity"]:
        eac_str = format_inr(r['eac'])
        vac_str = format_inr(r['vac'])
        d_str = f"+{r['cpm_delay_wd']} wd"
        print(f"{r['slab_delay_wd']} wd{'':<6} {r['steel_uplift_pct']}%{'':<11} {r['spi']:.3f}{'':<3} {r['cpi']:.3f}{'':<3} {eac_str:<15} {vac_str:<14} {r['cpm_handover_date']:<18} {d_str:<8}")
    print("=" * 86)


if __name__ == "__main__":
    res = run_sensitivity(export_json=True)
    print_sensitivity_tables(res)
