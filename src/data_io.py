"""Data loading utilities for project configuration, schedule activities, BOQ, and material coefficients."""

from pathlib import Path
from typing import Any, Dict, List, Union
import pandas as pd
import yaml


def get_repo_root() -> Path:
    """Return the absolute path to the repository root directory."""
    # __file__ is in src/data_io.py, so parent is src/, parent.parent is repo root
    return Path(__file__).resolve().parent.parent


def _resolve_path(path: Union[str, Path]) -> Path:
    """Resolve a path relative to the repo root if it is not already absolute."""
    p = Path(path)
    if not p.is_absolute():
        return get_repo_root() / p
    return p


def load_config(path: Union[str, Path] = "config/project.yaml") -> Dict[str, Any]:
    """Load and parse the project configuration YAML file."""
    file_path = _resolve_path(path)
    with open(file_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def _parse_predecessors(raw: Any) -> List[str]:
    """Parse a semicolon-separated string of predecessor IDs into a list."""
    if pd.isna(raw) or raw is None:
        return []
    s = str(raw).strip()
    if not s:
        return []
    # Split by semicolon and strip whitespace
    parts = s.split(";")
    result = []
    for item in parts:
        cleaned = item.strip()
        if cleaned:
            result.append(cleaned)
    return result


def _parse_boq_items(raw: Any) -> Dict[str, float]:
    """Parse a semicolon-separated string of ITEM:share pairs into a dictionary."""
    if pd.isna(raw) or raw is None:
        return {}
    s = str(raw).strip()
    if not s:
        return {}
    # Split ITEM:share pairs separated by semicolon
    mapping = {}
    pairs = s.split(";")
    for pair in pairs:
        pair = pair.strip()
        if not pair:
            continue
        item_id, share_str = pair.split(":")
        mapping[item_id.strip()] = float(share_str.strip())
    return mapping


def load_activities(path: Union[str, Path] = "data/activities.csv") -> pd.DataFrame:
    """Load activities CSV and parse predecessors into lists and boq_items into dicts."""
    file_path = _resolve_path(path)
    df = pd.read_csv(file_path, dtype={"predecessors": str, "boq_items": str})

    # Parse predecessors into list of IDs
    parsed_preds = []
    for val in df["predecessors"]:
        parsed_preds.append(_parse_predecessors(val))
    df["predecessors"] = parsed_preds

    # Parse boq_items into dict of {item_id: share}
    parsed_boq = []
    for val in df["boq_items"]:
        parsed_boq.append(_parse_boq_items(val))
    df["boq_items"] = parsed_boq

    return df


def load_boq(path: Union[str, Path] = "data/boq.csv") -> pd.DataFrame:
    """Load the Bill of Quantities (BOQ) CSV file."""
    file_path = _resolve_path(path)
    return pd.read_csv(file_path)


def load_coefficients(path: Union[str, Path] = "data/material_coefficients.csv") -> pd.DataFrame:
    """Load the material consumption coefficients CSV file."""
    file_path = _resolve_path(path)
    return pd.read_csv(file_path)
