"""Skills for the coder agent: save and re-read the generated test script."""

import ast
import re

from ..config import TEST_FILE, WORKSPACE_DIR


def _strip_fences(code: str) -> str:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", code, re.DOTALL)
    return match.group(1) if match else code


def save_test_code(code: str) -> dict:
    """Save the generated Playwright test script, replacing any previous version.

    The code is syntax-checked before saving; on a syntax error nothing is
    written and the error location is returned so it can be fixed.

    Args:
        code: Complete Python source of the test (markdown fences are stripped).
    """
    code = _strip_fences(code).strip() + "\n"
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {"saved": False, "error": f"SyntaxError: {e.msg} at line {e.lineno}: {e.text!r}"}

    warnings = []
    if "from e2e_agent.harness import E2ETest" not in code:
        warnings.append("code does not import E2ETest from e2e_agent.harness — "
                        "the runner requires the harness for video/report capture")
    if "t.step(" not in code and ".step(" not in code:
        warnings.append("no t.step(...) blocks found — the verifier cannot check "
                        "checklist items without steps")

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    TEST_FILE.write_text(code)
    return {"saved": True, "path": str(TEST_FILE),
            "lines": code.count("\n"), "warnings": warnings}


def get_current_test_code() -> dict:
    """Read the currently saved test script (the version the last run executed)."""
    if not TEST_FILE.exists():
        return {"exists": False, "code": None}
    return {"exists": True, "path": str(TEST_FILE), "code": TEST_FILE.read_text()}
