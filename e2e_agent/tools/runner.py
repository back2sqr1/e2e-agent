"""Skills for the verifier agent: execute the generated test and collect evidence."""

import asyncio
import json
import os

from google.adk.tools import ToolContext

from ..config import RUNS_DIR, TEST_FILE, TEST_TIMEOUT_SECONDS, WORKSPACE_DIR


def _walk_specs(suite: dict):
    for spec in suite.get("specs", []):
        yield spec
    for child in suite.get("suites", []):
        yield from _walk_specs(child)


def _normalize(pw_report: dict) -> dict:
    """Flatten Playwright's JSON report into the per-step shape the verifier audits."""
    steps, errors, video, trace = [], [], None, None
    status = "passed" if pw_report.get("stats", {}).get("unexpected", 1) == 0 else "failed"
    for suite in pw_report.get("suites", []):
        for spec in _walk_specs(suite):
            for t in spec.get("tests", []):
                for result in t.get("results", []):
                    for s in result.get("steps", []):
                        # step titles are the checklist ids
                        record = {"id": s["title"].split(":")[0].strip(),
                                  "title": s["title"],
                                  "status": "failed" if s.get("error") else "passed",
                                  "duration_ms": s.get("duration")}
                        if s.get("error"):
                            record["error"] = str(s["error"].get("message", s["error"]))[:1500]
                        steps.append(record)
                    for err in result.get("errors", []):
                        errors.append(str(err.get("message", err))[:1500])
                    for att in result.get("attachments", []):
                        if att.get("name") == "video":
                            video = att.get("path")
                        elif att.get("name") == "trace":
                            trace = att.get("path")
    return {"status": status, "steps": steps, "errors": errors[:5],
            "video": video, "trace": trace}


async def run_e2e_test(tool_context: ToolContext) -> dict:
    """Execute the saved Playwright TypeScript test and return the evidence.

    Runs `npx playwright test` on workspace/test_generated.spec.ts in a fresh
    browser. Playwright records a video and trace of the whole session and a
    per-step JSON report; all of it is returned here so the execution can be
    judged against the checklist. Steps that never ran (aborted after an
    earlier failure) are simply absent from the report.
    """
    if not TEST_FILE.exists():
        return {"error": "no test has been saved yet — the coder agent must call save_test_code first"}
    if not (WORKSPACE_DIR / "node_modules").exists():
        return {"error": "workspace/node_modules missing — run `npm install` in workspace/ "
                         "to install @playwright/test before tests can execute"}

    run_no = int(tool_context.state.get("run_count", 0)) + 1
    tool_context.state["run_count"] = run_no
    run_dir = RUNS_DIR / f"run_{run_no:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["E2E_RUN_DIR"] = str(run_dir)

    proc = await asyncio.create_subprocess_exec(
        "npx", "playwright", "test", "--config=playwright.config.ts",
        cwd=str(WORKSPACE_DIR), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TEST_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        stdout, stderr = await proc.communicate()

    report = None
    report_file = run_dir / "report.json"
    if report_file.exists():
        try:
            report = _normalize(json.loads(report_file.read_text()))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    result = {
        "run": run_no,
        "run_dir": str(run_dir),
        "exit_code": proc.returncode,
        "timed_out": timed_out,
        "report": report,
        "stdout_tail": stdout.decode(errors="replace")[-3000:],
        "stderr_tail": stderr.decode(errors="replace")[-3000:],
    }
    tool_context.state["last_run"] = {
        "run": run_no,
        "status": (report or {}).get("status", "crashed"),
        "video": (report or {}).get("video"),
        "trace": (report or {}).get("trace"),
        "run_dir": str(run_dir),
    }
    return result
