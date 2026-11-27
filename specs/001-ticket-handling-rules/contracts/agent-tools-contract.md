# Specialist Agent, Tool Gateway & CLI Contracts

**Feature**: [spec.md](../spec.md)  
**Date**: 2026-11-27

## 1. Specialist Agent Team Contract

### Triage & Routing (`TicketTriageService`)
- **Input**: `SupportTicket`
- **Output**: `(TicketType, tuple[SafetyCondition, ...])`
- **Ordering Guarantee**: Safety condition inspection on `ticket.guest_message` MUST execute before evaluating `ticket.guest_requested`.
- **Classification Rules**:
  1. Non-empty `safety_conditions` -> `TicketType.SAFETY` (overrides `refund`, `rebooking`, `callback`, `other`).
  2. Empty `safety_conditions` and `guest_requested == "refund"` -> `TicketType.REFUND`.
  3. Empty `safety_conditions` and `guest_requested in {"rebooking", "callback", "other"}` -> `TicketType.REBOOKING` (includes angry/frustrated messages).

### Specialist Agent Roles

| Agent | Input | Permitted Tool | Prohibited Tools | Output |
|---|---|---|---|---|
| `SafetyAgent` | `SupportTicket`, `safety_conditions` | `handoff_to_safety_agent` | `hold_booking`, `issue_refund` | `TicketResolution(outcome="safety", handoff_completed=True)` |
| `RebookingAgent` | `SupportTicket`, `list[OpenListing]` | `hold_booking` | `issue_refund`, `handoff_to_safety_agent` | `TicketResolution(outcome="rebooking", listing_id=...)` or fallback signal to `RefundAgent` when 0 comparable homes pass or guest declines |
| `RefundAgent` | `SupportTicket`, optional `amount` | `issue_refund` | `hold_booking`, `handoff_to_safety_agent` | `TicketResolution(outcome="refund", refund_amount=...)` |

---

## 2. Policy Tool Gateway Contracts (`PolicyToolGateway`)

All booking, refund, and hand-off calls pass through `PolicyToolGateway`, which enforces role authorization and AirCover policy invariants before mutating ledger/listing state.

### Tool 1: `hold_booking(agent_role, ticket, listing)`
- **Preconditions**:
  1. `agent_role == AgentRole.REBOOKING_AGENT` (else raise `UnauthorizedToolError`).
  2. Ticket has no active safety lock (`ticket_type != TicketType.SAFETY` or handoff completed; else raise `SafetyHandoffRequiredError`).
  3. Stay (`ticket.reservation_id`) has no existing refund or booking hold (one remedy per stay; else raise `PolicyViolationError`).
  4. Guest qualifies under at least one locked-out condition (no working access, host unreachable, or host cancelled within 30 days of `check_in_date`).
  5. `listing` passes all 5 comparable-home tests:
     - `listing.listing_id` is an open listing (`LST-100001`–`LST-100450`)
     - `listing.available_from <= ticket.check_in_date` and `listing.available_to >= ticket.check_out_date`
     - `listing.max_guests >= ticket.party_size`
     - `listing.bedrooms >= ticket.bedrooms`
     - `listing.status == ListingStatus.AVAILABLE`
     - `listing.nightly_price <= ticket.nightly_price * Decimal("1.20")`
- **Postconditions**:
  - Marks `listing.status = ListingStatus.ON_HOLD`.
  - Records `remedies_by_reservation[ticket.reservation_id] = "rebooking"`.
  - Adds `max(Decimal("0.00"), listing.nightly_price - ticket.nightly_price) * ticket.nights` to `uplift_spent`.
  - Appends `ToolCallRecord(tool_name="hold_booking", allowed=True, ...)`.

### Tool 2: `issue_refund(agent_role, ticket, amount=None)`
- **Preconditions**:
  1. `agent_role == AgentRole.REFUND_AGENT` (else raise `UnauthorizedToolError`).
  2. Ticket has no active safety lock (`ticket_type != TicketType.SAFETY` or handoff completed; else raise `SafetyHandoffRequiredError`).
  3. Stay (`ticket.reservation_id`) has no existing booking hold or refund (one remedy per stay; else raise `PolicyViolationError`).
  4. Effective `amount = ticket.total_paid if amount is None else amount` satisfies `Decimal("0.01") <= amount <= ticket.total_paid` (else raise `PolicyViolationError`).
- **Postconditions**:
  - Records `remedies_by_reservation[ticket.reservation_id] = "refund"`.
  - Appends `ToolCallRecord(tool_name="issue_refund", allowed=True, refund_amount=amount, ...)`.

### Tool 3: `handoff_to_safety_agent(agent_role, ticket, conditions)`
- **Preconditions**:
  1. `agent_role == AgentRole.SAFETY_AGENT` (else raise `UnauthorizedToolError`).
  2. `len(conditions) >= 1` (at least one `SafetyCondition` identified in `ticket.guest_message`).
- **Postconditions**:
  - Adds `ticket.ticket_id` to `safety_handoffs_completed`.
  - Records `remedies_by_reservation[ticket.reservation_id] = "safety_handoff"`.
  - Appends `ToolCallRecord(tool_name="handoff_to_safety_agent", allowed=True, safety_conditions=conditions, ...)`.

---

## 3. CLI Contract (`python -m stranded_guest_support`)

- **Command**:
  `python -m stranded_guest_support --tickets <tickets.csv> [--listings <open_listings.csv>] [--json]`
- **Behavior**:
  - Loads tickets from `--tickets` (defaults to `Lisbon Stranded Guest Tickets (16 Nov 2026).csv` if present).
  - If `--listings` is provided, runs full triage + rebooking/refund/safety resolution against the open listings CSV and prints per-ticket resolutions and incident summary (counts, total uplift vs EUR 9,000 budget, policy checks).
  - If `--listings` is omitted, runs triage and safety/refund validation and reports classification counts (`rebooking`, `refund`, `safety`) plus expected-outcome verification when `expected_outcome` is present.
- **Exit Codes**:
  - `0`: All tickets triaged/processed without policy violations.
  - `1`: Input error, missing required file, or policy/verification failure.
