"""Safety condition detection and safety-first ticket classification."""

from __future__ import annotations

import re

from .models import SafetyCondition, SupportTicket, TicketType

# Uniform regex table mapping each AirCover safety condition to multi-language cues.
# Hyperbolic frustration idioms ("dying out here", "lose it") are deliberately excluded.
SAFETY_CONDITION_PATTERNS: dict[SafetyCondition, tuple[re.Pattern[str], ...]] = {
    SafetyCondition.INJURY_OR_MEDICAL_NEED: (
        re.compile(
            r"\b(bleeding|injured|injury|fracture[ds]?|sprained|concussion|unconscious|"
            r"can hardly stand|cannot stand|bad hip|diabetic|insulin|pale and shaky|"
            r"seizure|asthma|chest pain|allergic reaction|pregnant|medication|medicine|"
            r"needs? a doctor|hospital|ambulance|paramedic|medical help)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(a sangrar|ferid[oa]|m[ée]dico|urg[êe]ncia|gr[áa]vida|"
            r"sangrando|herid[oa]|embarazada|médico|"
            r"saigne|bless[ée]|enceinte|m[ée]decin|"
            r"blutet|verletzt|schwanger|arzt|"
            r"sanguin|ferit[oa]|incinta|medico)\b",
            re.IGNORECASE,
        ),
    ),
    SafetyCondition.THREAT_OR_VIOLENCE: (
        re.compile(
            r"\b(threaten(?:ed|ing)?|followed me|following me|stalking|"
            r"watching the door|smash my|shouted at|yelled at|screamed at|"
            r"assault(?:ed)?|attacked|harmed|punched|hit me|pushed me|"
            r"still on the stairs|weapon|knife|violent|violence)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(amea[çc]|seguindo|persegu|amenaz|siguiendo|menac|suiv|"
            r"bedroh|verfolg|minacci|seguendo)\b",
            re.IGNORECASE,
        ),
    ),
    SafetyCondition.NOWHERE_SAFE_TO_WAIT: (
        re.compile(
            r"\b(nowhere safe|nowhere to wait|nowhere to go|do not know where to go|"
            r"don't know where to go|phone is on \d+%|phone (?:is )?dying|"
            r"battery (?:is )?(?:dying|dead)|out on the street at night|"
            r"on the street at night|sleeping on the street|outside in the dark|"
            r"alone with (?:my |our )?(?:luggage|bags|suitcases)|"
            r"asked me to leave.*(?:cold|nowhere|street))\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(sem s[íi]tio seguro|na rua [àa] noite|bateria a acabar|"
            r"sin lugar seguro|en la calle de noche|"
            r"nulle part o[ùu] aller|dans la rue la nuit|"
            r"nirgendwo sicher|auf der stra[ßs]e|"
            r"nessun posto sicuro|in strada di notte)\b",
            re.IGNORECASE,
        ),
    ),
    SafetyCondition.UNACCOMPANIED_MINOR: (
        re.compile(
            r"\b(unaccompanied minor|under 18|without an adult|"
            r"(?:i am|i'm|he is|she is|guest is|aged?)\s+(?:1[0-7]|[1-9])\b"
            r"(?:.*(?:on my own|alone|travelling|traveling|without an adult))?)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(menor desacompanhad[oa]|menor de 18|menor no acompa[ñn]ado|"
            r"mineur non accompagn[ée]|unbegleitete[rs]? minderj[äa]hrige|"
            r"minore non accompagnat[oa])\b",
            re.IGNORECASE,
        ),
    ),
    SafetyCondition.STATED_FEAR_OF_PERSON: (
        re.compile(
            r"\b((?:scared|afraid|terrified|frightened|fearful)\s+"
            r"(?:of|to\b|that|for my safety)|feel unsafe|unsafe around)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(com medo d[eao]|tenho medo|tengo miedo|asustad[oa]|"
            r"j'ai peur|effray[ée]|angst vor|f[üu]rchte|"
            r"ho paura|spaventat[oa])\b",
            re.IGNORECASE,
        ),
    ),
}


def detect_safety_conditions(guest_message: str) -> tuple[SafetyCondition, ...]:
    """Return all AirCover safety conditions detected in guest_message."""
    if not guest_message:
        return ()
    matched: list[SafetyCondition] = []
    for condition, patterns in SAFETY_CONDITION_PATTERNS.items():
        if any(pattern.search(guest_message) for pattern in patterns):
            matched.append(condition)
    return tuple(matched)


def classify_ticket(ticket: SupportTicket) -> tuple[TicketType, tuple[SafetyCondition, ...]]:
    """Classify a ticket with safety-first triage before evaluating guest_requested."""
    safety_conditions = detect_safety_conditions(ticket.guest_message)
    if safety_conditions:
        return TicketType.SAFETY, safety_conditions

    requested = ticket.guest_requested.strip().lower()
    if requested == "refund":
        return TicketType.REFUND, ()

    # Rebooking, callback, other, and angry-word messages without safety triggers
    # stay with the rebooking agent.
    return TicketType.REBOOKING, ()
