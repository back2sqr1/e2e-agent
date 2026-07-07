# e2e-agent

A multi-agent E2E testing system built on the [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) and [Playwright](https://playwright.dev/python/). You describe what to test in plain English; the agents find the right elements on the live page, write a Playwright test, run it with video + trace recording, diagnose failures, and rewrite the test until it passes and matches your intent.

## Architecture

```
user prompt
    │
    ▼
┌──────────┐   verifiable checklist (JSON in session state)
│ planner  │──────────────────────────────────────────────┐
└──────────┘                                              │
    ▼                                                     │
╔═ refinement_loop (max E2E_MAX_ITERATIONS) ═════════════╗│
║ ┌───────────────┐ skills: inspect_page, probe_locator  ║│
║ │ locator_scout │  → proven locator per checklist step ║│
║ └───────┬───────┘                                      ║│
║ ┌───────▼───────┐ skills: save_test_code,              ║│
║ │ test_writer   │         get_current_test_code        ║│
║ └───────┬───────┘  → workspace/test_generated.py       ║│
║ ┌───────▼───────┐ skills: run_e2e_test, exit_loop      ║│
║ │ verifier      │  → runs test, audits video/report,   ║│
║ └───────────────┘    files issues OR exits the loop    ║│
╚════════════════════════════════════════════════════════╝
    ▼
┌──────────┐
│ reporter │ → final verdict, per-item results, artifact paths
└──────────┘
```

Each iteration the verifier attributes every failure to an owner (`locator-agent` for bad selectors, `coder-agent` for wrong actions/order/assertions), and the next pass of the loop fixes exactly those issues. The loop ends when every checklist item passes — or when the verifier concludes the *app* is broken, which it reports as a finding instead of looping forever.

Generated tests run against a small harness (`e2e_agent/harness.py`) that records everything the verifier needs to "watch" the run:

- **video** of the whole browser session (`.webm`)
- **Playwright trace** (`trace.zip`, view with `playwright show-trace`)
- per-step pass/fail with timing, error, and a **screenshot at the moment of failure**
- browser console messages and page errors

Artifacts land in `workspace/runs/run_NN/`.

## Setup

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python google-adk playwright
.venv/bin/playwright install chromium

cp .env.example .env   # then put your GOOGLE_API_KEY in .env
```

Get an API key from [Google AI Studio](https://aistudio.google.com/apikey) (or set `GOOGLE_GENAI_USE_VERTEXAI=TRUE` with Vertex credentials instead).

## Run

```bash
source .venv/bin/activate
adk web            # browser UI at http://localhost:8000 — pick "e2e_agent"
# or
adk run e2e_agent  # terminal chat
```

Example prompt (uses the bundled demo shop — replace the path with your checkout):

> Test the store at file:///Users/you/Dev/e2e-agent/demo_app/index.html.
> Checklist:
> 1. Searching for "backpack" shows only the Laptop Backpack product.
> 2. Clearing the search shows all 4 products again.
> 3. Adding the Laptop Backpack to the cart makes the cart count show 1.
> 4. Clicking Checkout opens the checkout form.
> 5. Submitting the form with name "Jane Doe" and email "jane@example.com" shows the "Order placed" confirmation.

Include the URL and, ideally, your own checklist — the planner preserves your wording and makes each item verifiable. Without a checklist, the planner derives one from your description.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `E2E_AGENT_MODEL` | `gemini-2.5-flash` | Model for planner / locator / verifier / reporter |
| `E2E_CODER_MODEL` | `E2E_AGENT_MODEL` | Model for the test writer (try `gemini-2.5-pro`) |
| `E2E_MAX_ITERATIONS` | `4` | Max locate → code → verify loops |
| `E2E_HEADLESS` | `1` | Set `0` to watch the browser live |
| `E2E_ACTION_TIMEOUT_MS` | `10000` | Per-action Playwright timeout |
| `E2E_TEST_TIMEOUT_SECONDS` | `240` | Whole-test subprocess timeout |

## Layout

```
e2e_agent/
  agent.py        # the four agents + loop wiring (root_agent lives here)
  prompts.py      # each agent's instructions
  harness.py      # E2ETest: video/trace/report recorder generated tests run inside
  config.py       # env-driven settings
  tools/
    locators.py   # inspect_page, probe_locator        (locator_scout skills)
    coding.py     # save_test_code, get_current_test_code  (test_writer skills)
    runner.py     # run_e2e_test                       (verifier skill)
demo_app/         # offline demo store to try the pipeline on
workspace/        # generated test + per-run artifacts (gitignored)
```

## Extending the skills

- **Auth / multi-page flows**: add a `pre_actions` parameter to `inspect_page` (log in, click through) so mid-flow elements can be probed too.
- **Visual judgment**: the verifier currently audits the structured report; Gemini is multimodal, so failure screenshots from `workspace/runs/run_NN/` can be attached as ADK artifacts for it to look at directly.
- **CI**: run `adk run` non-interactively and gate on the reporter's verdict; commit `workspace/test_generated.py` once it passes as a durable regression test.
