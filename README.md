# Computer-Use Automation System

A small end-to-end system for discovering UI workflows with an LLM, recording successful workflows as typed reusable artifacts, and replaying those artifacts deterministically without an LLM in the execution loop.

The demo target is a local legacy-style credit-union admin application. The main workflow is:

`Member Search -> Member Details -> Open Sub-account -> Choose Account Type -> Review`

The normal capability stops at the review screen. A separate handoff-demo artifact adds a simulated irreversible `Create Account` action so the safety and human-takeover path can be demonstrated without putting that risky action into the normal automation flow.

## What this demonstrates

The project includes:

- a genuine LLM-driven `observe -> decide -> act` discovery loop against a live UI
- structured page observations and grounded model decisions
- a typed, versioned Pydantic capability artifact
- automatic parameterization of discovered values such as `${member_id}` and `${account_type}`
- deterministic replay with no LLM in the execution loop
- semantic target resolution using roles, accessible names, labels, and visible text
- known business-outcome handling such as `MEMBER_NOT_FOUND`
- bounded recovery for transient checkpoint conditions
- structured JSONL logs and screenshots
- an explicit execution allowlist and risky-action policy
- same-session human handoff and resume for risky actions
- curated evidence for discovery, replay, escalation, handoff, and recovery

For the design discussion and tradeoffs, see [`REPORT.md`](REPORT.md).

---

## Repository layout

```text
.
├── artifacts/
│   ├── open_sub_account_discovered_v1.json
│   └── open_sub_account_handoff_demo_v1.json
├── demo_app/
│   ├── app.py
│   ├── templates/
│   └── static/
├── evidence/
│   ├── discovery/
│   ├── replay/
│   ├── handoff/
│   └── recovery/
├── scripts/
│   ├── inspect_page.py
│   ├── run_discovery.py
│   ├── run_replay.py
│   ├── generate_example_artifact.py
│   └── generate_handoff_demo_artifact.py
├── src/
│   ├── agent/
│   ├── artifact/
│   ├── handoff/
│   ├── replay/
│   ├── safety/
│   └── surface/
├── tests/
├── .env.example
├── .gitignore
├── pytest.ini
├── README.md
├── REPORT.md
└── requirements.txt
```

---

## Requirements

Recommended environment:

- Python 3.11
- Chromium installed through Playwright
- an OpenAI API key for the discovery run only

Replay does **not** require an OpenAI API key.

---

## Setup

Clone the repository:

```bash
git clone <REPO_URL>
```

Create and activate a Python 3.11 environment. For Conda:

```bash
conda create -n interface-ai python=3.11 -y
conda activate interface-ai
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the tests:

```bash
pytest -q
```

---

## OpenAI API configuration

The LLM is only used during discovery.

Copy the example environment file and set a `.env`:

```env

OPENAI_API_KEY=replace_me

OPENAI_MODEL=gpt-5.6-luna

```

Never commit the real `.env` file.

The scripts read environment variables from the process environment.

Load the values from `.env` into the current shell before running discovery:

```bash
set -a
source .env
set +a
```

---

# Run the demo

The easiest way to review the project is to use two terminals.

## Terminal 1: start the target application

From the repository root:

```bash
cd demo_app
uvicorn app:app --reload
```

Demo member IDs:

```text
12345
56789
```

Known business-outcome member:

```text
99999
```

Keep this terminal running while using discovery or replay.

---

## Terminal 2: inspect the live UI

From the repository root:

```bash
conda activate interface-ai
python scripts/inspect_page.py --headed
```

This prints the page URL, title, visible text, and the interactive elements exposed to the discovery agent.

The observation layer intentionally provides a bounded representation of the page rather than raw full HTML.

---

# 1. Genuine LLM-driven discovery

Make sure the target app is running and your OpenAI environment variables are loaded.

Run:

```bash
python scripts/run_discovery.py \
  --goal "Open a savings sub-account for member 12345 and reach the review screen." \
  --input member_id=12345 \
  --input account_type=savings \
  --headed
```

The model operates one step at a time:

```text
observe current UI
        ↓
model returns structured AgentDecision
        ↓
runner validates target against current observation
        ↓
execute action through Playwright
        ↓
observe again
        ↓
repeat until success checkpoint
```

A successful discovery should execute five UI actions:

```text
1. Type member ID
2. Click Search Member
3. Click Open New Sub-account
4. Click Savings
5. Click Continue
```

The runner independently checks:

```text
CHECKPOINT: REVIEW_READY
```


Discovery evidence is written under:

```text
evidence/discovery/
```
The persisted evidence replaces invocation values with parameter placeholders where appropriate instead of storing the raw invocation value.

---

# 2. Inspect the generated capability artifact

After successful discovery: The artifact is generated from the successful model decisions but is separate from the raw model trace.

For example, a discovered concrete value:

```json
"value": "12345"
```

becomes:

```json
"value": "${member_id}"
```

and a discovered account-type target such as:

```json
"name": "Savings"
```

becomes:

```json
"name": "${account_type}"
```

The business contract remains developer-declared: typed inputs, outputs, success checkpoint, and known business outcomes are not invented by the model.

---

# 3. Deterministic replay with different inputs

This run uses the artifact produced by discovery, but does **not** use an LLM.

```bash
python scripts/run_replay.py \
  --artifact artifacts/open_sub_account_discovered_v1.json \
  --input member_id=56789 \
  --input account_type=checking \
  --headed
```

This demonstrates that a workflow discovered using:

```text
member_id=12345
account_type=savings
```

can be reused with:

```text
member_id=56789
account_type=checking
```

without putting a model back into the execution loop.

Replay JSONL evidence is written under:

```text
evidence/replay/
```

---

# 4. Known business outcome

Run the same capability using the demo member that produces a normal business rejection:

```bash
python scripts/run_replay.py \
  --artifact artifacts/open_sub_account_discovered_v1.json \
  --input member_id=99999 \
  --input account_type=savings \
  --headed
```

`MEMBER_NOT_FOUND` is deliberately treated differently from a technical automation failure.

---

# 5. Invalid input handling

For example:

```bash
python scripts/run_replay.py \
  --artifact artifacts/open_sub_account_discovered_v1.json \
  --input member_id=56789 \
  --input account_type=investment
```

The invalid enum is rejected before normal UI execution.

---

# 6. Safety policy and risky-action escalation

The normal discovered artifact stops at the review page and does not contain the simulated irreversible final action.

Generate a separate handoff-demo artifact:

```bash
python scripts/generate_handoff_demo_artifact.py
```

This creates:

```text
artifacts/open_sub_account_handoff_demo_v1.json
```

The demo artifact adds one extra step:

```text
click "Create Account"
```

and changes the final success checkpoint to:

```text
CHECKPOINT: ACCOUNT_CREATED
```

The execution policy classifies this click as risky.

## Headless escalation test

Run without `--headed`:

```bash
python scripts/run_replay.py \
  --artifact artifacts/open_sub_account_handoff_demo_v1.json \
  --input member_id=56789 \
  --input account_type=checking
```

The risky action is intercepted before Playwright executes it.

The default replay allowlist only permits:

```text
http://127.0.0.1:8000
```

The artifact itself cannot expand the allowlist.

---

# 7. Same-session human handoff

Run the handoff artifact with a visible browser:

```bash
python scripts/run_replay.py \
  --artifact artifacts/open_sub_account_handoff_demo_v1.json \
  --input member_id=56789 \
  --input account_type=checking \
  --headed
```

Replay performs the normal deterministic steps and pauses before the risky action.

The terminal will show:

```text
=== HUMAN HANDOFF REQUIRED ===

Click target matches risky operation 'create account'. Human control is required.
Paused at step: step_human_final_approval
Intended action: click button:Create Account
```

When replay pauses:

1. Leave the terminal waiting.
2. Switch to the already-open browser.
3. Click `Create Account` manually.
4. Wait until the browser shows:

```text
Sub-account Created
CHECKPOINT: ACCOUNT_CREATED
```
Replay then verifies the final checkpoint.

The same browser session is used before, during, and after handoff.

Handoff evidence is written under:

```text
evidence/handoff/
```

including structured events and before/after screenshots.

---

# 8. Recoverable-condition handling

Replay uses bounded retry for transient checkpoint-readiness failures. It does not blindly retry arbitrary side-effecting actions.

Run the focused test:

```bash
pytest \
  tests/test_replay_safety.py::test_checkpoint_condition_is_retried_and_recovers \
  -q
```
The curated example is stored at:

```text
evidence/recovery/recoverable_checkpoint.jsonl
```

---

# Evidence

The repository contains a small curated evidence set rather than every development run.

## Discovery

```text
evidence/discovery/
  discovery_success.jsonl
  discovery_success_final.png
```

`discovery_success.jsonl` contains the live observations and structured model decisions from a genuine LLM-driven run.

`discovery_success_final.png` shows the final UI state reached by that run.

## Deterministic replay

```text
evidence/replay/
  replay_success.jsonl
  replay_business_outcome.jsonl
  replay_policy_escalation.jsonl
  replay_policy_escalation.png
  replay_handoff_success.jsonl
```

These demonstrate:

- normal deterministic replay success
- `MEMBER_NOT_FOUND` as a business outcome
- risky-action policy escalation
- the UI state at escalation
- successful replay continuation after human handoff

## Human handoff

```text
evidence/handoff/
  handoff_success.jsonl
  handoff_before.png
  handoff_after.png
```

These show the handoff boundary and browser state before and after human intervention.

The handoff logger records the intended action and control transfer; successful completion is independently verified afterward by the replay engine using the configured final checkpoint.

## Recovery

```text
evidence/recovery/
  recoverable_checkpoint.jsonl
```

This demonstrates a checkpoint that is initially unavailable, retried in a bounded way, and then successfully recovered.

---

# Tests

Run the full test suite:

```bash
pytest -q
```

The tests cover:

- artifact model validation
- parameterized artifact recording
- agent decision validation
- discovery target grounding
- deterministic replay
- parameter resolution
- known business outcomes
- safety-policy allow/block/escalate behavior
- same-session handoff behavior
- recoverable checkpoint retry

---

# Safety notes

The normal capability stops at:

```text
CHECKPOINT: REVIEW_READY
```

It does **not** automatically create an account.

`Create Account` exists only in the separate handoff demo so the policy boundary can be tested.

Safety is enforced outside both the LLM and the artifact:

```text
proposed action
      ↓
ExecutionPolicy
  ↙      ↓       ↘
allow  escalate  block
```

The current policy includes:

- explicit origin allowlisting
- action checks
- risky target detection
- no arbitrary model-driven navigation during discovery
- target grounding against the current observation
- human escalation for risky actions


Discovery evidence parameterizes invocation values so the raw sensitive member ID is not persisted in the saved trace.

---
