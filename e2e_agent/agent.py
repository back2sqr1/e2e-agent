"""Agent pipeline: plan -> (find locators -> write code -> run & verify)* -> report.

Exposes `root_agent` for `adk web` / `adk run e2e_agent`.
"""

from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
from google.adk.tools import exit_loop
from pydantic import BaseModel, Field

from . import prompts
from .config import CODER_MODEL, DEFAULT_MODEL, MAX_ITERATIONS, resolve_model

_default_model = resolve_model(DEFAULT_MODEL)
_coder_model = resolve_model(CODER_MODEL)
from .tools.coding import get_current_test_code, save_test_code
from .tools.locators import inspect_page, probe_locator
from .tools.runner import run_e2e_test


# --- Test plan schema (what the planner must produce) -------------------

class ChecklistItem(BaseModel):
    id: str = Field(description="Short kebab-case step id, e.g. 'submit-search'")
    description: str = Field(description="The single user action or observation")
    success_criteria: str = Field(description="Observable condition proving the step worked")


class TestPlan(BaseModel):
    target_url: str = Field(description="Exact URL under test, or 'MISSING'")
    test_name: str = Field(description="Short kebab-case name for the flow")
    checklist: list[ChecklistItem]
    notes: str = Field(default="", description="Assumptions or open questions")


# --- Agents --------------------------------------------------------------

planner_agent = LlmAgent(
    name="planner",
    model=_default_model,
    description="Turns the user's testing request into a verifiable checklist.",
    instruction=prompts.PLANNER_INSTRUCTION,
    output_schema=TestPlan,
    output_key="test_plan",
)

locator_agent = LlmAgent(
    name="locator_scout",
    model=_default_model,
    description="Inspects the live page and finds a proven locator for every checklist step.",
    instruction=prompts.LOCATOR_INSTRUCTION,
    tools=[inspect_page, probe_locator, exit_loop],
    output_key="locator_report",
)

coder_agent = LlmAgent(
    name="test_writer",
    model=_coder_model,
    description="Writes (and rewrites) the Playwright test script from the plan and locators.",
    instruction=prompts.CODER_INSTRUCTION,
    tools=[save_test_code, get_current_test_code],
    output_key="code_status",
)

verifier_agent = LlmAgent(
    name="verifier",
    model=_default_model,
    description="Runs the test, audits the recorded evidence against the checklist, "
                "and either approves (ending the loop) or files issues.",
    instruction=prompts.VERIFIER_INSTRUCTION,
    tools=[run_e2e_test, probe_locator, exit_loop],
    output_key="issues",
)

refinement_loop = LoopAgent(
    name="refinement_loop",
    description="Locate -> code -> verify, repeated until the test passes or the "
                "iteration limit is reached.",
    sub_agents=[locator_agent, coder_agent, verifier_agent],
    max_iterations=MAX_ITERATIONS,
)

reporter_agent = LlmAgent(
    name="reporter",
    model=_default_model,
    description="Summarizes the final outcome and artifact locations for the user.",
    instruction=prompts.REPORTER_INSTRUCTION,
)

root_agent = SequentialAgent(
    name="e2e_test_pipeline",
    description="Generates, runs, and self-corrects a Playwright E2E test from a "
                "natural-language description.",
    sub_agents=[planner_agent, refinement_loop, reporter_agent],
)
