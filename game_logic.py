import secrets

from app_constants import (
    QUEST_GREEN,
    QUEST_RED,
    QUEST_YELLOW,
    SLAYER_CHANCE_CAP,
    SLAYER_CURVE,
    SLAYER_END_MULT,
    SLAYER_PITY_CAP,
    SLAYER_PITY_PER_TASK,
    SLAYER_START_MULT,
)


def weighted_pick(items):
    total = sum(max(0, int(i.get("weight", 1))) for i in items)
    if total <= 0:
        return items[secrets.randbelow(len(items))]
    r = secrets.randbelow(total)
    acc = 0
    for it in items:
        acc += max(0, int(it.get("weight", 1)))
        if r < acc:
            return it
    return items[-1]


def check_requires(state, card):
    reqs = card.get("requires", []) or []
    caps = state["skillCaps"]
    completed = set(state["completedCardIds"])

    for r in reqs:
        kind = r.get("kind")
        if kind == "SKILL_CAP_AT_LEAST":
            skill = r["skill"]
            needed = int(r["cap"])
            if int(caps.get(skill, 1)) < needed:
                return False
        elif kind == "CARD_COMPLETED":
            cid = r["cardId"]
            if cid not in completed:
                return False
        else:
            return False
    return True


def gate_satisfied(state):
    g = state.get("activeGate")
    if not g:
        return True
    if g.get("kind") == "REACH_LEVEL":
        skill = g["skill"]
        target = int(g["level"])
        cur = int(state["reachedLevels"].get(skill, 1))
        return cur >= target
    return True


def apply_unlock_effects(state, card):
    for eff in card.get("effects", []) or []:
        if eff.get("kind") == "SET_SKILL_CAP":
            skill = eff["skill"]
            cap = int(eff["cap"])
            state["skillCaps"][skill] = max(int(state["skillCaps"].get(skill, 1)), cap)


def complete_active_card(state, repeatable: bool = False):
    cid = state.get("activeCardId")
    if not cid:
        return False

    if not repeatable and cid not in state["completedCardIds"]:
        state["completedCardIds"].append(cid)

    state["activeCardId"] = None
    state["activeGate"] = None
    return True


def fmt_pct(p: float) -> str:
    return f"{p * 100:.1f}%"


def validate_cards(cards: list[dict]):
    bad = 0
    for c in cards:
        for r in c.get("requires") or []:
            if r.get("kind") == "SKILL_CAP_AT_LEAST" and "cap" not in r:
                bad += 1
                print("\n[INVALID requires] Missing 'cap'")
                print("  card id:", c.get("id"))
                print("  title  :", c.get("title"))
                print("  requires entry:", r)
    if bad:
        print(f"\nFound {bad} invalid requires entries.\n")


def resolve_gate(gate: dict) -> dict | None:
    if not gate:
        return None
    g = dict(gate)

    if g.get("kind") in ("MARKS_OF_GRACE", "DIARIES"):
        mn = int(g.get("min", 1))
        mx = int(g.get("max", mn))
        if mx < mn:
            mx = mn
        g["amount"] = mn + secrets.randbelow(mx - mn + 1)
    return g


def gate_amount_text(g: dict | None) -> str:
    if not g:
        return ""
    kind = g.get("kind")
    amt = int(g.get("amount", g.get("min", 1)))
    if kind == "MARKS_OF_GRACE":
        return f"Requirement: Collect {amt} Marks of grace."
    if kind == "DIARIES":
        return f"Requirement: Complete {amt} achievement diaries."
    return ""


def gate_range_text(g: dict | None) -> str:
    if not g:
        return ""
    kind = g.get("kind")
    mn = int(g.get("min", g.get("amount", 1)))
    mx = int(g.get("max", mn))
    if mx < mn:
        mx = mn

    def fmt_range(unit_singular: str, unit_plural: str):
        if mn == mx:
            unit = unit_singular if mn == 1 else unit_plural
            return f"Requirement: {mn} {unit}."
        return f"Requirement: {mn}-{mx} {unit_plural}."

    if kind == "MARKS_OF_GRACE":
        return "Requirement: Collect " + fmt_range("Mark of grace", "Marks of grace")[13:]
    if kind == "DIARIES":
        return "Requirement: Complete " + fmt_range("achievement diary", "achievement diaries")[13:]
    return ""


def slayer_pack_chance_for(st: dict, base_chance: float) -> float:
    max_packs = int(st.get("maxPacks", 0))
    found = int(st.get("packsFound", 0))
    remaining = max(0, max_packs - found)
    if max_packs <= 0 or remaining <= 0:
        return 0.0

    remaining_ratio = remaining / max_packs
    start_chance = min(SLAYER_CHANCE_CAP, base_chance * SLAYER_START_MULT)
    end_chance = min(SLAYER_CHANCE_CAP, base_chance * SLAYER_END_MULT)

    chance = end_chance + (start_chance - end_chance) * (remaining_ratio**SLAYER_CURVE)

    since = int(st.get("sinceLastPack", 0))
    pity = min(SLAYER_PITY_CAP, since * SLAYER_PITY_PER_TASK)

    return min(SLAYER_CHANCE_CAP, max(0.0, chance + pity))


def tracked_skills(state: dict):
    items = []
    for skill, cap in (state.get("skillCaps", {}) or {}).items():
        cap_i = int(cap)
        if cap_i >= 99:
            continue
        reached_i = max(1, min(cap_i, int(state.get("reachedLevels", {}).get(skill, 1))))
        items.append((skill, cap_i, reached_i))
    items.sort(key=lambda x: x[0].lower())
    return items


def is_repeatable(card: dict) -> bool:
    return bool(card.get("repeatable", False))


def draw_pack_options(eligible: list[dict], draw_n: int) -> list[dict]:
    pool = eligible[:]
    options: list[dict] = []

    def remove_from_pool(picked_id: str):
        nonlocal pool
        pool = [x for x in pool if x["id"] != picked_id]

    if draw_n >= 3:
        nonquests = [c for c in pool if c.get("type") != "QUEST"]
        if nonquests:
            first = weighted_pick(nonquests)
            options.append(first)
            remove_from_pool(first["id"])

    max_quests_if_possible = draw_n - 1

    while len(options) < draw_n and pool:
        quest_count = sum(1 for o in options if o.get("type") == "QUEST")
        nonquests_left = [c for c in pool if c.get("type") != "QUEST"]

        if nonquests_left and quest_count >= max_quests_if_possible:
            pick = weighted_pick(nonquests_left)
        else:
            pick = weighted_pick(pool)
            if (
                pick.get("type") == "QUEST"
                and nonquests_left
                and quest_count >= max_quests_if_possible
            ):
                pick = weighted_pick(nonquests_left)

        options.append(pick)
        remove_from_pool(pick["id"])

    return options


def quest_status(state: dict, qid: str) -> str:
    if qid in state.get("completedCardIds", []):
        return "COMPLETE"
    if state.get("activeCardId") == qid:
        return "ACTIVE"
    return "INCOMPLETE"


def quest_color(status: str) -> str:
    if status == "COMPLETE":
        return QUEST_GREEN
    if status == "ACTIVE":
        return QUEST_YELLOW
    return QUEST_RED
