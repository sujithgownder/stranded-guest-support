---

description: "Task list for Stranded Guest Support Ticket Handling Rules"
---

# Tasks: Stranded Guest Support Ticket Handling Rules

**Input**: Design documents from `/specs/001-ticket-handling-rules/`  
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [agent-tools-contract.md](contracts/agent-tools-contract.md), [quickstart.md](quickstart.md)

**Tests**: Included per [plan.md](plan.md) and [quickstart.md](quickstart.md) using Python's built-in `unittest` framework (`tests/unit/`, `tests/contract/`, `tests/integration/`).

**Organization**: Tasks are grouped by user story (`US1`, `US2`, `US3`) to enable independent implementation and verification of each priority slice.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label (`[US1]`, `[US2]`, `[US3]`) for story-phase tasks only
- Include exact repository-relative file paths in every task description

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize package directory structure, test layout, and packaging metadata

- [X] T001 Create package test directories `tests/unit/`, `tests/contract/`, and `tests/integration/` with `__init__.py` markers in `tests/__init__.py`
- [X] T002 Update `pyproject.toml` to configure `[project.scripts]` entry point `stranded-guest = "stranded_guest_support.cli:main"` and verify Python `>=3.11` metadata in `pyproject.toml`
- [X] T003 [P] Export public package symbols placeholder structure in `src/stranded_guest_support/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core domain models, CSV loaders, and policy exception/gateway foundation required before all user stories

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete

- [X] T004 Implement core enumerations (`TicketType`, `SafetyCondition`, `AgentRole`, `ListingStatus`), domain error types (`PolicyViolationError`, `UnauthorizedToolError`, `SafetyHandoffRequiredError`), and constrained dataclasses (`SupportTicket`, `OpenListing`, `ToolCallRecord`, `IncidentLedger`, `TicketResolution`) in `src/stranded_guest_support/models.py` citing `data-model.md`: `SupportTicket.ticket_id`, `SupportTicket.opened_at`, `SupportTicket.reservation_id`, `SupportTicket.guest_name`, `SupportTicket.guest_language`, `SupportTicket.original_listing_id`, `SupportTicket.original_listing_title`, `SupportTicket.neighborhood`, `SupportTicket.property_type`, `SupportTicket.bedrooms`, `SupportTicket.party_size`, `SupportTicket.check_in_date`, `SupportTicket.check_out_date`, `SupportTicket.nightly_price`, `SupportTicket.total_paid`, `SupportTicket.host_id`, `SupportTicket.host_cancelled_at`, `SupportTicket.host_last_reply_at`, `SupportTicket.guest_requested`, `SupportTicket.guest_message`, `SupportTicket.expected_outcome`, `OpenListing.listing_id`, `OpenListing.neighborhood`, `OpenListing.property_type`, `OpenListing.bedrooms`, `OpenListing.max_guests`, `OpenListing.available_from`, `OpenListing.available_to`, `OpenListing.nightly_price`, `OpenListing.status`, `ToolCallRecord.ticket_id`, `ToolCallRecord.reservation_id`, `ToolCallRecord.agent_role`, `ToolCallRecord.tool_name`, `ToolCallRecord.allowed`, `ToolCallRecord.listing_id`, `ToolCallRecord.refund_amount`, `ToolCallRecord.safety_conditions`, `ToolCallRecord.rejection_reason`, `IncidentLedger.remedies_by_reservation`, `IncidentLedger.total_uplift_budget`, `IncidentLedger.uplift_spent`, `IncidentLedger.safety_handoffs_completed`
- [X] T005 [P] Implement CSV loaders (`load_tickets_csv`, `load_open_listings_csv`) with `Decimal` monetary parsing and ISO-8601 date/datetime parsing in `src/stranded_guest_support/loaders.py` citing `data-model.md`: `SupportTicket.nightly_price`, `SupportTicket.total_paid`, `SupportTicket.check_in_date`, `SupportTicket.check_out_date`, `SupportTicket.opened_at`, `SupportTicket.host_cancelled_at`, `SupportTicket.host_last_reply_at`, `OpenListing.available_from`, `OpenListing.available_to`, `OpenListing.nightly_price`, `OpenListing.status`
- [X] T006 Implement `PolicyToolGateway` skeleton with role-isolation dispatch, `IncidentLedger` state tracking, and `ToolCallRecord` audit logging in `src/stranded_guest_support/tools.py` citing `data-model.md`: `ToolCallRecord.agent_role`, `ToolCallRecord.tool_name`, `ToolCallRecord.allowed`, `ToolCallRecord.rejection_reason`, `IncidentLedger.remedies_by_reservation`, `IncidentLedger.safety_handoffs_completed`

**Checkpoint**: Foundation ready — user story implementation can now begin in priority order (`US1` → `US2` → `US3`) or in parallel

---

## Phase 3: User Story 1 - Safety Triage and Mandatory Hand-Off (Priority: P1) 🎯 MVP

**Goal**: Detect all five AirCover safety conditions in `guest_message`, override any `guest_requested` value (`refund`, `rebooking`, `callback`, `other`), route to `SafetyAgent` (`handoff_to_safety_agent` only), and hard-block `hold_booking` and `issue_refund` on safety tickets prior to hand-off.

**Independent Test**: Run `python -m unittest tests/unit/test_safety.py tests/contract/test_agent_contracts.py` against all safety and non-safety messages (including `LIS-TKT-0007`, `LIS-TKT-0015`, `LIS-TKT-0023`, `LIS-TKT-0034`, `LIS-TKT-0046`, `LIS-TKT-0055`) and verify zero calls to `hold_booking` or `issue_refund` before `handoff_to_safety_agent`.

### Tests for User Story 1

- [X] T007 [P] [US1] Write unit tests for all five `SafetyCondition` triggers and pre-handoff safety lock exceptions in `tests/unit/test_safety.py`
- [X] T008 [P] [US1] Write contract tests verifying `SafetyAgent` may invoke only `handoff_to_safety_agent` and cannot invoke `hold_booking` or `issue_refund` in `tests/contract/test_agent_contracts.py`

### Implementation for User Story 1

- [X] T009 [US1] Implement `detect_safety_conditions` and safety-first `classify_ticket` in `src/stranded_guest_support/safety.py` covering all five AirCover conditions (`injury_or_medical_need`, `threat_or_violence`, `nowhere_safe_to_wait`, `unaccompanied_minor`, `stated_fear_of_person`) across supported languages with angry/hyperbole exclusions, citing `data-model.md`: `SupportTicket.guest_message`, `SupportTicket.guest_language`, `SupportTicket.guest_requested`
- [X] T010 [US1] Implement `handoff_to_safety_agent` and enforce the pre-handoff `SafetyHandoffRequiredError` lock blocking `hold_booking` and `issue_refund` on un-handed-off safety tickets in `src/stranded_guest_support/tools.py` citing `data-model.md`: `ToolCallRecord.safety_conditions`, `ToolCallRecord.tool_name`, `IncidentLedger.safety_handoffs_completed`, `IncidentLedger.remedies_by_reservation`
- [X] T011 [US1] Implement `SafetyAgent` and initial safety-first routing in `SupportTeamOrchestrator` in `src/stranded_guest_support/agents.py` citing `data-model.md`: `ToolCallRecord.agent_role`, `SupportTicket.ticket_id`, `SupportTicket.guest_message`

**Checkpoint**: User Story 1 (`safety` triage + `SafetyAgent` + pre-handoff lock) is independently functional and testable as the MVP

---

## Phase 4: User Story 2 - Comparable Home Rebooking Within Policy Limits (Priority: P2)

**Goal**: Keep non-safety `rebooking`, `callback`, `other`, and angry-word tickets with `RebookingAgent`, verify locked-out qualifying conditions, evaluate all five comparable-home tests (including the exact `1.20 * original nightly_price` ceiling), rank by Lisbon neighborhood preference, and place holds via `hold_booking` while tracking the EUR 9,000 uplift budget.

**Independent Test**: Run `python -m unittest tests/unit/test_eligibility.py tests/unit/test_tools.py` to verify angry/callback tickets stay with `RebookingAgent`, `EUR 132.00` passes and `EUR 132.01` fails for `EUR 110.00` original rate, and `hold_booking` transitions listing `status` from `available` to `on_hold`.

### Tests for User Story 2

- [X] T012 [P] [US2] Write unit tests for qualifying check-in failure conditions, all five comparable-home boundary checks (exact 120% cap, dates, `max_guests`, `bedrooms=0` studios, `status`), and neighborhood preference ranking in `tests/unit/test_eligibility.py`
- [X] T013 [P] [US2] Write unit tests for `hold_booking` role isolation, 120% ceiling rejection, uplift budget accounting, and one-remedy-per-stay lock in `tests/unit/test_tools.py`

### Implementation for User Story 2

- [X] T014 [US2] Implement `qualifies_for_rebooking`, `is_comparable_home`, `calculate_uplift`, and Lisbon neighborhood proximity preference ranking in `src/stranded_guest_support/eligibility.py` citing `data-model.md`: `SupportTicket.check_in_date`, `SupportTicket.check_out_date`, `SupportTicket.party_size`, `SupportTicket.bedrooms`, `SupportTicket.nightly_price`, `SupportTicket.neighborhood`, `SupportTicket.host_cancelled_at`, `SupportTicket.host_last_reply_at`, `SupportTicket.guest_message`, `OpenListing.listing_id`, `OpenListing.available_from`, `OpenListing.available_to`, `OpenListing.max_guests`, `OpenListing.bedrooms`, `OpenListing.status`, `OpenListing.nightly_price`, `OpenListing.neighborhood`
- [X] T015 [US2] Implement `hold_booking` in `PolicyToolGateway` enforcing `AgentRole.REBOOKING_AGENT`, open listing ID range (`LST-100001`–`LST-100450`), all five comparability tests, listing `status` transition (`available` -> `on_hold`), uplift tracking, and stay-level remedy locking in `src/stranded_guest_support/tools.py` citing `data-model.md`: `ToolCallRecord.listing_id`, `OpenListing.status`, `IncidentLedger.total_uplift_budget`, `IncidentLedger.uplift_spent`, `IncidentLedger.remedies_by_reservation`
- [X] T016 [US2] Implement `RebookingAgent` (including comparable listing selection and offer-declined / zero-match refund fallback signaling) and update `SupportTeamOrchestrator` routing for `rebooking`, `callback`, `other`, and angry non-safety messages in `src/stranded_guest_support/agents.py` citing `data-model.md`: `SupportTicket.guest_requested`, `ToolCallRecord.agent_role`

**Checkpoint**: User Stories 1 and 2 are both independently functional and testable

---

## Phase 5: User Story 3 - Policy-Capped Refund Processing (Priority: P3)

**Goal**: Route non-safety `refund` tickets (plus declined-offer or zero-comparable-listing rebooking fallbacks) to `RefundAgent`, and enforce `[EUR 0.01, total_paid]` bounds and one-remedy-per-stay closure via `issue_refund`.

**Independent Test**: Run `python -m unittest tests/unit/test_tools.py tests/contract/test_agent_contracts.py` verifying promo-discounted bookings (e.g., `LIS-TKT-0028`, `total_paid = 432.00`) cannot be refunded above `total_paid`, zero/negative refunds fail, and rebooked stays cannot also receive a refund.

### Tests for User Story 3

- [X] T017 [P] [US3] Extend `tests/unit/test_tools.py` with `issue_refund` boundary tests (`EUR 0.00` rejection, `total_paid` exact pass, `total_paid + 0.01` rejection, promo-code cap, and rebooking+refund double-remedy rejection)
- [X] T018 [P] [US3] Extend `tests/contract/test_agent_contracts.py` with `RefundAgent` role isolation and zero-comparable-home / declined-rebooking fallback tests

### Implementation for User Story 3

- [X] T019 [US3] Implement `issue_refund` in `PolicyToolGateway` enforcing `AgentRole.REFUND_AGENT`, `[EUR 0.01, SupportTicket.total_paid]` cap, and one-remedy-per-stay lock in `src/stranded_guest_support/tools.py` citing `data-model.md`: `SupportTicket.total_paid`, `SupportTicket.reservation_id`, `ToolCallRecord.refund_amount`, `IncidentLedger.remedies_by_reservation`
- [X] T020 [US3] Implement `RefundAgent` and wire `refund` routing plus rebooking-to-refund fallback in `SupportTeamOrchestrator` in `src/stranded_guest_support/agents.py` citing `data-model.md`: `SupportTicket.guest_requested`, `SupportTicket.total_paid`, `ToolCallRecord.agent_role`

**Checkpoint**: All three user stories (`safety`, `rebooking`, `refund`) are independently functional and policy-enforced

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: CLI integration, full 60-ticket Lisbon incident verification, root launcher, and documentation alignment

- [X] T021 Implement CLI argument parsing, JSON/table reporting, and exit-code checks in `src/stranded_guest_support/cli.py`, module runner in `src/stranded_guest_support/__main__.py`, and root launcher in `stranded-guest.py`
- [X] T022 Update package exports (`SupportTeamOrchestrator`, `PolicyToolGateway`, `TicketType`, `SafetyCondition`, `AgentRole`, `load_tickets_csv`, `load_open_listings_csv`) in `src/stranded_guest_support/__init__.py`
- [X] T023 Add end-to-end 60-ticket Lisbon CSV integration test (verifying `34 rebooking`, `20 refund`, `6 safety`, 120% ceilings, `total_paid` caps, EUR 9,000 uplift budget, and zero pre-handoff safety violations using synthetic `LST-100001`–`LST-100450` listings) in `tests/integration/test_lisbon_incident.py`
- [X] T024 [P] Update `README.md` Development section with test and CLI execution commands matching `specs/001-ticket-handling-rules/quickstart.md`
- [X] T025 Run full `python -m unittest discover -s tests -v` and `python -m stranded_guest_support --tickets "Lisbon Stranded Guest Tickets (16 Nov 2026).csv" --json` validation per `specs/001-ticket-handling-rules/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — starts immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (`T001`–`T003`) — **BLOCKS** all user stories
- **User Story 1 (Phase 3 - P1)**: Depends on Phase 2 (`T004`–`T006`) — delivers MVP safety triage & hand-off lock
- **User Story 2 (Phase 4 - P2)**: Depends on Phase 2 (`T004`–`T006`) and orchestrator base from `T011` (integrates non-safety routing after safety triage)
- **User Story 3 (Phase 5 - P3)**: Depends on Phase 2 (`T004`–`T006`) and integrates rebooking fallback from `T016`
- **Polish (Phase 6)**: Depends on completion of `US1`, `US2`, and `US3`

### Parallel Opportunities

- **Phase 1**: `T002` and `T003` can run in parallel after `T001`
- **Phase 2**: `T005` (`loaders.py`) can run in parallel once `T004` (`models.py`) defines types
- **Phase 3 (US1)**: `T007` and `T008` test files can be authored in parallel
- **Phase 4 (US2)**: `T012` and `T013` test files can be authored in parallel
- **Phase 5 (US3)**: `T017` and `T018` test extensions can be authored in parallel
- **Phase 6**: `T024` (`README.md`) can run in parallel with `T023` (`tests/integration/test_lisbon_incident.py`)

---

## Parallel Example: User Story 1

```powershell
# Author US1 tests in parallel:
Task: "T007 [P] [US1] Write unit tests for all five SafetyCondition triggers in tests/unit/test_safety.py"
Task: "T008 [P] [US1] Write contract tests verifying SafetyAgent tool restrictions in tests/contract/test_agent_contracts.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup: `T001`–`T003`)
2. Complete Phase 2 (Foundational: `T004`–`T006`)
3. Complete Phase 3 (User Story 1: `T007`–`T011`)
4. **STOP and VALIDATE**: Run `python -m unittest tests/unit/test_safety.py tests/contract/test_agent_contracts.py` to confirm all 6 safety tickets hand off exclusively via `handoff_to_safety_agent` with zero pre-handoff `hold_booking`/`issue_refund` calls.

### Incremental Delivery

1. Setup + Foundational → Core types, CSV loaders, and `PolicyToolGateway` ready
2. Add User Story 1 (`US1`) → Safety triage + mandatory live hand-off verified (MVP)
3. Add User Story 2 (`US2`) → Comparable-home rebooking + 120% ceiling + angry/callback retention verified
4. Add User Story 3 (`US3`) → Policy-capped `total_paid` refunds + zero-match fallback + one-remedy-per-stay verified
5. Polish (`Phase 6`) → CLI, package exports, 60-ticket integration suite, and `quickstart.md` validation
