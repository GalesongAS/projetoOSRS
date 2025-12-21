import json
import os
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
CARDS_PATH = os.path.join(HERE, "cards.json")
BACKUP_PATH = os.path.join(HERE, "cards.json.bak")

# Weight per tier end-cap (early = more common, late = rarer)
WEIGHT_BY_END = {
    10: 14,
    20: 12,
    30: 10,
    40: 9,
    50: 8,
    60: 7,
    70: 6,
    80: 5,
    90: 4,
    99: 3,
}

def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

def slug(s: str) -> str:
    return s.strip().lower().replace(" ", "-")

def tiers():
    # (start, end) pairs: 1-10, 11-20, ... 91-99
    out = []
    start = 1
    end = 10
    while end < 99:
        out.append((start, end))
        start = end + 1
        end = min(end + 10, 99)
        if end == 99:
            out.append((start, end))
            break
    # ensure last is 91-99 (not 91-100)
    return out

def make_unlock_cards(skills):
    cards = []
    for skill in skills:
        prev_end = None
        for start, end in tiers():
            sid = f"unlock-{slug(skill)}-{start:03d}-{end:03d}"
            title = f"{skill} {start} \u2192 {end}"
            desc = (
                f"Increase your {skill} cap to {end}. "
                f"You must reach {end} before opening another pack."
            )

            card = {
                "id": sid,
                "type": "UNLOCK",
                "title": title,
                "description": desc,
                "weight": WEIGHT_BY_END.get(end, 5),
                "effects": [{"kind": "SET_SKILL_CAP", "skill": skill, "cap": end}],
                "gate": {"kind": "REACH_LEVEL", "skill": skill, "level": end},
                # marker so we can safely regenerate later
                "_generated": "skill_unlock_v1",
            }

            # require previous cap before next tier can appear
            if prev_end is not None:
                card["requires"] = [{"kind": "SKILL_CAP_AT_LEAST", "skill": skill, "cap": prev_end}]

            cards.append(card)
            prev_end = end
    return cards

def main():
    config = read_json(CONFIG_PATH)
    starting_caps = config.get("startingCaps", {})

    # skills we want unlock cards for = anything not already 99-cap
    skills = [s for s, cap in starting_caps.items() if int(cap) < 99]
    skills.sort(key=lambda x: x.lower())

    existing = read_json(CARDS_PATH) if os.path.exists(CARDS_PATH) else []

    # keep your hand-made cards, remove only previous generated unlocks
    kept = [c for c in existing if c.get("_generated") != "skill_unlock_v1"]

    generated = make_unlock_cards(skills)

    # backup + write
    if os.path.exists(CARDS_PATH):
        write_json(BACKUP_PATH, existing)

    new_cards = kept + generated
    write_json(CARDS_PATH, new_cards)

    print(f"Done. Skills: {len(skills)}. Generated unlock cards: {len(generated)}.")
    print(f"Updated: {CARDS_PATH}")
    if os.path.exists(BACKUP_PATH):
        print(f"Backup:  {BACKUP_PATH}")

if __name__ == "__main__":
    main()
