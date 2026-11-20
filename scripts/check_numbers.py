"""Number tracing and consistency validation utility.

Validates that every numeric value, currency amount, percentage, and date appearing
in executive reports (PDF, README) is strictly traceable to results.json, project.yaml,
or test_summary.json, with zero invented numbers.
"""

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
from typing import Any, List, Optional, Set, Tuple, Union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from src.report import format_inr, format_date_str
from src.data_io import load_activities, load_boq
from src.simulate import simulate


def build_known_numbers(repo_root: Optional[Path] = None) -> Set[str]:
    """Compile exhaustive set of authorized numeric and date representations.

    Sources:
    1. Structural allow-list (small, explicit, documented).
    2. outputs/results.json (flattened: raw, rounded, formatted).
    3. config/project.yaml (parameters, dates, thresholds).
    4. outputs/test_summary.json (test execution counts).
    5. Baseline activity durations and simulated actual durations.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    known: Set[str] = set()

    # 1. Structural Allow-list (Explicit, small, documented)
    # - G+4 building structure notation, A4 paper standard
    # - Calendar year 2026
    # - Single digit integers and standard month numbers (1 to 12)
    allow_list = {
        "G+4", "4", "A4", "2026",
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
    }
    known.update(allow_list)

    def add_numeric(val: Union[int, float]) -> None:
        if val is None:
            return
        known.add(str(val))
        int_val = int(round(val))
        known.add(str(int_val))
        known.add(f"{val:.1f}")
        known.add(f"{val:.2f}")
        known.add(f"{val:.3f}")
        known.add(f"{val:+.1f}%")
        known.add(f"{val:.1f}%")
        known.add(f"{val:+.2f}%")
        known.add(f"{val:.2f}%")
        known.add(f"{val:.0f}%")
        known.add(f"{int_val:,}")
        known.add(f"+{int_val}")
        known.add(f"-{int_val}")

        inr_fmt = format_inr(int_val)
        known.add(inr_fmt)
        known.add(inr_fmt.replace("Rs ", "").replace("-Rs ", "-"))

        if val < 0:
            abs_int = abs(int_val)
            abs_inr = format_inr(abs_int)
            known.add(str(abs_int))
            known.add(f"{abs_int:,}")
            known.add(abs_inr)
            known.add(abs_inr.replace("Rs ", ""))

        if abs(val) <= 1.0:
            known.add(f"{val * 100:.1f}%")
            known.add(f"{val * 100:.0f}%")
            known.add(f"{(1.0 - val) * 100:.0f}%")
            known.add(f"{(1.0 - val) * 100:.1f}%")

    def add_date_str(s: str) -> None:
        known.add(s)
        s_clean = s.strip()
        # ISO date matching
        if len(s_clean) == 10 and s_clean.count("-") == 2:
            try:
                d = date.fromisoformat(s_clean)
                known.add(d.strftime("%d %b %Y"))
                known.add(f"{d.day} {d.strftime('%b')} {d.year}")
                known.add(d.strftime("%b %Y"))
                known.add(d.strftime("%B %Y"))
            except ValueError:
                pass
        # Formatted dates inside strings (e.g. Achieved (19 Feb 2026))
        d_matches = re.findall(r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b", s)
        for dm in d_matches:
            known.add(dm)

    def recurse(data: Any) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                recurse(v)
        elif isinstance(data, list):
            for item in data:
                recurse(item)
        elif isinstance(data, (int, float)):
            add_numeric(data)
        elif isinstance(data, str):
            add_date_str(data)

    # 2. Results JSON
    results_path = repo_root / "outputs" / "results.json"
    if results_path.exists():
        with open(results_path, "r", encoding="utf-8") as f:
            res_json = json.load(f)
        recurse(res_json)

    # 3. Project Config
    config_path = repo_root / "config" / "project.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg_yaml = yaml.safe_load(f)
        recurse(cfg_yaml)

    # 4. Test Summary JSON
    summary_path = repo_root / "outputs" / "test_summary.json"
    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as f:
            sum_json = json.load(f)
        recurse(sum_json)

    # 5. Baseline & Simulated Durations
    try:
        acts = load_activities()
        boq = load_boq()
        add_numeric(len(acts))
        for _, r in acts.iterrows():
            add_numeric(int(r["duration_days"]))

        if config_path.exists():
            sim = simulate(cfg_yaml, acts, boq, through_month=6)
            for _, dur in sim.actual_durations.items():
                add_numeric(dur)
    except Exception:
        pass

    return known


def check_text(text: str, known_numbers: Optional[Set[str]] = None) -> List[Tuple[str, str]]:
    """Scan text for all numeric and date tokens, returning unknown tokens with context.

    Returns:
        List of tuples: (unrecognized_token, surrounding_context)
    """
    if known_numbers is None:
        known_numbers = build_known_numbers()

    # Pattern matches standard ISO dates, text dates, formatted Indian/Western currencies, and numbers
    pat = re.compile(
        r"\b\d{4}-\d{2}-\d{2}\b"
        r"|\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b"
        r"|-?Rs\.?\s*[\d,]+"
        r"|[-+]?\b\d+(?:,\d+)*(?:\.\d+)?%?"
    )
    unknown: List[Tuple[str, str]] = []

    for m in pat.finditer(text):
        tok = m.group().strip()
        start, end = m.span()

        # Disregard numeric segments that are part of alphanumeric identifiers (e.g. NCR-003, RA-05, SLAB_F2)
        before = text[max(0, start - 4):start]
        after = text[end:min(len(text), end + 4)]
        if re.search(r"[A-Za-z]-?$", before) or re.search(r"^[A-Za-z]", after):
            continue

        # Strip trailing punctuation (e.g. comma, period, semicolon, colon, paren)
        tok = tok.rstrip(",.;:)")
        if not tok:
            continue

        # Check membership in known set
        clean = tok.lstrip("+-").rstrip("%")
        inr_clean = tok.replace("Rs ", "").replace("-Rs ", "-").replace("Rs.", "").strip().rstrip(",.;:)")

        is_authorized = (
            tok in known_numbers
            or clean in known_numbers
            or inr_clean in known_numbers
            or tok.replace(" ", "") in known_numbers
            or tok.replace(",", "") in known_numbers
            or clean.replace(",", "") in known_numbers
            or inr_clean.replace(",", "") in known_numbers
        )

        if not is_authorized:
            surrounding = text[max(0, start - 30):min(len(text), end + 30)].replace("\n", " ").strip()
            unknown.append((tok, surrounding))

    return unknown


def check_pdf(pdf_path: Union[str, Path], known_numbers: Optional[Set[str]] = None) -> List[Tuple[str, str]]:
    """Extract and validate all numbers in a PDF document."""
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    full_text = "\n".join([page.extract_text() or "" for page in reader.pages])
    return check_text(full_text, known_numbers)


def check_file(file_path: Union[str, Path], known_numbers: Optional[Set[str]] = None) -> List[Tuple[str, str]]:
    """Validate all numbers in a text or markdown file."""
    path = Path(file_path)
    if not path.exists():
        print(f"[SKIP] File does not exist: {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return check_text(text, known_numbers)


def main() -> None:
    """CLI entrypoint validating numbers across specified PDF, README, and Markdown files."""
    parser = argparse.ArgumentParser(description="Check numbers in outputs against known data sources.")
    parser.add_argument("--pdf", help="Path to PDF report to inspect")
    parser.add_argument("--readme", help="Path to README.md file to inspect")
    parser.add_argument("--md", action="append", help="Path to Markdown file to inspect")
    args = parser.parse_args()

    known = build_known_numbers()
    all_unknown: List[Tuple[str, str, str]] = []

    if args.pdf:
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            print(f"[ERROR] PDF file not found: {pdf_path}")
            sys.exit(1)
        unknown_pdf = check_pdf(pdf_path, known)
        for tok, ctx in unknown_pdf:
            all_unknown.append((str(pdf_path), tok, ctx))

    if args.readme:
        readme_path = Path(args.readme)
        if readme_path.exists():
            unknown_readme = check_file(readme_path, known)
            for tok, ctx in unknown_readme:
                all_unknown.append((str(readme_path), tok, ctx))
        else:
            print(f"[INFO] README file not found: {readme_path} (skipped)")

    if args.md:
        for md_arg in args.md:
            md_path = Path(md_arg)
            if md_path.exists():
                unknown_md = check_file(md_path, known)
                for tok, ctx in unknown_md:
                    all_unknown.append((str(md_path), tok, ctx))
            else:
                print(f"[ERROR] Markdown file not found: {md_path}")
                all_unknown.append((str(md_path), "FILE_NOT_FOUND", f"File does not exist: {md_path}"))

    print("=" * 64)
    print("NUMBER TRACING AUDIT RESULTS")
    print("=" * 64)

    if not all_unknown:
        print("[PASS] All numbers are verified and traceable to results/config.")
        print("=" * 64)
        sys.exit(0)
    else:
        print(f"[FAIL] Found {len(all_unknown)} untraced or unauthorized numbers:")
        for source, tok, ctx in all_unknown:
            print(f"  - [{source}] Unknown token: '{tok}'")
            print(f"    Context: ... {ctx} ...")
        print("=" * 64)
        sys.exit(1)


if __name__ == "__main__":
    main()
