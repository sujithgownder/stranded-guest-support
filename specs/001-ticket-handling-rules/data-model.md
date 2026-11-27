# Data Model: Stranded Guest Support Ticket Handling

**Feature**: [spec.md](spec.md)  
**Date**: 2026-11-27

## Enumerations

### `TicketType`
- `rebooking`: Qualifying stranded guest seeking replacement accommodation, asking a non-safety question (`other`), requesting a `callback` without safety triggers, or expressing anger/frustration without safety triggers.
- `refund`: Non-safety qualifying guest requesting a refund, declining offered comparable homes, or having no comparable open listing available.
- `safety`: Ticket where `guest_message` exhibits any one of the five `SafetyCondition` values.

### `SafetyCondition`
- `injury_or_medical_need`
- `threat_or_violence`
- `nowhere_safe_to_wait`
- `unaccompanied_minor`
- `stated_fear_of_person`

### `AgentRole`
- `rebooking_agent`: Permitted tool = `hold_booking`
- `refund_agent`: Permitted tool = `issue_refund`
- `safety_agent`: Permitted tool = `handoff_to_safety_agent` only

### `ListingStatus`
- `available` (eligible for `hold_booking`)
- `on_hold` (fails comparability holdability check)
- `booked` (fails comparability holdability check)

---

## Core Entities

### 1. `SupportTicket`
Represents one stranded-guest incident record from `Lisbon Stranded Guest Tickets (16 Nov 2026).csv` (`airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv`).

| Field | Type | Constraints / Notes |
|---|---|---|
| `ticket_id` | `str` | Unique identifier (`LIS-TKT-0001`–`LIS-TKT-0060`) |
| `opened_at` | `datetime` (UTC) | ISO-8601 timestamp when ticket opened |
| `reservation_id` | `str` | Unique reservation key (`RES-2026-10001`–`RES-2026-10060`) |
| `guest_name` | `str` | Non-empty guest display name |
| `guest_language` | `str` | ISO language code (`en`, `pt`, `es`, `fr`, `de`, `it`) |
| `original_listing_id` | `str` | Original listing (`LST-200001`–`LST-200060`); not in open listings |
| `original_listing_title` | `str` | Original property title |
| `neighborhood` | `str` | Original Lisbon neighborhood |
| `property_type` | `str` | e.g., `Entire apartment`, `Entire studio`, `Entire townhouse`, `Private room` |
| `bedrooms` | `int` | `>= 0` (`0` for studios) |
| `party_size` | `int` | `>= 1` |
| `check_in_date` | `date` | Stay start date (`2026-11-16`) |
| `check_out_date` | `date` | Stay end date (`> check_in_date`) |
| `nightly_price` | `Decimal` | Original nightly rate in EUR (`> 0.00`) |
| `total_paid` | `Decimal` | Total paid by guest in EUR (`> 0.00`); may be `< nightly_price * nights` when discounted |
| `host_id` | `str` | Host identifier (`HOST-...`) |
| `host_cancelled_at` | `datetime \| None` | Empty if not cancelled in app |
| `host_last_reply_at` | `datetime \| None` | Empty if host never replied |
| `guest_requested` | `str` | `rebooking`, `refund`, `callback`, or `other` |
| `guest_message` | `str` | Free-text guest message inspected for safety & check-in access issues |
| `expected_outcome` | `str \| None` | Optional benchmark label (`rebooking`, `refund`, `safety`) |

**Derived Properties**:
- `nights = (check_out_date - check_in_date).days` (`>= 1`)
- `max_rebook_nightly_price = (nightly_price * Decimal("1.20")).quantize(Decimal("0.01"))`

### 2. `OpenListing`
Represents a candidate replacement property from `airbnb_lisbon_open_listings_2026-11-16.csv`.

| Field | Type | Constraints / Notes |
|---|---|---|
| `listing_id` | `str` | Must be in open inventory range (`LST-100001`–`LST-100450`) |
| `neighborhood` | `str` | Lisbon neighborhood used for preference ranking |
| `property_type` | `str` | Property classification |
| `bedrooms` | `int` | Must be `>= ticket.bedrooms` to pass comparability |
| `max_guests` | `int` | Must be `>= ticket.party_size` to pass comparability |
| `available_from` | `date` | Must be `<= ticket.check_in_date` |
| `available_to` | `date` | Must be `>= ticket.check_out_date` |
| `nightly_price` | `Decimal` | Must be `<= 1.20 * ticket.nightly_price` |
| `status` | `ListingStatus` | Must equal `available` at hold time |

### 3. `ToolCallRecord`
Immutable audit entry created whenever a specialist agent executes (or attempts) a booking/refund/safety action.

| Field | Type | Constraints / Notes |
|---|---|---|
| `ticket_id` | `str` | Target ticket |
| `reservation_id` | `str` | Target reservation |
| `agent_role` | `AgentRole` | Calling specialist agent |
| `tool_name` | `str` | `hold_booking`, `issue_refund`, or `handoff_to_safety_agent` |
| `allowed` | `bool` | Whether policy guard permitted execution |
| `listing_id` | `str \| None` | Present on `hold_booking` |
| `refund_amount` | `Decimal \| None` | Present on `issue_refund` (`0.01 <= amount <= total_paid`) |
| `safety_conditions` | `tuple[SafetyCondition, ...]` | Present on `handoff_to_safety_agent` |
| `rejection_reason` | `str \| None` | Populated if policy guard blocked the call |

### 4. `IncidentLedger`
Tracks stay-level remedies and incident-wide financial totals across a batch of tickets.

| Field | Type | Constraints / Notes |
|---|---|---|
| `remedies_by_reservation` | `dict[str, str]` | Maps `reservation_id` -> `"rebooking"`, `"refund"`, or `"safety_handoff"` |
| `total_uplift_budget` | `Decimal` | `Decimal("9000.00")` incident cap across all 60 tickets |
| `uplift_spent` | `Decimal` | Sum of `max(0, listing.nightly_price - ticket.nightly_price) * nights` |
| `safety_handoffs_completed` | `set[str]` | `ticket_id` values handed off via `handoff_to_safety_agent` |

---

## Validation Rules & State Transitions

### Ticket Triage & Remedy State Machine

```text
[Ticket Received]
       │
       ├──(Any 1 of 5 SafetyConditions in guest_message)──► [safety]
       │         │
       │         └─► SafetyAgent -> handoff_to_safety_agent() -> [Live Safety Hand-Off]
       │             (hold_booking & issue_refund HARD-BLOCKED prior to handoff)
       │
       ├──(No safety condition AND guest_requested == "refund")──► [refund]
       │         │
       │         └─► RefundAgent -> issue_refund(<= total_paid) -> [Closed: Refunded]
       │
       └──(No safety condition AND guest_requested in {"rebooking","callback","other"})──► [rebooking]
                 │
                 ├─(Qualifies AND comparable listing available)
                 │    └─► RebookingAgent -> hold_booking(listing) -> [Held: Rebooked]
                 │         (listing.status transitions: available -> on_hold)
                 │
                 └─(No comparable listing OR guest declines offer)
                      └─► RefundAgent -> issue_refund(total_paid) -> [Closed: Refunded]
```

### Hard Invariants
1. **Safety Pre-Handoff Lock**: If `ticket_type == safety` and `ticket_id not in safety_handoffs_completed`, any call to `hold_booking` or `issue_refund` raises `PolicyViolationError`.
2. **Agent Tool Isolation**:
   - `rebooking_agent` can call only `hold_booking`.
   - `refund_agent` can call only `issue_refund`.
   - `safety_agent` can call only `handoff_to_safety_agent`.
3. **120% Price Ceiling**: `listing.nightly_price <= ticket.nightly_price * Decimal("1.20")`. No override is permitted on 16 November 2026.
4. **Refund Cap**: `Decimal("0.01") <= amount <= ticket.total_paid`.
5. **One Remedy Per Stay**: A `reservation_id` with a `"rebooking"` remedy cannot receive an `"issue_refund"` for the same stay, and a `"refund"` closes the stay against any `"hold_booking"`.
