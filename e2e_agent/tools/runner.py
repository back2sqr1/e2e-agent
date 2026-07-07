"""Skills for the verifier agent: execute the generated test and collect evidence."""

import asyncio
import json
import os
import sys

from google.adk.tools import ToolContext

from ..config import PROJECT_ROOT, RUNS_DIR, TEST_FILE, TEST_TIMEOUT_SECONDS


async def run_e2e_test(tool_context: ToolContext) -> dict:
    """Execute the saved Playwright test in a fresh browser and return the evidence.

    Runs workspace/test_generated.py as a subprocess. The harness records a
    video and trace of the whole session and a per-step report; all of it is
    returned here so the execution can be judged against the checklist.
    """
    if not TEST_FILE.exists():
        return {"error": "no test has been saved yet — the coder agent must call save_test_code first"}

    run_no = int(tool_context.state.get("run_count", 0)) + 1
    tool_context.state["run_count"] = run_no
    run_dir = RUNS_DIR / f"run_{run_no:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["E2E_RUN_DIR"] = str(run_dir)
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(TEST_FILE),
        cwd=str(PROJECT_ROOT), env=env,
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
            report = json.loads(report_file.read_text())
        except json.JSONDecodeError:
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
