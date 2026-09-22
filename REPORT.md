# REPORT

## Architecture

I split the system into two very different phases: discovery and replay.

Discovery is the flexible part. It takes a natural-language goal, observes the live UI, asks the model for one structured action, checks that the requested target is actually present, executes that action, and observes again. The loop continues until an independently configured success checkpoint is reached. In the demo, the model discovered the full member search → open sub-account → choose account type → review flow in five UI actions.

Replay is intentionally much simpler. Once a capability has been discovered and recorded, replay does not use an LLM at all. It loads the saved artifact, validates the inputs, resolves placeholders such as `${member_id}`, executes the recorded steps in order, applies policy checks, verifies checkpoints, and returns a typed result. The main idea is that the model is used only where the UI is unknown; repeated runs should be predictable, cheap, and easy to debug.

The browser layer is behind a `Surface` abstraction. The higher-level discovery and replay code only depends on operations such as `open`, `observe`, `click`, `type`, `select`, `read`, `is_visible`, `wait`, and `screenshot`. Playwright is the current implementation, but the rest of the system does not depend directly on Playwright internals. This leaves room for another implementation later, such as a desktop accessibility-tree surface.

I used a small local credit-union admin app as the target application. That keeps the demo stable while still giving the system a realistic UI with forms, links, navigation, a normal business outcome, and a risky final action.

One performance choice falls out naturally from this architecture: LLM latency and cost only happen during discovery. Replay does not make model calls. Discovery currently re-observes the page and makes one model call per action. That is slower than asking for a full plan once, but it is safer and more robust because each decision is based on the actual current UI state.

The successful discovery, replay, business-outcome, escalation, handoff, and recovery runs are preserved under `/evidence/`

## Artifact schema

The reusable artifact is a typed and versioned capability, not a saved model transcript.

The schema is defined with Pydantic and includes the capability name, artifact/schema version, target application, entry URL, typed inputs, typed outputs, ordered steps, targets, actions, checkpoints, a final success condition, and known business outcomes.

The business contract is developer-controlled. For example, `member_id`, `account_type`, the expected `review_status`, the success checkpoint, and `MEMBER_NOT_FOUND` are declared outside the model. The LLM only discovers how to carry out that known capability on the current UI. I chose this on purpose because input/output meaning and business semantics should not be invented by the model.

After a successful discovery run, the recorder converts the model decisions into replayable `Step` objects. It also parameterizes concrete discovery values. For example, the run may discover the workflow using member `12345` and the UI label `Savings`, but the saved artifact contains `${member_id}` and `${account_type}`. That artifact can then be replayed with a different member and a different account type.

Targets are kept semantic where possible. The recorder prefers things such as role + accessible name, label, or visible text rather than coordinates. It also removes redundant locator fields when one clean semantic locator is enough. This makes the artifact easier to review and less sensitive to layout changes.

## Determinism & error handling

Replay has no LLM in the decision loop. Given an artifact and a set of inputs, it follows the saved steps in order and checks the expected state after execution.

The engine separates different classes of outcomes instead of treating everything as a generic exception.

A normal business result such as `MEMBER_NOT_FOUND` returns `business_outcome`. Invalid invocation data, such as an unsupported `account_type`, is rejected before normal UI execution. A missing control or failed browser action becomes a hard failure with a specific code such as `STEP_EXECUTION_FAILED`. A failed success checkpoint becomes a checkpoint failure instead of being silently ignored.

For transient UI timing issues, replay has a small bounded recovery mechanism. If a checkpoint is not ready, the engine can wait briefly and retry it. The log records both `recoverable_condition` and `recoverable_condition_recovered`. I deliberately limited recovery to checks like checkpoint readiness instead of blindly retrying arbitrary side-effecting actions.

Structured JSONL logs capture run start/end, step start/end, business outcomes, policy decisions, recoverable conditions, handoffs, and hard failures. Screenshots are captured for important failure or escalation points. This makes the execution trace easier to inspect than a stack trace alone.

The main performance improvement here is avoiding repeated model inference. After discovery, replay is mostly browser I/O plus small local operations such as parameter substitution, validation, policy evaluation, and logging. Those local operations are negligible compared with browser navigation.

## Heterogeneity & multi-tenant

I did not try to build multiple full application integrations in the time available. Instead, the design keeps application-specific behavior in artifacts and the UI-specific mechanics behind `Surface`.

A browser application currently uses `PlaywrightSurface`. A future desktop implementation could expose the same operations using accessibility APIs while keeping discovery, replay, artifact validation, safety policy, and error handling mostly unchanged.

The artifact also keeps the workflow separate from the replay engine. A different application can have a different entry URL, targets, inputs, outputs, checkpoints, and policy configuration without requiring a new execution engine.

For a real multi-tenant deployment, I would isolate artifacts, credentials, policy allowlists, evidence, and browser sessions per tenant. Tenant identity would be part of the execution context, and artifacts would be stored and versioned per tenant/application. I did not add a database, queue, Kubernetes layer, or tenant service here because those would add infrastructure without improving the core computer-use behavior being demonstrated.

## Escalation & handoff

Risky actions are handled outside the normal replay path.

The handoff demo adds a simulated irreversible `Create Account` step after the normal review screen. When replay reaches that step, the execution policy classifies it as risky and stops before Playwright clicks it.

Without a handoff handler, the run returns `HUMAN_REQUIRED`. In headed mode, the same browser session stays open and control is handed to the user. The user completes the risky action manually, returns to the terminal, and replay resumes in the same session.

The system records the handoff start, the intended risky action, the handoff completion, and resume events. It also saves before/after screenshots. After the user returns control, replay does not simply trust that the action was completed; it verifies the configured final checkpoint (`CHECKPOINT: ACCOUNT_CREATED`) before returning success.

The current implementation does not record raw human mouse/keyboard events. The human confirms completion, and the automation verifies the resulting application state. For a production operator workflow, I would add richer event capture and a remote handoff UI, but the current version is enough to demonstrate safe same-session takeover and resume. Successful handoff is backed by the replay JSONL in `/evidence/replay` plus before/after screenshots and final checkpoint verification.

## Safety

Safety is enforced independently of both the model and the artifact.

The `ExecutionPolicy` has an explicit origin allowlist, action checks, and risky-target detection. Replay blocks navigation outside the allowed origin. Risky clicks such as `Create Account` are escalated instead of executed automatically.

Discovery is also constrained. The model is given a bounded observation containing visible text and interactive elements. It is expected to choose from controls that were actually observed, and the runner checks the selected target against the current observation before executing it. Model-driven arbitrary navigation is blocked during discovery.

Sensitive values are handled conservatively. The member ID is marked sensitive in the capability contract, and persisted discovery evidence replaces invocation values with placeholders such as `${member_id}` instead of keeping the raw value. The OpenAI API key is not stored in source control; `.env.example` contains placeholders only.

The normal reusable capability intentionally stops at the review screen. The risky final action only exists in a separate handoff-demo artifact so that irreversible behavior is never part of the normal automation path.

## Cuts

I kept the implementation focused on the core system instead of adding infrastructure that would not change the main result.

I did not build desktop automation, a remote operator dashboard, a production multi-tenant service, a persistent artifact database, distributed workers, or a second target application. The `Surface` and artifact boundaries are there so those could be added later.

I also did not make the LLM infer the entire business contract. Inputs, outputs, success criteria, and known business outcomes stay developer-defined. The model discovers UI procedure, not business meaning.

Locator recovery is intentionally simple. The artifact usually stores one strong semantic target rather than a long self-healing fallback chain. A production version could keep ordered fallback locators and try alternatives before failing.

Discovery currently sends bounded visible text plus interactive element metadata on each model call. For larger pages, I would reduce repeated tokens by sending observation deltas, compressing static page chrome, or using compact element IDs. I would not add that optimization here because the demo pages are small and the current behavior is easier to inspect.

The human handoff is console-driven and records the handoff boundary plus screenshots rather than a full stream of operator events. A production version could capture actual human input events and attach them to the trace.

Overall, the main tradeoff was to put intelligence in discovery and keep replay simple. That gives the system a flexible way to learn an unfamiliar UI once, while keeping repeated execution deterministic, cheaper, easier to audit, and safer.
