# Stranded Guest Support

A Python package and agent-team specification for handling stranded guest check-in support tickets under AirCover rebooking and refund policy (Lisbon Check-In Incident, 16 November 2026).

## Ticket Handling Rules

Support rules are derived from [AirCover Rebooking and Refund Rules - Lisbon Check-In Incident.md](AirCover%20Rebooking%20and%20Refund%20Rules%20-%20Lisbon%20Check-In%20Incident.md) (`aircover_rebooking_refund_rules.md`), [Lisbon Stranded Guest Tickets (16 Nov 2026).csv](Lisbon%20Stranded%20Guest%20Tickets%20(16%20Nov%202026).csv) (`airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv`), and detailed in [specs/001-ticket-handling-rules/spec.md](specs/001-ticket-handling-rules/spec.md).

### Ticket Types and Specialist Agents

Every ticket is classified into one of three ticket types and handled by a dedicated specialist agent:

| Ticket Type | Specialist Agent | Permitted Booking/Action Tool | Policy Scope |
|---|---|---|---|
| `rebooking` | **Rebooking agent** | `hold_booking` | Places holds on comparable open listings (`LST-100001`–`LST-100450`) for qualifying stranded guests; also retains angry-word and callback-only tickets when no safety condition is present |
| `refund` | **Refund agent** | `issue_refund` | Issues refunds up to `total_paid` when the guest requests a refund, declines rebooking, or has no comparable listing available |
| `safety` | **Safety agent** | `handoff_to_safety_agent` (only) | Immediately hands off to a live Trust and Safety agent; strictly forbidden from calling `issue_refund` or `hold_booking` before hand-off |

### Safety Triage Rules (Highest Priority)

If **any one** of the five AirCover safety conditions appears in `guest_message`, the ticket **must** be routed to a live safety agent via `handoff_to_safety_agent`—even when `guest_requested` is `refund`, `callback`, `rebooking`, or `other`, and even when the guest asks only for money, a call, or a new flat without mentioning "safety" or "emergency":

1. `injury_or_medical_need` — someone is hurt, unwell, pregnant, needs medication, or needs a doctor
2. `threat_or_violence` — someone has threatened, followed, shouted at, or harmed the guest
3. `nowhere_safe_to_wait` — out on the street at night, phone dying, alone with luggage, nowhere to go
4. `unaccompanied_minor` — a guest under 18 travelling or waiting without an adult
5. `stated_fear_of_person` — afraid of the host, a neighbour, a stranger, or someone in the party

**Critical safety guardrail**: On a `safety` ticket, **no agent may call `issue_refund` or `hold_booking` before `handoff_to_safety_agent`**. After hand-off, the live safety agent decides any refund or booking.

### Non-Safety Routing and Qualifying Conditions

- **Angry words or callback requests alone**: Frustrated/angry wording or a `callback` request without any of the five AirCover safety conditions stays with the **rebooking agent** (`rebooking`), not `safety`.
- **Qualifying conditions**: A guest qualifies when any one of the following is true:
  1. No working access provided at check-in (empty key box, wrong code, no one at the door)
  2. Host unreachable (`host_last_reply_at` empty or not after the guest's contact; `guest_message`)
  3. Host cancelled within 30 days before `check_in_date`
- **Stay coverage & refusals**: Support covers the full remaining stay (`check_in_date` to `check_out_date`). Turning down one offer does not end the guest's right to another comparable home or to a full refund.

### Comparable Home & Financial Limits

- **Rebooking price cap (120%)**: Every rebooked home must satisfy `listing nightly_price <= 1.20 * original nightly_price` (no above-120% overrides are available on 16 November 2026, even if part of the EUR 9,000 total uplift budget / EUR 150 planning average remains).
- **Five mandatory comparable-home tests**:
  1. **Dates covered**: `available_from <= check_in_date` and `available_to >= check_out_date` with no gap
  2. **Fits the party**: `max_guests >= party_size`
  3. **Enough bedrooms**: listing `bedrooms >= ticket bedrooms`
  4. **Can be held now**: `status = available` (`on_hold` and `booked` fail)
  5. **Price ceiling**: `listing nightly_price <= 1.20 * ticket nightly_price`
  *(Same or neighbouring Lisbon `neighborhood` is preferred, not a pass/fail gate.)*
- **Refund cap (`total_paid`)**: Refunds never exceed `total_paid` (including promo-discounted reservations; no goodwill or inconvenience additions above `total_paid`). Any partial amount from EUR 0.01 up to `total_paid` is within policy, and a full `total_paid` refund is due when no comparable home exists or the guest declines rebooking.
- **One remedy per stay**: A refund closes the stay and is never combined with a rebooking for the same nights.

## Development

Install the package in editable mode with `python -m pip install -e .`.
