# e2e-agent

A multi-agent E2E testing system built on the [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) and [Playwright](https://playwright.dev/). You describe what to test in plain English; the agents find the right elements on the live page, write a **TypeScript** Playwright test (`@playwright/test`), run it with video + trace recording, diagnose failures, and rewrite the test until it passes and matches your intent.

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
║ └───────┬───────┘  → workspace/test_generated.spec.ts  ║│
║ ┌───────▼───────┐ skills: run_e2e_test, probe_locator, ║│
║ │ verifier      │   exit_loop → runs test, audits      ║│
║ └───────────────┘   report, files issues OR exits loop ║│
╚════════════════════════════════════════════════════════╝
    ▼
┌──────────┐
│ reporter │ → final verdict, per-item results, artifact paths
└──────────┘
```

Each iteration the verifier attributes every failure to an owner (`locator-agent` for bad selectors, `coder-agent` for wrong actions/order/assertions), and the next pass of the loop fixes exactly those issues. The loop ends when every checklist item passes — or when the verifier concludes the *app* is broken, which it reports as a finding instead of looping forever.

Generated tests are plain `@playwright/test` specs; `workspace/playwright.config.ts` records everything the verifier needs to "watch" the run:

- **video** of the whole browser session (`.webm`)
- **Playwright trace** (`trace.zip`, view with `npx playwright show-trace`)
- per-step pass/fail (one `test.step` per checklist item) with timing and error
- a **screenshot at the moment of failure**

Artifacts land in `workspace/runs/run_NN/`. (`e2e_agent/harness.py` is the legacy recorder from when the pipeline generated Python tests; it's kept so older generated tests still run.)

## Setup

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python google-adk playwright
.venv/bin/playwright install chromium   # browser for the locator scout

(cd workspace && npm install)           # @playwright/test for generated tests

cp .env.example .env   # then put your GOOGLE_API_KEY in .env
```

Get an API key from [Google AI Studio](https://aistudio.google.com/apikey) (or set `GOOGLE_GENAI_USE_VERTEXAI=TRUE` with Vertex credentials instead).

### Using OpenRouter instead

Model ids with a provider prefix are routed through LiteLLM, so an [OpenRouter](https://openrouter.ai/) key works for any or all agents — no Google key needed if every agent uses one:

```bash
# in .env
OPENROUTER_API_KEY=sk-or-v1-...
E2E_AGENT_MODEL=openrouter/google/gemini-2.5-flash
E2E_CODER_MODEL=openrouter/anthropic/claude-sonnet-4.5
```

Any `openrouter/<vendor>/<model>` id from the OpenRouter catalog works, with two requirements: the loop agents need **tool/function calling** and the planner needs **structured output** support (all mainstream Gemini / Claude / GPT models on OpenRouter have both; check the model page for smaller ones). You can also mix — e.g. native `gemini-2.5-flash` as `E2E_AGENT_MODEL` with an OpenRouter model just for the coder.

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
  harness.py      # legacy Python recorder (pre-TypeScript generated tests)
  config.py       # env-driven settings
  tools/
    locators.py   # inspect_page, probe_locator     (locator_scout + verifier)
    coding.py     # save_test_code, get_current_test_code  (test_writer skills)
    runner.py     # run_e2e_test — npx playwright test  (verifier skill)
demo_app/         # offline demo store to try the pipeline on
workspace/
  package.json          # @playwright/test for the generated specs
  playwright.config.ts  # video/trace/report recording per run
  test_generated.spec.ts + runs/   # pipeline output (gitignored)
```

## Extending the skills

- **Auth / multi-page flows**: add a `pre_actions` parameter to `inspect_page` (log in, click through) so mid-flow elements can be probed too.
- **Visual judgment**: the verifier currently audits the structured report; Gemini is multimodal, so failure screenshots from `workspace/runs/run_NN/` can be attached as ADK artifacts for it to look at directly.
- **CI**: run `adk run` non-interactively and gate on the reporter's verdict; commit `workspace/test_generated.spec.ts` once it passes as a durable regression test.
