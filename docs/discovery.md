# Discovery: fictional payment exception assistant

## Problem and people
Working hypothesis: an operations analyst may need to switch between case details, notes and procedures to investigate an exception. This is not a measured claim about a real bank. The primary simulated persona is a payment operations analyst; other simulated stakeholders are an operations manager, a risk reviewer and an engineering owner. No stakeholder interviews have been conducted.

## Workflow
Current simulated process: open an exception, read payment details and notes, find a procedure, identify missing facts, decide a next step, and document and route it. Proposed process: select a case, retrieve relevant fictional procedures, review a cited draft recommendation and uncertainty, and let the analyst decide. The prototype ends at recommendation.

## Assumptions, questions and risks
Assumptions: case details and procedures are available; the analyst can interpret them and verify a recommendation. Questions for real discovery include what triggers exceptions, which information and procedures are consulted, when escalation is required, what data may be exposed, and how usefulness and handling time are measured. Risks include unsupported advice, irrelevant citations, conflicting facts, prompt injection in case notes, and confusing fictional procedures with real policy. Human review and explicit abstention are planned controls, not guarantees.

## Scope and stories
Only fictional data is used. The MVP is read-only: it does not send messages, change cases, release payments, make compliance decisions or connect to banking systems. Analysts should be able to select a case, request an investigation, inspect exact evidence, and see missing information, uncertainty and escalation. The owner should be able to evaluate recommendations and record cost, latency and failures. The present slice supports case selection and inspection only; investigation and evaluation are future work.

MVP acceptance requires at least five cases, structured recommendations grounded in case facts and valid citations, explicit insufficient-evidence responses, no external writes, and repeatable offline tests for boundaries, citations and no-action behavior.
