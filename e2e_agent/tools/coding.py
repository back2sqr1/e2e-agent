"""Skills for the coder agent: save and re-read the generated test script.

The generated test is TypeScript (@playwright/test). Saving syntax-checks it
by asking Playwright to list the tests in the workspace — that transpiles the
spec without running it, so syntax errors surface with file/line info.
"""

import json
import re
import subprocess

from google.adk.tools import ToolContext

from ..config import TEST_FILE, WORKSPACE_DIR


def _strip_fences(code: str) -> str:
    match = re.search(r"```(?:\w+)?\s*\n(.*?)```", code, re.DOTALL)
    return match.group(1) if match else code


_LOCATOR_ARG_RE = re.compile(
    r"\.(?:getByTestId|getByRole|getByLabel|getByPlaceholder|getByText"
    r"|getByAltText|getByTitle|locator)\(\s*[\"'`]([^\"'`]+)[\"'`]"
)
# option-object values the scout must vouch for: accessible names and filter text
_NAME_OPTION_RE = re.compile(r"\b(?:name|hasText)\s*:\s*[\"'`]([^\"'`]+)[\"'`]")

# getByRole's first argument; no point flagging these against the report.
_ARIA_ROLES = {
    "alert", "button", "checkbox", "combobox", "dialog", "form", "heading",
    "link", "list", "listitem", "menu", "menuitem", "option", "radio",
    "searchbox", "slider", "spinbutton", "tab", "table", "textbox",
}


def _unvouched_locators(code: str, locator_report: object) -> list[str]:
    """Locator values used in the code that the locator report never mentions."""
    report_text = locator_report if isinstance(locator_report, str) else json.dumps(locator_report or {})
    if not report_text.strip():
        return []
    values = set(_LOCATOR_ARG_RE.findall(code)) | set(_NAME_OPTION_RE.findall(code))
    return sorted(v for v in values
                  if v.lower() not in _ARIA_ROLES and v not in report_text)


def _list_tests() -> str | None:
    """Transpile-check the saved spec via `playwright test --list`.

    Returns an error string on failure, None when the spec parses cleanly.
    """
    if not (WORKSPACE_DIR / "node_modules").exists():
        return None  # can't check without deps; the runner will surface it
    try:
        proc = subprocess.run(
            ["npx", "playwright", "test", "--list", "--config=playwright.config.ts"],
            cwd=WORKSPACE_DIR, capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None  # tooling problem, not a code problem; don't block the save
    if proc.returncode != 0:
        return (proc.stdout + "\n" + proc.stderr).strip()[-1500:]
    return None


def save_test_code(code: str, tool_context: ToolContext) -> dict:
    """Save the generated Playwright TypeScript test, replacing any previous version.

    The code is transpile-checked before being accepted; on a syntax error the
    previous version is restored and the error location is returned.

    Args:
        code: Complete TypeScript source of the test (markdown fences are stripped).
    """
    code = _strip_fences(code).strip() + "\n"

    previous = TEST_FILE.read_text() if TEST_FILE.exists() else None
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    TEST_FILE.write_text(code)

    syntax_error = _list_tests()
    if syntax_error is not None:
        if previous is None:
            TEST_FILE.unlink(missing_ok=True)
        else:
            TEST_FILE.write_text(previous)
        return {"saved": False, "error": f"TypeScript/Playwright error: {syntax_error}"}

    warnings = []
    if "from '@playwright/test'" not in code and 'from "@playwright/test"' not in code:
        warnings.append("code does not import from @playwright/test — the runner "
                        "requires it for video/trace/report capture")
    if "test.step(" not in code:
        warnings.append("no test.step(...) blocks found — the verifier cannot check "
                        "checklist items without steps")
    for value in _unvouched_locators(code, tool_context.state.get("locator_report")):
        warnings.append(
            f"locator value {value!r} appears nowhere in the locator report — "
            "it may be invented. Use a locator the scout verified, or flag the "
            "step so the scout probes this element on the next iteration.")

    return {"saved": True, "path": str(TEST_FILE),
            "lines": code.count("\n"), "warnings": warnings}


def get_current_test_code() -> dict:
    """Read the currently saved test script (the version the last run executed)."""
    if not TEST_FILE.exists():
        return {"exists": False, "code": None}
    return {"exists": True, "path": str(TEST_FILE), "code": TEST_FILE.read_text()}
