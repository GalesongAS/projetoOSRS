import io
import json
import re
import tarfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "quests.json"

# --- turn quest name into stable card id ---
def slugify(name: str) -> str:
    s = name.lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[’']", "", s)          # remove apostrophes
    s = re.sub(r"[^a-z0-9]+", "_", s)   # non-alnum -> _
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def card_id_for_quest(name: str) -> str:
    return f"quest_{slugify(name)}"

def npm_latest_tarball(package: str) -> tuple[str, str]:
    # registry returns latest version + tarball url
    meta = requests.get(f"https://registry.npmjs.org/{package}/latest", timeout=30).json()
    return meta["version"], meta["dist"]["tarball"]

def extract_quest_js_files(tgz_bytes: bytes) -> dict[str, str]:
    # returns {filename: filetext} for dist/model/quest/all/*.js
    out: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(tgz_bytes), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            # package/dist/model/quest/all/<Quest>.js
            if m.name.startswith("package/dist/model/quest/all/") and m.name.endswith(".js"):
                f = tf.extractfile(m)
                if not f:
                    continue
                out[Path(m.name).name] = f.read().decode("utf-8", errors="replace")
    return out

def parse_field(text: str, field: str):
    # crude but works for these minified object literals
    # supports 'x' or "x" or numbers/bools
    # e.g. name: 'Lost City'
    m = re.search(rf"{re.escape(field)}\s*:\s*'([^']*)'", text)
    if m:
        return m.group(1)
    m = re.search(rf'{re.escape(field)}\s*:\s*"([^"]*)"', text)
    if m:
        return m.group(1)
    m = re.search(rf"{re.escape(field)}\s*:\s*(true|false)\b", text)
    if m:
        return m.group(1) == "true"
    m = re.search(rf"{re.escape(field)}\s*:\s*([0-9]+)\b", text)
    if m:
        return int(m.group(1))
    return None

def parse_enum_name(text: str, field: str) -> str | None:
    # difficulty: enums_1.QuestDifficulty.Intermediate
    m = re.search(rf"{re.escape(field)}\s*:\s*[^.]+\.[A-Za-z_]+\.(\w+)", text)
    return m.group(1) if m else None

def parse_requirements(text: str):
    # We only extract:
    # - LevelRequirement('Woodcutting', 36, ...)
    # - QuestRequirement('Cook\'s Assistant')
    levels = re.findall(r"LevelRequirement\(\s*['\"]([^'\"]+)['\"]\s*,\s*([0-9]+)", text)
    quests = re.findall(r"QuestRequirement\(\s*['\"]([^'\"]+)['\"]\s*\)", text)
    return levels, quests

def main():
    pkg = "osrs-tools"
    version, tarball = npm_latest_tarball(pkg)
    print(f"Using {pkg} {version}")
    tgz = requests.get(tarball, timeout=60).content
    js_files = extract_quest_js_files(tgz)

    # pass 1: build name list so we can map prereq quest names -> ids
    quests_basic = []
    for fname, code in js_files.items():
        name = parse_field(code, "name")
        if not name:
            continue
        miniquest = parse_field(code, "miniquest") or False
        if miniquest:
            continue  # keep it simple: skip miniquests for now
        quests_basic.append(name)

    name_to_id = {name: card_id_for_quest(name) for name in quests_basic}

    # pass 2: build quest cards
    quest_cards = []
    missing_prereqs = set()

    for fname, code in js_files.items():
        name = parse_field(code, "name")
        if not name:
            continue
        if parse_field(code, "miniquest"):
            continue

        members = bool(parse_field(code, "members"))
        qp = int(parse_field(code, "questPoints") or 0)
        url = parse_field(code, "url") or ""
        difficulty = parse_enum_name(code, "difficulty") or "Unknown"

        levels, prereq_names = parse_requirements(code)

        requires = []
        for skill, lvl in levels:
            requires.append({"kind": "SKILL_CAP_AT_LEAST", "skill": skill, "cap": int(lvl)})

        for qn in prereq_names:
            qid = name_to_id.get(qn)
            if qid:
                requires.append({"kind": "CARD_COMPLETED", "cardId": qid})
            else:
                missing_prereqs.add(qn)

        # weights by difficulty (tweak to taste)
        weight_map = {"Novice": 12, "Intermediate": 8, "Experienced": 5, "Master": 2, "Grandmaster": 1}
        weight = weight_map.get(difficulty, 5)

        quest_cards.append({
            "id": name_to_id.get(name, card_id_for_quest(name)),
            "type": "QUEST",
            "title": name,
            "description": f"Complete the OSRS quest: {name}.",
            "weight": weight,
            "requires": requires,
            "meta": {"members": members, "difficulty": difficulty, "questPoints": qp, "url": url},
        })

    quest_cards.sort(key=lambda c: c["title"].lower())

    OUT_PATH.write_text(json.dumps(quest_cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(quest_cards)} quest cards to: {OUT_PATH}")

    if missing_prereqs:
        print("\n⚠️ Some prereq quest names were not found in the dataset name list (you can ignore or map manually):")
        for qn in sorted(missing_prereqs)[:50]:
            print(" -", qn)
        if len(missing_prereqs) > 50:
            print(f" ... and {len(missing_prereqs)-50} more")

if __name__ == "__main__":
    main()
