"""Test suite runner and summary metrics generator.

Executes full test suite via pytest, parses per-file and total pass/fail statistics,
and exports outputs/test_summary.json.
"""

import json
from pathlib import Path
import re
import subprocess
import sys


def run_tests_and_summarize() -> dict:
    """Run pytest with verbose output, parse results, write test_summary.json, and print summary."""
    repo_root = Path(__file__).resolve().parent.parent
    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    cmd = [python_cmd, "-m", "pytest", "-v"]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)

    passed_count = 0
    failed_count = 0
    by_file: dict[str, int] = {}

    pattern = re.compile(r"^(tests[\\/][^:]+\.py)::(\S+)\s+(PASSED|FAILED|ERROR)")

    for line in proc.stdout.splitlines():
        line = line.strip()
        m = pattern.match(line)
        if m:
            file_path = m.group(1).replace("\\", "/")
            status = m.group(3)
            if status == "PASSED":
                passed_count += 1
                by_file[file_path] = by_file.get(file_path, 0) + 1
            else:
                failed_count += 1

    total_count = passed_count + failed_count
    summary = {
        "passed": passed_count,
        "failed": failed_count,
        "total": total_count,
        "by_file": dict(sorted(by_file.items())),
    }

    out_path = repo_root / "outputs" / "test_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)

    print("=" * 60)
    print("TEST SUITE EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Total Tests Run: {total_count}")
    print(f"Passed:          {passed_count}")
    print(f"Failed:          {failed_count}")
    print("-" * 60)
    print("Passed Tests by Module:")
    for f_name, cnt in summary["by_file"].items():
        print(f"  - {f_name:<36}: {cnt:>2} tests")
    print("=" * 60)
    print(f"Summary written to: {out_path.relative_to(repo_root)}")

    if failed_count > 0:
        sys.exit(1)

    return summary


if __name__ == "__main__":
    run_tests_and_summarize()
