"""Centralized project paths."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLEANED_DIR = DATA_DIR / "cleaned"
ANALYSIS_READY_DIR = DATA_DIR / "analysis_ready"
REPORTS_DIR = PROJECT_ROOT / "reports"
