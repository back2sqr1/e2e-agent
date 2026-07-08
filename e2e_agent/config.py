"""Central configuration for the e2e-agent pipeline."""

import os
from pathlib import Path

# Project layout
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
RUNS_DIR = WORKSPACE_DIR / "runs"
TEST_FILE = WORKSPACE_DIR / "test_generated.spec.ts"

# Models. Plain Gemini ids ("gemini-2.5-flash") use ADK's native client with
# GOOGLE_API_KEY. Ids with a provider prefix are routed through LiteLLM —
# e.g. "openrouter/anthropic/claude-sonnet-4.5" or "openrouter/google/gemini-2.5-pro"
# with OPENROUTER_API_KEY set. Coder benefits from a stronger model.
DEFAULT_MODEL = os.environ.get("E2E_AGENT_MODEL", "gemini-2.5-flash")
CODER_MODEL = os.environ.get("E2E_CODER_MODEL", DEFAULT_MODEL)


def resolve_model(model_id: str):
    """Return what LlmAgent(model=...) needs for this model id."""
    if "/" not in model_id:
        return model_id  # native Gemini
    from google.adk.models.lite_llm import LiteLlm
    return LiteLlm(model=model_id)

# Refinement loop
MAX_ITERATIONS = int(os.environ.get("E2E_MAX_ITERATIONS", "4"))

# Browser behavior
HEADLESS = os.environ.get("E2E_HEADLESS", "1") != "0"
ACTION_TIMEOUT_MS = int(os.environ.get("E2E_ACTION_TIMEOUT_MS", "10000"))
TEST_TIMEOUT_SECONDS = int(os.environ.get("E2E_TEST_TIMEOUT_SECONDS", "240"))
