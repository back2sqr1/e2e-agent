"""Runtime harness that generated Playwright tests are written against.

The coder agent generates a script of the form:

    from e2e_agent.harness import E2ETest

    with E2ETest("checkout-flow") as t:
        page = t.page
        with t.step("open-home", "Open the store homepage"):
            page.goto("https://example.com")
        with t.step("search", "Search for a backpack"):
            page.get_by_placeholder("Search").fill("backpack")

The harness takes care of everything the verifier agent needs to "watch"
the execution afterwards:

- launches Chromium and records a video of the whole session
- records a Playwright trace (screenshots + DOM snapshots per action)
- captures browser console messages and page errors
- records every step's outcome (passed / failed / not reached) with
  timing, error details, and a screenshot at the moment of failure
- writes it all to <run_dir>/report.json

A failing step aborts the remaining steps but the report, video, and
trace are always written. The process exits non-zero on failure.
"""

import json
import os
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


class StepFailed(Exception):
    """Raised internally to abort the test after a step fails."""


class E2ETest:
    def __init__(self, name: str = "e2e-test", headless: bool | None = None,
                 viewport: tuple[int, int] = (1280, 720),
                 action_timeout_ms: int | None = None):
        self.name = name
        self.run_dir = Path(os.environ.get("E2E_RUN_DIR", "workspace/runs/adhoc")).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if headless is None:
            headless = os.environ.get("E2E_HEADLESS", "1") != "0"
        self.headless = headless
        self.viewport = viewport
        self.action_timeout_ms = action_timeout_ms or int(os.environ.get("E2E_ACTION_TIMEOUT_MS", "10000"))

        self.steps: list[dict] = []
        self.console_messages: list[dict] = []
        self.page_errors: list[str] = []
        self.unhandled_error: str | None = None
        self._started = time.time()

    # -- lifecycle -----------------------------------------------------

    def __enter__(self) -> "E2ETest":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            record_video_dir=str(self.run_dir / "video"),
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
        )
        self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
        self._context.set_default_timeout(self.action_timeout_ms)
        # Web-first assertions default to a 5s retry window regardless of the
        # action timeout; keep the two consistent.
        expect.set_options(timeout=self.action_timeout_ms)
        self.page = self._context.new_page()
        self.page.on("console", self._on_console)
        self.page.on("pageerror", lambda err: self.page_errors.append(str(err)[:500]))
        return self

    def __exit__(self, exc_type, exc, tb):
        aborted_by_step = exc_type is StepFailed
        if exc is not None and not aborted_by_step:
            # Exception outside any step (or in setup code)
            self.unhandled_error = "".join(traceback.format_exception(exc_type, exc, tb))[-2000:]
        self._finalize()
        if self.passed:
            return True
        # Replace whatever was in flight with a clean non-zero exit so the
        # runner can rely on the exit code; the report has the details.
        raise SystemExit(1)

    # -- steps ---------------------------------------------------------

    @contextmanager
    def step(self, step_id: str, description: str = ""):
        record = {"id": step_id, "description": description, "status": "running",
                  "started_at": round(time.time() - self._started, 2)}
        self.steps.append(record)
        t0 = time.time()
        try:
            yield
            record["status"] = "passed"
        except Exception as e:
            record["status"] = "failed"
            record["error"] = f"{type(e).__name__}: {e}"[:1500]
            shot = self.run_dir / f"failure_{step_id}.png"
            try:
                self.page.screenshot(path=str(shot), full_page=False)
                record["failure_screenshot"] = str(shot)
            except Exception:
                pass
            raise StepFailed(step_id) from e
        finally:
            record["duration_s"] = round(time.time() - t0, 2)

    # -- internals -----------------------------------------------------

    def _on_console(self, msg):
        if len(self.console_messages) < 200:
            self.console_messages.append({"type": msg.type, "text": msg.text[:300]})

    @property
    def passed(self) -> bool:
        return (self.unhandled_error is None
                and bool(self.steps)
                and all(s["status"] == "passed" for s in self.steps))

    def _finalize(self):
        trace_path = self.run_dir / "trace.zip"
        try:
            self._context.tracing.stop(path=str(trace_path))
        except Exception:
            trace_path = None
        try:
            self._context.close()  # flushes the video file
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass

        videos = sorted((self.run_dir / "video").glob("*.webm"),
                        key=lambda p: p.stat().st_mtime) if (self.run_dir / "video").exists() else []
        report = {
            "name": self.name,
            "status": "passed" if self.passed else "failed",
            "steps": self.steps,
            "unhandled_error": self.unhandled_error,
            "console_messages": self.console_messages[-50:],
            "page_errors": self.page_errors[:20],
            "video": str(videos[-1]) if videos else None,
            "trace": str(trace_path) if trace_path else None,
            "duration_s": round(time.time() - self._started, 2),
        }
        (self.run_dir / "report.json").write_text(json.dumps(report, indent=2))
        print(f"[harness] {report['status'].upper()} — report: {self.run_dir / 'report.json'}")
