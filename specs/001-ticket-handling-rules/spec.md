# Feature Specification: Stranded Guest Support Ticket Handling Rules

**Feature Branch**: `001-ticket-handling-rules`

**Created**: 2026-11-27

**Status**: Draft

**Input**: User description: "Ticket handling rules for the Stranded guest support agent team, from airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv and aircover_rebooking_refund_rules.md. Ticket types: rebooking, refund and safety. Name three specialist agents: a rebooking agent that may use hold_booking, a refund agent that may use issue_refund, and a safety agent that may only use handoff_to_safety_agent. Any one of the five AirCover safety conditions in the guest message sends the ticket to a live safety agent, even when the guest asks only for money, a call or a new flat. On a safety ticket no agent may call issue_refund or hold_booking before handoff_to_safety_agent. Angry words or a callback request alone stay with the rebooking agent. Refunds never exceed total_paid. Rebooked homes stay within 120% of the original nightly_price."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Safety Triage and Mandatory Hand-Off (Priority: P1)

A stranded guest contacts support after being locked out or having their Lisbon reservation cancelled on 16 November 2026, and their `guest_message` describes any one of the five AirCover safety conditions (`injury_or_medical_need`, `threat_or_violence`, `nowhere_safe_to_wait`, `unaccompanied_minor`, or `stated_fear_of_person`). Even if the ticket's `guest_requested` field is `refund`, `rebooking`, `callback`, or `other`, and even if the guest explicitly asks only for money, a phone call, or a new flat without mentioning "safety" or "emergency", the ticket is classified as `safety` and routed to the **safety agent**, which immediately transfers the case to a live Trust and Safety agent using `handoff_to_safety_agent`. No financial refund or replacement hold is executed prior to that hand-off.

**Why this priority**: Guest physical safety and duty of care for vulnerable, injured, threatened, or stranded guests supersede all commercial rebooking or refund workflows. Issuing a refund or booking a flat without a live safety hand-off leaves at-risk guests without immediate human intervention.

**Independent Test**: Can be fully tested by evaluating tickets whose `guest_message` contains any of the five safety conditions (across `refund`, `rebooking`, `callback`, and `other` request types) and verifying that the ticket is routed to the safety agent, `handoff_to_safety_agent` is the sole action invoked, and neither `issue_refund` nor `hold_booking` is called beforehand.

**Acceptance Scenarios**:

1. **Given** a ticket where `guest_requested` is `refund` and `guest_message` describes a bleeding injury (`injury_or_medical_need`, e.g., `LIS-TKT-0007`), **When** the support team processes the ticket, **Then** the ticket is classified as `safety`, assigned to the safety agent, and handled solely via `handoff_to_safety_agent` with zero calls to `issue_refund` or `hold_booking`.
2. **Given** a ticket where `guest_requested` is `callback` and `guest_message` indicates an `unaccompanied_minor` (and/or `nowhere_safe_to_wait`, e.g., `LIS-TKT-0015`), **When** the support team processes the ticket, **Then** the ticket is classified as `safety` and transferred via `handoff_to_safety_agent` before any booking or refund action.
3. **Given** a ticket where `guest_requested` is `rebooking` or `other` and `guest_message` describes `nowhere_safe_to_wait`, `threat_or_violence`, `stated_fear_of_person`, or `injury_or_medical_need` (e.g., `LIS-TKT-0023`, `LIS-TKT-0034`, `LIS-TKT-0046`, `LIS-TKT-0055`), **When** the support team processes the ticket, **Then** the ticket is classified as `safety` and only `handoff_to_safety_agent` is invoked so the live safety agent decides any subsequent booking or refund.

---

### User Story 2 - Comparable Home Rebooking Within Policy Limits (Priority: P2)

A qualifying locked-out guest without any safety condition asks for a replacement place, asks a general question (`other`), requests a `callback` to hear options, or expresses frustration with angry words or hyperbolic complaints (`rebooking` or `callback` with no safety condition). The ticket is classified as `rebooking` and routed to the **rebooking agent**, which selects an eligible open listing (`LST-100001` to `LST-100450`) covering the full remaining stay (`check_in_date` to `check_out_date`) that passes all five comparable-home tests—including a `nightly_price` no higher than 120% of the original `nightly_price`—and places a hold using `hold_booking`.

**Why this priority**: Most stranded guests need immediate accommodation for their remaining Lisbon nights (34 of the 60 incident tickets), and enforcing comparable-home rules prevents over-budget holds, under-sized rooms, or misclassifying angry or callback tickets as safety escalations.

**Independent Test**: Can be fully tested by presenting non-safety tickets (including `rebooking`, `callback`, `other`, and frustrated/angry messages) alongside open listing inventory and verifying that the rebooking agent invokes `hold_booking` only on an `available` listing passing all five comparable-home criteria without invoking `issue_refund`.

**Acceptance Scenarios**:

1. **Given** a qualifying non-safety ticket requesting a replacement stay (e.g., `LIS-TKT-0001`, `LIS-TKT-0003`, `LIS-TKT-0019`), **When** the rebooking agent evaluates open listings (`LST-100001` to `LST-100450`), **Then** it selects a listing with `status` = `available`, `available_from` <= `check_in_date`, `available_to` >= `check_out_date`, `max_guests` >= `party_size`, `bedrooms` >= original `bedrooms`, and `nightly_price` <= 1.20 * original `nightly_price`, and calls `hold_booking`.
2. **Given** a non-safety ticket containing angry words, urgency, or figurative frustration without any of the five safety conditions (e.g., `LIS-TKT-0005`, `LIS-TKT-0022`, `LIS-TKT-0041`), **When** the ticket is triaged, **Then** it remains a `rebooking` ticket handled by the rebooking agent rather than escalating to `safety`.
3. **Given** a non-safety ticket with `guest_requested` = `callback` or `other` and no safety condition (e.g., `LIS-TKT-0017`, `LIS-TKT-0029`, `LIS-TKT-0039`, `LIS-TKT-0049`, `LIS-TKT-0059`, `LIS-TKT-0060`), **When** the ticket is triaged, **Then** it stays with the rebooking agent.
4. **Given** a candidate open listing whose `nightly_price` exceeds 120% of the ticket's original `nightly_price` (e.g., EUR 132.01 when original `nightly_price` is EUR 110.00), **When** the rebooking agent checks comparability on 16 November 2026, **Then** the listing is rejected and cannot be held via `hold_booking`, even if total incident uplift budget remains.
5. **Given** a guest declines an offered comparable home, **When** another comparable open listing is available, **Then** the guest retains the right to another comparable offer or to decline rebooking altogether and receive a full refund.

---

### User Story 3 - Policy-Capped Refund Processing (Priority: P3)

A qualifying locked-out guest without any safety condition explicitly requests a refund instead of rebooking (for example, because they are returning home, staying with contacts, or booking a hotel), or declines rebooking, or has no comparable open listing available. The ticket is classified as `refund` and routed to the **refund agent**, which issues a refund up to—and never exceeding—`total_paid` using `issue_refund`, closing the stay without combining a rebooking for the same nights.

**Why this priority**: Accurate refund handling satisfies the 20 non-safety refund requests cleanly while strictly preventing overpayments above `total_paid` (especially on discounted or promo-code bookings) and preventing duplicate remedies (refund plus rebooking).

**Independent Test**: Can be fully tested by processing non-safety refund tickets (including promo-discounted reservations where `total_paid` is less than `nightly_price` multiplied by nights) and verifying that the refund agent invokes `issue_refund` for an amount between EUR 0.01 and `total_paid` inclusive, with no `hold_booking` call.

**Acceptance Scenarios**:

1. **Given** a non-safety ticket where the guest requests a refund (e.g., `LIS-TKT-0004`, `LIS-TKT-0008`, `LIS-TKT-0018`), **When** the refund agent processes the ticket, **Then** it calls `issue_refund` for `total_paid` and does not call `hold_booking` for the same stay.
2. **Given** a reservation booked with a promo code where `total_paid` is lower than `nightly_price` multiplied by the number of nights (e.g., `LIS-TKT-0028` with 4 nights at EUR 120.00/night and `total_paid` = EUR 432.00), **When** the refund agent issues a refund, **Then** the refund amount does not exceed `total_paid` (EUR 432.00) and no goodwill or inconvenience top-up above `total_paid` is added.
3. **Given** a non-safety rebooking ticket where either no open listing passes all five comparable-home tests or the guest declines rebooking, **When** the guest is transitioned to a refund resolution, **Then** a full refund equal to `total_paid` is issued via `issue_refund` and no rebooking hold is kept for those nights.

---

### Edge Cases

- **Conflicting guest request vs. safety condition**: A guest sets `guest_requested` to `refund`, `rebooking`, `callback`, or `other` and asks only for money, a call, or a flat, while `guest_message` reveals an injury, medical episode, threat, stalker/fear, minor alone, or nowhere safe to wait. Safety always overrides the stated request; the ticket becomes `safety` and only `handoff_to_safety_agent` may be called.
- **Figurative or angry language without a safety condition**: A guest uses intense or hyperbolic phrasing (e.g., "I am dying out here", "worst day of our lives", "before we all lose it", demanding immediate replacement without apology). Unless one of the five AirCover safety conditions is actually present, the ticket stays with the rebooking agent and is not routed to `safety`.
- **Callback request without a safety condition**: A guest selects `callback` and asks someone to phone them to review housing options (`LIS-TKT-0017`, `LIS-TKT-0039`, `LIS-TKT-0049`, `LIS-TKT-0059`). Unless a safety condition is present (as in `LIS-TKT-0015`), the ticket stays with the rebooking agent.
- **Exact 120% nightly price boundary**: A listing priced at exactly `1.20 * original nightly_price` (e.g., EUR 132.00 for an EUR 110.00 booking) passes; a listing at EUR 132.01 fails. Because policy manager Laura Schmidt's override sign-off is unavailable on 16 November 2026, no above-120% exception is permitted.
- **Zero-bedroom studios**: Original `bedrooms = 0` (`Entire studio`) allows open listings with `bedrooms >= 0` (studio or 1+ bedroom) provided all other comparability tests pass.
- **Promo-discounted bookings**: `total_paid` can be less than `nightly_price * nights` (`LIS-TKT-0028`). The refund ceiling is always `total_paid`, never the undiscounted nightly rate total.
- **Neighborhood preference vs. hard constraint**: Matching or neighbouring Lisbon `neighborhood` is preferred when selecting among comparable homes, not a pass/fail gate; guests open to any area (`LIS-TKT-0029`, `LIS-TKT-0060`) or when the original neighborhood has no match may be rebooked into any qualifying Lisbon neighborhood.
- **Non-open original listing IDs**: `original_listing_id` values (`LST-200001` through `LST-200060`) are absent from open listings; holds must reference open `listing_id` values (`LST-100001` through `LST-100450`) with `status = available`.
- **No double remedy**: A guest cannot receive both a rebooking (`hold_booking`) and a refund (`issue_refund`) for the same nights.
- **Non-English guest messages**: Tickets arrive in multiple languages (`en`, `pt`, `es`, `fr`, `de`, `it`); safety detection and ticket triage apply regardless of `guest_language`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The support workflow MUST classify every incoming incident ticket into exactly one of three ticket types: `rebooking`, `refund`, or `safety`.
- **FR-002**: The support team MUST define and enforce three distinct specialist agents with strict action boundaries:
  - **Rebooking agent**: may invoke `hold_booking` (and MUST NOT invoke `issue_refund` or bypass safety hand-off).
  - **Refund agent**: may invoke `issue_refund` (and MUST NOT invoke `hold_booking` or bypass safety hand-off).
  - **Safety agent**: may ONLY invoke `handoff_to_safety_agent` (and MUST NOT invoke `hold_booking` or `issue_refund`).
- **FR-003**: Before any booking or refund action occurs, ticket triage MUST inspect `guest_message` for the five AirCover safety conditions:
  1. `injury_or_medical_need` (injured, unwell, pregnant, needs medication, or needs a doctor)
  2. `threat_or_violence` (threatened, followed, shouted at, or harmed)
  3. `nowhere_safe_to_wait` (out on the street at night, phone dying, alone with luggage, nowhere to go)
  4. `unaccompanied_minor` (guest under 18 travelling or waiting without an adult)
  5. `stated_fear_of_person` (afraid of the host, a neighbour, a stranger, or someone in the party)
- **FR-004**: If ANY one of the five safety conditions appears in `guest_message`, the ticket MUST be classified as `safety` and routed to the safety agent, regardless of `guest_requested` (`rebooking`, `refund`, `callback`, or `other`) and regardless of whether the guest asks only for money, a call, or a new flat, or omits the words "safety" or "emergency".
- **FR-005**: On every `safety` ticket, no agent may call `issue_refund` or `hold_booking` before `handoff_to_safety_agent` completes; only `handoff_to_safety_agent` is permitted prior to live Trust and Safety takeover, after which the live safety agent decides any refund or booking.
- **FR-006**: Tickets containing angry words, complaints, or a `callback` request without any of the five AirCover safety conditions MUST remain with the rebooking agent (classified as `rebooking`), rather than escalating to `safety`.
- **FR-007**: A guest MUST qualify for rebooking support when at least one qualifying condition holds:
  1. No working access at check-in (empty lockbox, wrong code, nobody at the door) as described in `guest_message`
  2. Host unreachable (`host_last_reply_at` empty or not after the guest's contact, and/or stated in `guest_message`)
  3. Host cancelled within 30 days before `check_in_date` (`host_cancelled_at` within 30 days prior to `check_in_date`)
- **FR-008**: Rebooking support MUST cover the entire remaining stay from `check_in_date` to `check_out_date`, not only the first night.
- **FR-009**: The rebooking agent MUST invoke `hold_booking` only on an open listing (`LST-100001` to `LST-100450`) that passes all five comparable-home tests simultaneously:
  1. `available_from` <= `check_in_date` and `available_to` >= `check_out_date` (continuous coverage with no gap)
  2. `max_guests` >= `party_size`
  3. Open listing `bedrooms` >= ticket `bedrooms`
  4. Open listing `status` = `available` at the time of hold (`on_hold` and `booked` fail)
  5. Open listing `nightly_price` <= `1.20 *` original ticket `nightly_price`
- **FR-010**: On 16 November 2026, the rebooking agent MUST NOT offer or hold any home priced above 120% of the original `nightly_price`, even if remaining incident uplift budget exists (overall incident uplift budget is EUR 9,000 across the 60 tickets, with a EUR 150 planning average per rebooked guest).
- **FR-011**: When multiple open listings pass all five comparable-home tests, the rebooking agent SHOULD prefer a listing in the same or a neighbouring Lisbon `neighborhood`, while treating neighborhood matching as a preference rather than a pass/fail eligibility gate.
- **FR-012**: Turning down an offered comparable home MUST NOT terminate a qualifying guest's right to another comparable home offer or to a full refund.
- **FR-013**: The refund agent MUST process eligible non-safety tickets (where the guest requests a refund, declines rebooking, or has no comparable open listing available) via `issue_refund` with an amount from EUR 0.01 up to and never exceeding the ticket's `total_paid` (no goodwill or inconvenience additions above `total_paid`).
- **FR-014**: When no open listing passes the comparable-home tests or the guest declines rebooking, the refund agent MUST issue the full `total_paid` via `issue_refund`.
- **FR-015**: The support workflow MUST enforce one remedy per stay: a refund closes the stay and MUST NOT be combined with a rebooking (`hold_booking`) for the same nights.

### Key Entities

- **Support Ticket**: Represents a stranded guest incident (`ticket_id` `LIS-TKT-0001` through `LIS-TKT-0060`) containing reservation context (`reservation_id`, `original_listing_id` `LST-200001`–`LST-200060`, `neighborhood`, `property_type`, `bedrooms`, `party_size`, `check_in_date`, `check_out_date`, `nightly_price`, `total_paid`), host communication timestamps (`host_cancelled_at`, `host_last_reply_at`), guest request details (`guest_language`, `guest_requested`, `guest_message`), and expected classification (`rebooking`, `refund`, or `safety`).
- **Open Listing**: Represents an available Lisbon replacement property (`listing_id` `LST-100001` through `LST-100450`) with availability window (`available_from`, `available_to`), capacity (`max_guests`, `bedrooms`), neighborhood (`neighborhood`), nightly rate (`nightly_price`), and booking availability (`status`: `available`, `on_hold`, or `booked`).
- **Specialist Agent Role**: One of three support agent roles—`rebooking` agent (`hold_booking`), `refund` agent (`issue_refund`), or `safety` agent (`handoff_to_safety_agent`)—each restricted to its permitted tool and policy rules.
- **AirCover Safety Condition**: One of five triage triggers (`injury_or_medical_need`, `threat_or_violence`, `nowhere_safe_to_wait`, `unaccompanied_minor`, `stated_fear_of_person`) detected in `guest_message` that mandates immediate `safety` classification and `handoff_to_safety_agent`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of tickets exhibiting any of the five AirCover safety conditions in `guest_message` (6 of 60 in the 16 November 2026 Lisbon incident dataset) are routed to the safety agent and invoke `handoff_to_safety_agent` with 0 pre-handoff calls to `issue_refund` or `hold_booking`.
- **SC-002**: 100% of tickets in the 60-ticket incident dataset are classified accurately into `rebooking` (34 tickets), `refund` (20 tickets), and `safety` (6 tickets), including 100% retention of non-safety `callback` (4 tickets), `other` (2 tickets), and angry-language tickets with the rebooking agent.
- **SC-003**: 100% of rebooking holds placed via `hold_booking` satisfy all five comparable-home tests, with 0 holds exceeding 120% of the ticket's original `nightly_price` and 0 holds on `on_hold` or `booked` listings.
- **SC-004**: 100% of refunds issued via `issue_refund` stay within `[EUR 0.01, total_paid]`, with 0 refunds exceeding `total_paid` and 0 stays receiving both a rebooking hold and a refund for the same nights.
- **SC-005**: Every stranded guest in the incident receives a rebooking hold, a refund, or a live safety agent hand-off before midnight on 16 November 2026, while total rebooking uplift stays within the EUR 9,000 incident budget.

## Assumptions

- Source rules and ticket dataset correspond to [AirCover Rebooking and Refund Rules - Lisbon Check-In Incident.md](../../AirCover%20Rebooking%20and%20Refund%20Rules%20-%20Lisbon%20Check-In%20Incident.md) (referenced as `aircover_rebooking_refund_rules.md`) and [Lisbon Stranded Guest Tickets (16 Nov 2026).csv](../../Lisbon%20Stranded%20Guest%20Tickets%20(16%20Nov%202026).csv) (referenced as `airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv`).
- The companion open listings export (`airbnb_lisbon_open_listings_2026-11-16.csv`, containing 450 open Lisbon listings `LST-100001`–`LST-100450`) is provided at runtime or in the environment where the agent team executes rebooking checks, even though it is not yet checked into the repository.
- Initial ticket triage operates before any specialist booking or refund tool is executed so safety screening always precedes `hold_booking` and `issue_refund`.
- All monetary amounts in the Lisbon incident dataset are denominated in EUR.
