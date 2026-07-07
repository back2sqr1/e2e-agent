"""Central configuration for the e2e-agent pipeline."""

import os
from pathlib import Path

# Project layout
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
RUNS_DIR = WORKSPACE_DIR / "runs"
TEST_FILE = WORKSPACE_DIR / "test_generated.py"

# Models (any Gemini model id works; coder benefits from a stronger model)
DEFAULT_MODEL = os.environ.get("E2E_AGENT_MODEL", "gemini-2.5-flash")
CODER_MODEL = os.environ.get("E2E_CODER_MODEL", DEFAULT_MODEL)

# Refinement loop
MAX_ITERATIONS = int(os.environ.get("E2E_MAX_ITERATIONS", "4"))

# Browser behavior
HEADLESS = os.environ.get("E2E_HEADLESS", "1") != "0"
ACTION_TIMEOUT_MS = int(os.environ.get("E2E_ACTION_TIMEOUT_MS", "10000"))
TEST_TIMEOUT_SECONDS = int(os.environ.get("E2E_TEST_TIMEOUT_SECONDS", "240"))
