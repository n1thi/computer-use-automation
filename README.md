# Computer-Use Automation System

A small end-to-end system for discovering and replaying UI automation capabilities.

The project demonstrates how an AI agent can eventually discover how to complete a task through a user interface, record the successful workflow as a structured capability, and replay that capability deterministically without an LLM in the execution loop.

## Current Status

The project currently includes:

- A local mock credit-union administration application
- A typed, versioned capability artifact schema using Pydantic
- Parameterized workflow inputs such as `${member_id}` and `${account_type}`
- A Playwright-based browser surface
- Deterministic replay of saved capabilities
- Success checkpoint verification
- Known business-outcome handling such as `MEMBER_NOT_FOUND`
- Failure screenshot capture

LLM-driven discovery, safety policies, human escalation, and richer observability will be added next.

## Project Structure

```text
.
├── artifacts/
│   └── open_sub_account_v1.json
├── demo_app/
│   ├── app.py
│   ├── static/
│   └── templates/
├── scripts/
│   ├── generate_example_artifact.py
│   └── run_replay.py
├── src/
│   ├── artifact/
│   ├── replay/
│   └── surface/
├── tests/
├── pytest.ini
└── requirements.txt