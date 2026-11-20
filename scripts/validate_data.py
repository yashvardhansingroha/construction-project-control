"""Validation script for project data files: activities, BOQ, and material coefficients."""

import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add repository root to sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.data_io import load_activities, load_boq, load_coefficients, load_config


def check_unique_ids(activities_df) -> Tuple[bool, str]:
    """Check that all activity IDs are unique."""
    ids = list(activities_df["id"])
    duplicates = [x for x in ids if ids.count(x) > 1]
    if len(duplicates) == 0:
        return True, f"All {len(ids)} activity IDs are unique"
    return False, f"Duplicate activity IDs found: {set(duplicates)}"


def check_predecessors_exist(activities_df) -> Tuple[bool, str]:
    """Check that all predecessors referenced exist in activity IDs."""
    all_ids = set(activities_df["id"])
    missing = []
    for _, row in activities_df.iterrows():
        act_id = row["id"]
        for p in row["predecessors"]:
            if p not in all_ids:
                missing.append(f"{act_id} -> {p}")
    if not missing:
        return True, "All predecessors exist in activity IDs"
    return False, f"Missing predecessors referenced: {missing}"


def check_no_cycles(activities_df) -> Tuple[bool, str]:
    """Check that there are no cycles in the activity network using depth-first search."""
    # Directed graph: predecessor -> activity
    graph: Dict[str, List[str]] = {row["id"]: [] for _, row in activities_df.iterrows()}
    for _, row in activities_df.iterrows():
        act_id = row["id"]
        for p in row["predecessors"]:
            if p in graph:
                graph[p].append(act_id)

    # 0 = unvisited (white), 1 = visiting in current DFS stack (gray), 2 = completed (black)
    visited: Dict[str, int] = {node: 0 for node in graph}
    cycle_nodes: List[str] = []

    def dfs(node: str, stack: List[str]) -> bool:
        visited[node] = 1
        stack.append(node)
        for succ in graph[node]:
            if visited[succ] == 1:
                cycle_nodes.extend(stack[stack.index(succ):] + [succ])
                return True
            if visited[succ] == 0:
                if dfs(succ, stack):
                    return True
        stack.pop()
        visited[node] = 2
        return False

    for node in graph:
        if visited[node] == 0:
            if dfs(node, []):
                return False, f"Cycle detected in activity network: {' -> '.join(cycle_nodes)}"

    return True, "No cycles detected in activity dependency graph"


def check_single_start(activities_df) -> Tuple[bool, str]:
    """Check that exactly one activity has no predecessors."""
    start_activities = []
    for _, row in activities_df.iterrows():
        if len(row["predecessors"]) == 0:
            start_activities.append(row["id"])
    if len(start_activities) == 1:
        return True, f"Exactly one start activity: {start_activities[0]}"
    return False, f"Expected exactly 1 start activity, found {len(start_activities)}: {start_activities}"


def check_milestones(activities_df) -> Tuple[bool, str]:
    """Check that all milestones have duration 0 and empty boq_items."""
    invalid = []
    count = 0
    for _, row in activities_df.iterrows():
        if row["type"] == "milestone":
            count += 1
            if row["duration_days"] != 0:
                invalid.append(f"{row['id']} has duration {row['duration_days']} != 0")
            if len(row["boq_items"]) != 0:
                invalid.append(f"{row['id']} has non-empty boq_items: {row['boq_items']}")
    if not invalid:
        return True, f"All {count} milestones have duration 0 and empty boq_items"
    return False, f"Invalid milestones: {'; '.join(invalid)}"


def check_work_mappings(activities_df) -> Tuple[bool, str]:
    """Check that every work activity has a non-empty BOQ mapping."""
    missing = []
    count = 0
    for _, row in activities_df.iterrows():
        if row["type"] == "work":
            count += 1
            if len(row["boq_items"]) == 0:
                missing.append(row["id"])
    if not missing:
        return True, f"All {count} work activities have a non-empty BOQ mapping"
    return False, f"Work activities missing BOQ mapping: {missing}"


def check_mapped_boq_items_exist(activities_df, boq_df) -> Tuple[bool, str]:
    """Check that all BOQ items referenced in activities exist in boq.csv."""
    boq_item_ids = set(boq_df["item"])
    unknown_items = set()
    for _, row in activities_df.iterrows():
        for item_key in row["boq_items"]:
            if item_key not in boq_item_ids:
                unknown_items.add(item_key)
    if not unknown_items:
        return True, "All mapped BOQ items exist in boq.csv"
    return False, f"Unknown BOQ items in activities: {unknown_items}"


def check_all_boq_items_used(activities_df, boq_df) -> Tuple[bool, str]:
    """Check that every BOQ item is used by at least one activity."""
    used_items = set()
    for _, row in activities_df.iterrows():
        for item_key in row["boq_items"]:
            used_items.add(item_key)
    all_items = set(boq_df["item"])
    unused = all_items - used_items
    if not unused:
        return True, f"All {len(all_items)} BOQ items are utilized in activities"
    return False, f"Unused BOQ items: {unused}"


def check_boq_shares_sum(activities_df, boq_df, tol: float = 1e-9) -> Tuple[bool, str]:
    """Check that shares per BOQ item sum to 1.0 within tolerance."""
    shares: Dict[str, float] = {item: 0.0 for item in boq_df["item"]}
    for _, row in activities_df.iterrows():
        for item_key, share_val in row["boq_items"].items():
            if item_key in shares:
                shares[item_key] += share_val
    bad_items = []
    for item, total in shares.items():
        if abs(total - 1.0) >= tol:
            bad_items.append(f"{item} (sum={total:.6f})")
    if not bad_items:
        return True, f"All {len(shares)} BOQ item shares sum to 1.0 (tol={tol})"
    return False, f"BOQ item shares do not sum to 1.0: {', '.join(bad_items)}"


def check_steel_matches_rcc(activities_df) -> Tuple[bool, str]:
    """Check that STEEL share equals RCC_M25 share for every activity."""
    mismatches = []
    for _, row in activities_df.iterrows():
        boq = row["boq_items"]
        rcc_share = boq.get("RCC_M25", 0.0)
        steel_share = boq.get("STEEL", 0.0)
        if abs(rcc_share - steel_share) > 1e-9:
            mismatches.append(f"{row['id']}: RCC_M25={rcc_share}, STEEL={steel_share}")
    if not mismatches:
        return True, "STEEL share equals RCC_M25 share per activity"
    return False, f"STEEL and RCC_M25 share mismatch: {'; '.join(mismatches)}"


def check_coefficient_rows(boq_df, coeff_df) -> Tuple[bool, str]:
    """Check that every BOQ item has a corresponding row in material_coefficients.csv."""
    coeff_items = set(coeff_df["item"])
    missing = []
    for item in boq_df["item"]:
        if item not in coeff_items:
            missing.append(item)
    if not missing:
        return True, f"All {len(boq_df)} BOQ items have a row in material_coefficients.csv"
    return False, f"BOQ items missing coefficient row: {missing}"


def check_no_negative_numbers(activities_df, boq_df, coeff_df) -> Tuple[bool, str]:
    """Check that there are no negative quantities, rates, shares, or coefficients."""
    negatives = []
    for _, row in activities_df.iterrows():
        if row["duration_days"] < 0:
            negatives.append(f"activities {row['id']} duration_days={row['duration_days']}")
        for k, v in row["boq_items"].items():
            if v < 0:
                negatives.append(f"activities {row['id']} boq share {k}={v}")
    for _, row in boq_df.iterrows():
        if row["quantity"] < 0:
            negatives.append(f"boq {row['item']} quantity={row['quantity']}")
        if row["rate_inr"] < 0:
            negatives.append(f"boq {row['item']} rate_inr={row['rate_inr']}")
    numeric_coeff_cols = ["cement_bags", "steel_kg", "sand_cum", "aggregate_cum", "bricks"]
    for _, row in coeff_df.iterrows():
        for col in numeric_coeff_cols:
            if row[col] < 0:
                negatives.append(f"coefficients {row['item']} {col}={row[col]}")
    if not negatives:
        return True, "No negative numbers found across all data files"
    return False, f"Negative numbers found: {'; '.join(negatives)}"


def main() -> int:
    """Run all validation checks and print results and summary block."""
    try:
        config = load_config()
        activities = load_activities()
        boq = load_boq()
        coefficients = load_coefficients()
    except Exception as exc:
        print(f"FAIL: Failed to load input files: {exc}")
        return 1

    checks = [
        ("Unique activity IDs", lambda: check_unique_ids(activities)),
        ("Every predecessor exists", lambda: check_predecessors_exist(activities)),
        ("No dependency cycles", lambda: check_no_cycles(activities)),
        ("Exactly one start activity", lambda: check_single_start(activities)),
        ("Milestones have duration 0 and empty boq_items", lambda: check_milestones(activities)),
        ("Every work activity has a mapping", lambda: check_work_mappings(activities)),
        ("Every mapped BOQ item exists", lambda: check_mapped_boq_items_exist(activities, boq)),
        ("Every BOQ item is used", lambda: check_all_boq_items_used(activities, boq)),
        ("Shares per BOQ item sum to 1.0", lambda: check_boq_shares_sum(activities, boq)),
        ("STEEL share equals RCC_M25 share per activity", lambda: check_steel_matches_rcc(activities)),
        ("Every BOQ item has a coefficient row", lambda: check_coefficient_rows(boq, coefficients)),
        ("No negative numbers", lambda: check_no_negative_numbers(activities, boq, coefficients)),
    ]

    all_passed = True
    print("=" * 60)
    print("DATA VALIDATION CHECKS")
    print("=" * 60)

    for name, check_fn in checks:
        passed, detail = check_fn()
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {detail}")
        if not passed:
            all_passed = False

    # Summary calculations
    # 1. Activities by type
    type_counts = activities["type"].value_counts().to_dict()

    # 2. Milestone IDs
    milestones = list(activities[activities["type"] == "milestone"]["id"])

    # 3. BAC: sum of quantity * rate_inr
    # Formula: BAC = sum(quantity * rate_inr)
    bac_series = boq["quantity"] * boq["rate_inr"]
    bac = float(bac_series.sum())

    # 4. BAC per sqm of built-up area
    built_up_area = float(config["project"]["built_up_area_sqm"])
    bac_per_sqm = bac / built_up_area

    # 5. Steel kg per cum of RCC
    # BOQ STEEL quantity is in MT (1 MT = 1000 kg)
    steel_mt = float(boq[boq["item"] == "STEEL"]["quantity"].iloc[0])
    steel_kg_total = steel_mt * 1000.0
    rcc_cum_total = float(boq[boq["item"] == "RCC_M25"]["quantity"].iloc[0])
    steel_kg_per_cum_rcc = steel_kg_total / rcc_cum_total

    # 6. Total cement bags for the whole BOQ
    # Merge BOQ with coefficients on item
    merged_boq = boq.merge(coefficients, on="item", how="left")
    cement_bags_total = float((merged_boq["quantity"] * merged_boq["cement_bags"]).sum())

    print("=" * 60)
    print("SUMMARY BLOCK")
    print("=" * 60)
    print("Activities by type:")
    for act_type, count in sorted(type_counts.items()):
        print(f"  - {act_type}: {count}")
    print(f"  - Total activities: {len(activities)}")
    print(f"Milestone IDs: {', '.join(milestones)}")
    print(f"BAC (sum of quantity x rate): INR {bac:,.2f}")
    print(f"BAC per sqm of built-up area: INR {bac_per_sqm:,.2f} / sqm (Area: {built_up_area:,.0f} sqm)")
    print(f"Steel kg per cum of RCC: {steel_kg_per_cum_rcc:.2f} kg/cum ({steel_kg_total:,.0f} kg steel / {rcc_cum_total:,.0f} cum RCC)")
    print(f"Total cement bags for whole BOQ: {cement_bags_total:,.1f} bags")
    print("=" * 60)

    if not all_passed:
        print("RESULT: VALIDATION FAILED")
        return 1

    print("RESULT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
