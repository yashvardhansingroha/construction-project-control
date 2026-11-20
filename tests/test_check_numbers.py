"""Tests for number tracing and verification audit (scripts/check_numbers.py)."""

from pathlib import Path
import json
import pytest

from scripts.check_numbers import build_known_numbers, check_text, check_pdf


def test_month_6_pdf_passes_number_check():
    """Verify that every number and date in report_month_06.pdf is strictly traceable."""
    pdf_path = Path("outputs/report_month_06.pdf")
    assert pdf_path.exists(), "outputs/report_month_06.pdf must exist"

    known = build_known_numbers()
    unknown = check_pdf(pdf_path, known)
    assert len(unknown) == 0, f"Found untraced numbers in PDF report: {unknown}"


def test_fake_sentence_unauthorized_numbers_detected():
    """Verify that check_text catches invented numbers ('SPI 0.812 and EAC Rs 4,01,23,456')."""
    known = build_known_numbers()
    fake_text = "Project status: SPI 0.812 and EAC Rs 4,01,23,456 as of data date."

    unknown = check_text(fake_text, known)
    unauthorized_tokens = [tok for tok, _ in unknown]

    assert len(unknown) == 2, f"Expected exactly 2 unauthorized numbers, found: {unknown}"
    assert "0.812" in unauthorized_tokens, "Invented SPI 0.812 was not caught"
    assert any("4,01,23,456" in tok for tok in unauthorized_tokens), "Invented EAC Rs 4,01,23,456 was not caught"


def test_real_number_indian_format_accepted():
    """Verify that legitimate numbers from results.json written in Indian format are accepted."""
    known = build_known_numbers()
    with open("outputs/results.json", "r", encoding="utf-8") as f:
        res = json.load(f)

    # True month 6 EV is 18,743,829
    m6_ev = res["month_6_headline"]["ev"]
    legit_sentence = f"Cumulative Earned Value placed through Month 6 reached Rs {m6_ev:,}."

    unknown = check_text(legit_sentence, known)
    assert len(unknown) == 0, f"Legitimate number flagged as unknown: {unknown}"


def test_trailing_punctuation_stripped():
    """Verify that trailing punctuation (comma, period, colon, semicolon, paren) is stripped before matching."""
    known = build_known_numbers()
    # "Rs 9,59,642," has a trailing comma; should match retention_held_to_date
    sentence = "Cumulative retention held to date is Rs 9,59,642, while SLAB_F2 float is 0 wd."
    unknown = check_text(sentence, known)
    assert len(unknown) == 0, f"Trailing punctuation caused false alarm: {unknown}"


def test_baseline_cpm_floats_accepted():
    """Verify that CPM activity floats from baseline_cpm in results.json (e.g. BW_GF 143 wd) are accepted."""
    known = build_known_numbers()
    with open("outputs/results.json", "r", encoding="utf-8") as f:
        res = json.load(f)

    assert "baseline_cpm" in res, "baseline_cpm must be present in results.json"
    assert "retention_held_to_date" in res, "retention_held_to_date must be present in results.json"

    sentence = "BW_GF float is 143 wd while SLAB_F2 float is 0 wd."
    unknown = check_text(sentence, known)
    assert len(unknown) == 0, f"CPM float flagged as unknown: {unknown}"
