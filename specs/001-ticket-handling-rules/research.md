# Phase 0 Research: Stranded Guest Support Ticket Handling Rules

**Feature**: [spec.md](spec.md)  
**Date**: 2026-11-27

## Research Decisions

### 1. Language, Runtime, and Dependency Footprint

- **Decision**: Use Python 3 (verified `3.15.2` in the workspace) with only the Python standard library (`csv`, `dataclasses`, `datetime`, `decimal`, `enum`, `json`, `pathlib`, `re`, `argparse`, `unittest`) for core runtime and tests.
- **Rationale**: `pyproject.toml` currently declares no third-party dependencies and the local environment has only `pip` installed. Using the standard library guarantees deterministic, offline-capable execution immediately after `python -m pip install -e .` with zero network installs or version drift.
- **Alternatives considered**:
  - Adding `pydantic` + `pytest`: Improves schema ergonomics, but adds external install requirements not yet present in `pyproject.toml` or the local Python environment. Can be layered later without changing domain logic.
  - Using an external LLM SDK for triage: Introduces non-determinism, API key requirements, and failure risk on strict safety guardrails; deterministic rule + lexical pattern triage is verifiable against all 60 incident tickets while remaining extensible via a classifier protocol.

### 2. Monetary Precision for 120% Price Ceiling and `total_paid` Refund Cap

- **Decision**: Represent all currency amounts (`nightly_price`, `total_paid`, `uplift`, `refund_amount`) using `decimal.Decimal` quantized to 2 decimal places (`EUR 0.01`, `ROUND_HALF_UP` / exact comparison on `1.20 * original_nightly_price`).
- **Rationale**: Binary floating-point arithmetic can misclassify exact boundary checks such as `1.20 * 110.00 = 132.00` vs `132.01`, or `1.20 * 145.50 = 174.60`. Exact `Decimal` math guarantees zero boundary errors on the 120% ceiling and on `EUR 0.01 <= refund <= total_paid`.
- **Alternatives considered**:
  - Python `float`: Rejected due to IEEE-754 representation inaccuracy (e.g., `145.5 * 1.2` drift risks).
  - Integer cents (`int`): Equally exact, though `Decimal` aligns directly with CSV decimal strings (`92.00`, `145.50`) and keeps financial formulas readable.

### 3. Safety Triage Priority and Distinction from Angry/Callback Messages

- **Decision**: Implement a safety-first triage pipeline where `SafetyCondition` detection on `guest_message` always runs *before* inspecting `guest_requested` or dispatching to `RebookingAgent`/`RefundAgent`. Combine explicit condition pattern rules across the 6 supported languages (`en`, `pt`, `es`, `fr`, `de`, `it`) with negative guards for non-safety frustration idioms (e.g., `"I am dying out here"`, `"before we all lose it"`, `"worst day of our lives"`).
- **Rationale**: Inspection of the 60 tickets in `Lisbon Stranded Guest Tickets (16 Nov 2026).csv` shows 6 `safety` tickets disguised across all four `guest_requested` values (`refund`: 2, `rebooking`: 2, `callback`: 1, `other`: 1), while frustrated/angry `rebooking` tickets (`LIS-TKT-0005`, `LIS-TKT-0022`, `LIS-TKT-0041`) and non-safety `callback` tickets (`LIS-TKT-0017`, `LIS-TKT-0039`, `LIS-TKT-0049`, `LIS-TKT-0059`) must remain `rebooking`.
- **Alternatives considered**:
  - Routing solely on `guest_requested`: Fails on all 6 safety tickets and fails on `callback`/`other` tickets.
  - Pure keyword matching for `"dying"` or `"scared"`: Risks false positives on hyperbole (`"I am dying out here"` in `LIS-TKT-0022` refers to waiting with suitcases, whereas `"phone is on 9%"` + `"16"` in `LIS-TKT-0015` or `"diabetic"` + `"pale and shaky"` in `LIS-TKT-0055` are true safety triggers). Context-aware phrase patterns resolve this cleanly.

### 4. Tool Access Enforcement and Pre-Handoff Safety Lock

- **Decision**: Enforce agent tool permissions and safety ticket locks inside a central `PolicyToolGateway` (not merely in agent prompts/docstrings). Each specialist agent receives only its permitted tool capability (`RebookingAgent` -> `hold_booking`, `RefundAgent` -> `issue_refund`, `SafetyAgent` -> `handoff_to_safety_agent`), and the gateway additionally enforces ticket-state invariants (`safety` tickets reject `hold_booking`/`issue_refund` prior to `handoff_to_safety_agent`; stays reject double remedies).
- **Rationale**: Defense in depth ensures that even if a caller or orchestrator misroutes a ticket or attempts an unauthorized call, policy invariants from `AirCover Rebooking and Refund Rules - Lisbon Check-In Incident.md` cannot be violated.
- **Alternatives considered**:
  - Convention-only tool assignment without gateway checks: Insufficient to guarantee the safety pre-handoff invariant or one-remedy-per-stay invariant under edge-case or adversarial test scenarios.

### 5. Companion Open Listings Data (`airbnb_lisbon_open_listings_2026-11-16.csv`)

- **Decision**: Load open listings via a repository/loader abstraction accepting any CSV path matching the documented schema (`listing_id`, `neighborhood`, `property_type`, `bedrooms`, `max_guests`, `available_from`, `available_to`, `nightly_price`, `status`), and include deterministic fixture generators in tests covering `LST-100001`–`LST-100450`.
- **Rationale**: `AirCover Rebooking and Refund Rules - Lisbon Check-In Incident.md` defines the exact schema and ID range (`LST-100001` to `LST-100450`) for `airbnb_lisbon_open_listings_2026-11-16.csv`, while the workspace currently contains only the 60-ticket CSV. An abstract loader + synthetic test inventory lets the entire workflow be implemented and verified end-to-end immediately and seamlessly consume the real 450-row CSV when provided.
- **Alternatives considered**:
  - Hardcoding mock listings inside production modules: Rejected because production code must remain cleanly decoupled from test fixtures.

### 6. Lisbon Neighborhood Preference Ranking

- **Decision**: Model Lisbon neighborhood proximity as a deterministic adjacency table covering the neighbourhoods present in the 60-ticket dataset (`Alfama`, `Baixa`, `Chiado`, `Graca`, `Bairro Alto`, `Principe Real`, `Estrela`, `Belem`, `Alcantara`, `Parque das Nacoes`, plus mentioned areas `Mouraria`, `Campo de Ourique`, `Santos`, `Lapa`). Use neighborhood match (`exact` > `neighbouring` > `other Lisbon`) solely for tie-breaking among listings that pass all five hard comparable-home tests, followed by lowest nightly price / lowest uplift.
- **Rationale**: Rules explicitly state that same or neighbouring Lisbon `neighborhood` is preferred when choosing between passing homes, and is *not* a pass or fail test.
- **Alternatives considered**:
  - Filtering strictly by exact `neighborhood`: Would cause valid guests (`LIS-TKT-0029`, `LIS-TKT-0060`, or cases where original neighborhood lacks passing homes) to fail rebooking unnecessarily.
