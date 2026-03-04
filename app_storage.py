import json
import os


def read_json_safe(path: str, fallback):
    try:
        if os.path.exists(path):
            return read_json(path)
    except Exception:
        pass
    return fallback


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def default_save(config):
    caps = dict(config.get("startingCaps", {}))
    masters = {
        m["id"]: {
            "tasks": 0,
            "packsFound": 0,
            "maxPacks": int(m["maxPacks"]),
            "sinceLastPack": 0,
        }
        for m in config.get("slayerMasters", [])
    }

    return {
        "version": 3,
        "unopenedPacks": 0,
        "packsOpened": 0,
        "taskLog": [],
        "pendingPackOptionIds": [],
        "lastPackOptionIds": [],
        "lastPackPickedId": None,
        "skillCaps": caps,
        "reachedLevels": {},
        "activeCardId": None,
        "activeGate": None,
        "obtainedCardIds": [],
        "completedCardIds": [],
        "slayerMasters": masters,
    }


def migrate_save(state: dict, config: dict) -> dict:
    state.setdefault("unopenedPacks", 0)
    state.setdefault("packsOpened", 0)
    state.setdefault("skillCaps", {})
    state.setdefault("reachedLevels", {})
    state.setdefault("activeCardId", None)
    state.setdefault("activeGate", None)
    state.setdefault("obtainedCardIds", [])
    state.setdefault("completedCardIds", [])
    state.setdefault("taskLog", [])
    state.setdefault("pendingPackOptionIds", [])
    state.setdefault("lastPackOptionIds", [])
    state.setdefault("lastPackPickedId", None)

    defaults = config.get("startingCaps", {})
    for skill, cap in defaults.items():
        if skill not in state["skillCaps"]:
            state["skillCaps"][skill] = cap

    state.setdefault("slayerMasters", {})
    for m in config.get("slayerMasters", []):
        mid = m["id"]
        if mid not in state["slayerMasters"]:
            state["slayerMasters"][mid] = {
                "tasks": 0,
                "packsFound": 0,
                "maxPacks": int(m["maxPacks"]),
                "sinceLastPack": 0,
            }
        else:
            state["slayerMasters"][mid]["maxPacks"] = int(m["maxPacks"])
            state["slayerMasters"][mid].setdefault("sinceLastPack", 0)

    return state
