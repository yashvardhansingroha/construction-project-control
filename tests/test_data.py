"""Unit tests for project data validation and configuration integrity."""

import pytest
from src.data_io import load_activities, load_boq, load_coefficients, load_config
from scripts.validate_data import (
    check_all_boq_items_used,
    check_boq_shares_sum,
    check_coefficient_rows,
    check_mapped_boq_items_exist,
    check_milestones,
    check_no_cycles,
    check_no_negative_numbers,
    check_predecessors_exist,
    check_single_start,
    check_steel_matches_rcc,
    check_unique_ids,
    check_work_mappings,
)


@pytest.fixture
def config():
    """Fixture providing loaded project configuration."""
    return load_config()


@pytest.fixture
def activities():
    """Fixture providing loaded activities DataFrame."""
    return load_activities()


@pytest.fixture
def boq():
    """Fixture providing loaded BOQ DataFrame."""
    return load_boq()


@pytest.fixture
def coefficients():
    """Fixture providing loaded material coefficients DataFrame."""
    return load_coefficients()


def test_config_frozen_values(config):
    """Verify that all FROZEN configuration values match the specification exactly."""
    # Project frozen values
    proj = config["project"]
    assert proj["name"] == "G+4 Residential Building (Synthetic)"
    assert proj["synthetic"] is True
    assert proj["built_up_area_sqm"] == 2000
    assert proj["floors"] == 5
    assert proj["footprint_sqm"] == 400
    assert proj["foundation"] == "isolated footings"

    # Calendar frozen values
    cal = config["calendar"]
    assert str(cal["start_date"]) == "2026-01-05"
    assert cal["working_days"] == "Mon-Sat"
    assert str(cal["data_date"]) == "2026-06-30"
    assert cal["report_month"] == 6

    # Seed
    assert config["seed"] == 42

    # Payments frozen values
    pay = config["payments"]
    assert pay["retention_pct"] == 5
    assert pay["tds_pct"] == 2
    assert pay["certification_days"] == 7
    assert pay["payment_days_after_certification"] == 14

    # Thresholds frozen values
    th = config["thresholds"]
    assert th["milestone_slip_days"] == 5
    assert th["spi_amber"] == 0.95
    assert th["spi_red"] == 0.90
    assert th["cpi_amber"] == 0.95
    assert th["cpi_red"] == 0.90
    assert th["activity_cost_variance_pct"] == 5
    assert th["ncr_open_days"] == 14
    assert th["bill_pending_days"] == 30

    # Noise frozen values
    ns = config["noise"]
    assert ns["progress_sd"] == 0.03
    assert ns["cost_sd"] == 0.02
    assert ns["cost_noise_clip_pct"] == 3

    # Injections frozen values
    inj = config["injections"]
    assert inj["injections_enabled"] is True
    assert inj["slab_delay"]["activity"] == "SLAB_F2"
    assert inj["slab_delay"]["extra_working_days"] == 10
    assert inj["steel_escalation"]["boq_item"] == "STEEL"
    assert inj["steel_escalation"]["rate_uplift_pct"] == 10
    assert inj["steel_escalation"]["from_month"] == 3
    assert inj["cement_shortage"]["month"] == 4
    assert inj["cement_shortage"]["procured_fraction_of_requirement"] == 0.70

    # QC failure injections
    qc = inj["qc_failures"]
    assert len(qc) == 3
    assert qc[0]["activity"] == "SLAB_F1" and qc[0]["test"] == "cube_test" and qc[0]["ncr_closed_days"] == 9
    assert qc[1]["activity"] == "COL_F2" and qc[1]["test"] == "reinforcement_check" and qc[1]["ncr_closed_days"] == 20
    assert qc[2]["activity"] == "SLAB_F3" and qc[2]["test"] == "slab_level_check" and qc[2]["ncr_status"] == "open"

    # Payment issue injections
    p_issues = inj["payment_issues"]
    assert p_issues["ra_05_held"]["bill"] == "RA-05" and p_issues["ra_05_held"]["status"] == "held"
    assert p_issues["ra_03_late"]["bill"] == "RA-03" and p_issues["ra_03_late"]["payment_days_after_submission"] == 45


def test_activity_and_milestone_counts(activities):
    """Verify that there are exactly 38 activities and 5 milestones."""
    assert len(activities) == 38
    milestones = activities[activities["type"] == "milestone"]
    assert len(milestones) == 5
    expected_milestones = ["M_PLINTH", "M_ROOF", "M_STRUCTURE", "M_FINISH", "M_HANDOVER"]
    assert list(milestones["id"]) == expected_milestones


def test_unique_activity_ids(activities):
    """Check that all activity IDs are unique."""
    passed, msg = check_unique_ids(activities)
    assert passed, msg


def test_predecessors_exist(activities):
    """Check that every referenced predecessor exists in activity IDs."""
    passed, msg = check_predecessors_exist(activities)
    assert passed, msg


def test_no_cycles(activities):
    """Check that the activity network contains no cycles."""
    passed, msg = check_no_cycles(activities)
    assert passed, msg


def test_single_start_activity(activities):
    """Check that exactly one activity has no predecessors (single start)."""
    passed, msg = check_single_start(activities)
    assert passed, msg


def test_milestones_have_duration_zero_and_empty_boq(activities):
    """Check that all milestones have duration 0 and empty boq_items."""
    passed, msg = check_milestones(activities)
    assert passed, msg


def test_work_activities_have_boq_mapping(activities):
    """Check that every work activity has a non-empty BOQ mapping."""
    passed, msg = check_work_mappings(activities)
    assert passed, msg


def test_mapped_boq_items_exist(activities, boq):
    """Check that every mapped BOQ item in activities exists in boq.csv."""
    passed, msg = check_mapped_boq_items_exist(activities, boq)
    assert passed, msg


def test_all_boq_items_used(activities, boq):
    """Check that every BOQ item is used by at least one activity."""
    passed, msg = check_all_boq_items_used(activities, boq)
    assert passed, msg


def test_boq_shares_sum_to_one(activities, boq):
    """Check that shares per BOQ item sum to 1.0 within tolerance."""
    passed, msg = check_boq_shares_sum(activities, boq)
    assert passed, msg


def test_steel_share_equals_rcc_share(activities):
    """Check that STEEL share equals RCC_M25 share per activity."""
    passed, msg = check_steel_matches_rcc(activities)
    assert passed, msg


def test_every_boq_item_has_coefficient_row(boq, coefficients):
    """Check that every BOQ item has a corresponding row in material_coefficients.csv."""
    passed, msg = check_coefficient_rows(boq, coefficients)
    assert passed, msg


def test_no_negative_numbers(activities, boq, coefficients):
    """Check that no negative values exist across all data files."""
    passed, msg = check_no_negative_numbers(activities, boq, coefficients)
    assert passed, msg
