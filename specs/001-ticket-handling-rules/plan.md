# Implementation Plan: Stranded Guest Support Ticket Handling Rules

**Branch**: `001-ticket-handling-rules` | **Date**: 2026-11-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-ticket-handling-rules/spec.md`

## Summary

Implement the policy-enforced ticket triage, specialist agent team (`RebookingAgent`, `RefundAgent`, `SafetyAgent`), and tool execution gateway (`hold_booking`, `issue_refund`, `handoff_to_safety_agent`) in the `stranded_guest_support` Python package. The design prioritizes deterministic safety screening of `guest_message` across all five AirCover safety conditions before any booking or refund action, keeps angry-word and callback-only tickets with the rebooking agent, enforces the 5-test comparable-home gate (including the exact 120% `nightly_price` ceiling) and `total_paid` refund cap using `Decimal` arithmetic, and validates against all 60 tickets in `Lisbon Stranded Guest Tickets (16 Nov 2026).csv`.

## Technical Context

**Language/Version**: Python 3.15 (compatible with Python 3.11+)

**Primary Dependencies**: Python Standard Library only (`csv`, `dataclasses`, `datetime`, `decimal`, `enum`, `json`, `pathlib`, `re`, `argparse`)

**Storage**: Local CSV input files (`Lisbon Stranded Guest Tickets (16 Nov 2026).csv` / `airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv` and runtime `airbnb_lisbon_open_listings_2026-11-16.csv`) and in-memory state ledger per incident batch

**Testing**: `unittest` (Python Standard Library test runner) covering unit, contract, and 60-ticket integration suites

**Target Platform**: Cross-platform CLI and importable Python package (Windows / Linux)

**Project Type**: Python library + CLI package (`src/stranded_guest_support`)

**Performance Goals**: Process 60 tickets against 450 open listings in < 500 ms locally with deterministic repeatable outcomes

**Constraints**: Zero external runtime dependencies; exact `Decimal` monetary math (`EUR 0.01`); hard pre-handoff lock forbidding `issue_refund` or `hold_booking` on safety tickets; one remedy per stay; EUR 9,000 incident uplift budget tracking

**Scale/Scope**: 60 stranded-guest incident tickets (`LIS-TKT-0001`–`LIS-TKT-0060`) evaluated against up to 450 open Lisbon listings (`LST-100001`–`LST-100450`)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Note: `.specify/memory/constitution.md` currently contains the default project template without project-specific ratified overrides. Applying baseline engineering governance principles:

1. **Library-First & Modularity**: Core ticket classification, comparability evaluation, tool gateway, and specialist agents live as importable modules under `src/stranded_guest_support/` decoupled from CLI I/O. **PASS**.
2. **CLI Interface**: Expose a clean CLI entry point (`python -m stranded_guest_support` and optional `stranded-guest.py` wrapper) supporting structured JSON and human-readable output. **PASS**.
3. **Test-First & Contract Verification**: Every functional requirement (`FR-001`–`FR-015`) and tool boundary (`hold_booking`, `issue_refund`, `handoff_to_safety_agent`) maps to explicit unit, contract, and 60-ticket integration tests in `tests/`. **PASS**.
4. **Simplicity / Zero Unnecessary Dependencies**: Standard library only; no speculative web servers, databases, or framework overhead. **PASS**.

*Post-Phase 1 Re-Check*: Data model, agent/tool contracts, and quickstart validation scenarios maintain strict module separation, zero external runtime dependencies, and full traceability to `FR-001`–`FR-015`. **PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/001-ticket-handling-rules/
├── plan.md                                 # This implementation plan
├── research.md                             # Phase 0 design decisions
├── data-model.md                           # Phase 1 domain entities, rules, and state transitions
├── quickstart.md                           # Phase 1 validation and run guide
├── checklists/
│   └── requirements.md                     # Spec quality checklist
├── contracts/
│   └── agent-tools-contract.md             # Specialist agent, tool gateway, and CLI contracts
└── tasks.md                                # Phase 2 output (created by /speckit-tasks)
```

### Source Code (repository root)

```text
src/
└── stranded_guest_support/
    ├── __init__.py                         # Public package exports
    ├── __main__.py                         # Module CLI entrypoint (`python -m stranded_guest_support`)
    ├── models.py                           # Enums, dataclasses, and typed error classes
    ├── loaders.py                          # CSV loaders for tickets and open listings
    ├── safety.py                           # Five AirCover safety condition detector
    ├── eligibility.py                      # Qualifying check, 5 comparable-home tests, neighborhood ranking
    ├── tools.py                            # Policy-guarded tool gateway (`hold_booking`, `issue_refund`, `handoff_to_safety_agent`)
    ├── agents.py                           # Specialist agents (`RebookingAgent`, `RefundAgent`, `SafetyAgent`) & orchestrator
    └── cli.py                              # CLI argument parsing and JSON/summary reporting

tests/
├── unit/
│   ├── test_safety.py                      # Five safety conditions, multi-language cues, angry/callback non-safety guards
│   ├── test_eligibility.py                 # Qualifying conditions & 5 comparable-home boundary checks (120% cap, dates, bedrooms, status)
│   └── test_tools.py                       # Role permissions, pre-handoff safety lock, total_paid cap, one-remedy-per-stay
├── contract/
│   └── test_agent_contracts.py             # Specialist agent tool restrictions & resolution schema conformance
└── integration/
    └── test_lisbon_incident.py             # End-to-end validation across all 60 tickets in Lisbon CSV + synthetic 450 listings

stranded-guest.py                           # Optional root CLI launcher delegating to `stranded_guest_support.cli`
pyproject.toml                              # Package metadata and console script / test config
```

**Structure Decision**: Single Python package layout matching the existing `pyproject.toml` (`package-dir = {"" = "src"}`, `src/stranded_guest_support/`), adding modular domain files for safety triage, comparability evaluation, policy-enforced tool execution, specialist agents, and `tests/` separated into unit, contract, and integration suites.

## Complexity Tracking

No constitution violations or justified exceptions required.
