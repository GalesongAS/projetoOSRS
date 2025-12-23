import json
import os
import secrets
import flet as ft
from datetime import datetime


HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
CARDS_PATH = os.path.join(HERE, "cards.json")
QUESTS_PATH = os.path.join(HERE, "quests.json")

SAVE_DIR = os.path.join(os.path.expanduser("~"), ".runecards")
SAVE_PATH = os.path.join(SAVE_DIR, "save.json")

ASSETS_DIR = os.path.join(HERE, "assets")

# Version-safe colors namespace
C = ft.Colors if hasattr(ft, "Colors") else ft.colors

# --- OSRS-ish palette (tweak freely) ---
OSRS_BG = "#0f0d0a"
PANEL_BG = "#211c15"
PANEL_INNER = "#17130f"
BORDER_DARK = "#0a0806"
BORDER_LIGHT = "#5b4f3b"
TEXT_MAIN = "#d7c9ae"
TEXT_DIM = "#b6a789"
ACCENT = "#c9b06a"
QUEST_RED = "#d14b43"
QUEST_GREEN = "#3ddc62"
QUEST_YELLOW = "#ffd166"

# --- Slayer pack drop tuning ---
SLAYER_START_MULT = 2.3
SLAYER_END_MULT = 0.50
SLAYER_CURVE = 1.0
SLAYER_PITY_PER_TASK = 0.02
SLAYER_PITY_CAP = 0.25
SLAYER_CHANCE_CAP = 0.90

NOTES_TEXT = (
    "• Packs stack.\n"
    "• You can only have 1 active card.\n"
    "• Gated unlocks block opening packs until you confirm the requirement.\n"
    "• Slayer Masters have finite pack pools."
)

# ---------- IO ----------
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

# ---------- State ----------
def default_save(config):
    caps = dict(config.get("startingCaps", {}))
    masters = {
        m["id"]: {"tasks": 0, "packsFound": 0, "maxPacks": int(m["maxPacks"]), "sinceLastPack": 0}
        for m in config.get("slayerMasters", [])
    }

    return {
        "version": 3,
        "unopenedPacks": 0,
        "packsOpened": 0,
        "taskLog": [],
        "pendingPackOptionIds": [],

        # keep last opened pack visible after picking
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

# ---------- Card logic ----------
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
    return False

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

# ---------- UI helpers ----------
def panel(content, padding=16):
    return ft.Container(
        padding=padding,
        bgcolor=PANEL_BG,
        border_radius=14,
        border=ft.border.all(1, BORDER_DARK),
        content=ft.Container(
            padding=12,
            bgcolor=PANEL_INNER,
            border_radius=12,
            border=ft.border.all(1, BORDER_LIGHT),
            content=content,
        ),
    )

def osrs_button(text: str, on_click, primary=False):
    return ft.Container(
        border_radius=10,
        border=ft.border.all(1, BORDER_LIGHT),
        bgcolor=("#3a2f1f" if primary else "#2b241a"),
        padding=ft.padding.symmetric(horizontal=14, vertical=10),
        on_click=on_click,
        content=ft.Text(text, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
    )

def icon_button(img_src: str, on_click, tooltip: str = "", size: int = 22):
    return ft.Container(
        width=size + 18,
        height=size + 18,
        border_radius=10,
        border=ft.border.all(1, BORDER_LIGHT),
        bgcolor="#2b241a",
        padding=8,
        tooltip=tooltip or None,
        on_click=on_click,
        content=ft.Image(src=img_src, width=size, height=size, fit=ft.ImageFit.CONTAIN),
    )

def stat_pill(label: str, value_control: ft.Control):
    return ft.Container(
        padding=ft.padding.symmetric(horizontal=10, vertical=6),
        border_radius=999,
        bgcolor="#1a1510",
        border=ft.border.all(1, BORDER_LIGHT),
        content=ft.Row(
            tight=True,
            spacing=6,
            controls=[
                ft.Text(label, color=TEXT_DIM, size=11),
                value_control,
            ],
        ),
    )

def action_tile(
    title: str,
    subtitle: str,
    on_click,
    *,
    badge: ft.Control | None = None,
    icon_src: str | None = None,
    emoji_fallback: str = "★",
    primary: bool = False,
):
    bg = "#3a2f1f" if primary else "#15110d"

    icon_ok = False
    if icon_src:
        icon_ok = os.path.exists(os.path.join(ASSETS_DIR, icon_src.replace("/", os.sep)))

    icon_control = (
        ft.Image(src=icon_src, width=24, height=24, fit=ft.ImageFit.CONTAIN)
        if icon_ok
        else ft.Text(emoji_fallback, size=18, color=TEXT_MAIN)
    )

    return ft.Container(
        padding=12,
        border_radius=12,
        bgcolor=bg,
        border=ft.border.all(1, BORDER_LIGHT),
        on_click=on_click,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=40,
                            height=40,
                            border_radius=10,
                            bgcolor="#1a1510",
                            border=ft.border.all(1, BORDER_LIGHT),
                            alignment=ft.alignment.center,
                            content=icon_control,
                        ),
                        ft.Column(
                            spacing=1,
                            controls=[
                                ft.Text(title, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                                ft.Text(subtitle, color=TEXT_DIM, size=11),
                            ],
                        ),
                    ],
                ),
                badge if badge else ft.Container(width=0, height=0),
            ],
        ),
    )

def main(page: ft.Page):
    page.fonts = {"OSRS": "fonts/RunescapeChat.ttf"}
    page.theme = ft.Theme(font_family="OSRS")

    page.title = "RuneCards"
    page.bgcolor = OSRS_BG
    page.window_width = 1200
    page.window_height = 760

    config = read_json(CONFIG_PATH)

    all_cards = read_json(CARDS_PATH)
    if os.path.exists(QUESTS_PATH):
        all_cards.extend(read_json(QUESTS_PATH))
    cards_by_id = {c["id"]: c for c in all_cards}

    if os.path.exists(SAVE_PATH):
        state = migrate_save(read_json(SAVE_PATH), config)
    else:
        state = default_save(config)

    # ✅ SAFETY: if a pack was opened but not picked, keep showing the same options after restart
    pending = list(state.get("pendingPackOptionIds") or [])
    if pending:
        if not state.get("lastPackOptionIds"):
            state["lastPackOptionIds"] = pending[:]
        # you haven't picked yet, so force None
        state["lastPackPickedId"] = None

    write_json(SAVE_PATH, state)

    status_text = ft.Text("", size=12, color=TEXT_DIM)
    status_box = ft.Container(
        visible=False,
        padding=ft.padding.symmetric(horizontal=12, vertical=8),
        border_radius=12,
        bgcolor="#15110d",
        border=ft.border.all(1, BORDER_LIGHT),
        content=status_text,
    )

    def set_status(msg: str, color: str):
        status_text.value = msg
        status_text.color = color
        status_box.visible = True
        page.update()

    def save():
        write_json(SAVE_PATH, state)

    def snack(msg: str):
        page.snack_bar = ft.SnackBar(ft.Text(msg, color=TEXT_MAIN))
        page.snack_bar.open = True
        page.update()

    def open_dialog(dlg: ft.AlertDialog):
        if hasattr(page, "open"):
            page.open(dlg)
        else:
            if dlg not in page.overlay:
                page.overlay.append(dlg)
            dlg.open = True
            page.update()

    def close_dialog(dlg: ft.AlertDialog):
        if hasattr(page, "close"):
            page.close(dlg)
        else:
            dlg.open = False
            page.update()

    def total_slayer_tasks():
        return sum(int(v.get("tasks", 0)) for v in state.get("slayerMasters", {}).values())

    def config_master_name(master_id: str) -> str:
        for mm in config.get("slayerMasters", []):
            if mm["id"] == master_id:
                return mm.get("name", master_id)
        return master_id

    top_packs = ft.Text(color=TEXT_MAIN, weight=ft.FontWeight.BOLD)
    top_tasks = ft.Text(color=TEXT_MAIN, weight=ft.FontWeight.BOLD)
    top_opened = ft.Text(color=TEXT_MAIN, weight=ft.FontWeight.BOLD)

    left_packs = ft.Text(color=TEXT_MAIN, weight=ft.FontWeight.BOLD)
    left_tasks = ft.Text(color=TEXT_MAIN, weight=ft.FontWeight.BOLD)

    def is_repeatable(card: dict) -> bool:
        return bool(card.get("repeatable", False))

    def resolve_gate(gate: dict) -> dict:
        if not gate:
            return None
        g = dict(gate)
        if g.get("kind") == "MARKS_OF_GRACE":
            mn = int(g.get("min", 1))
            mx = int(g.get("max", mn))
            if mx < mn:
                mx = mn
            g["amount"] = mn + secrets.randbelow(mx - mn + 1)
        return g

    def slayer_pack_chance_for(st: dict) -> float:
        base = float(config["packChancePerSlayerTask"])

        max_packs = int(st.get("maxPacks", 0))
        found = int(st.get("packsFound", 0))
        remaining = max(0, max_packs - found)
        if max_packs <= 0 or remaining <= 0:
            return 0.0

        remaining_ratio = remaining / max_packs
        start_chance = min(SLAYER_CHANCE_CAP, base * SLAYER_START_MULT)
        end_chance = min(SLAYER_CHANCE_CAP, base * SLAYER_END_MULT)

        chance = end_chance + (start_chance - end_chance) * (remaining_ratio ** SLAYER_CURVE)

        since = int(st.get("sinceLastPack", 0))
        pity = min(SLAYER_PITY_CAP, since * SLAYER_PITY_PER_TASK)

        return min(SLAYER_CHANCE_CAP, max(0.0, chance + pity))

    def log_completed(card: dict, detail: str = ""):
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "cardId": card.get("id"),
            "title": card.get("title", card.get("id")),
            "type": card.get("type", "?"),
            "detail": detail,
        }
        state.setdefault("taskLog", []).append(entry)

    # ---------- Pack UI (RIGHT PANEL) ----------
    pack_title = ft.Text("Pack opening — pick 1 of 3", size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)
    pack_hint = ft.Text("Pick one card. After picking, the other 2 remain (dimmed).", color=TEXT_DIM, size=11)

    # “empty” state: keep it empty like you asked
    pack_empty = ft.Container(height=0)
    pack_empty.visible = True

    pack_options_row = ft.Row(
        spacing=12,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )
    pack_options_row.visible = False
    
    # ✅ Create once (NOT inside render_pack_from_state)
    complete_btn_section = ft.Container(
        alignment=ft.alignment.center,
        padding=ft.padding.only(top=10),
        visible=False,  # toggled in refresh()
        content=ft.Container(
            border_radius=14,
            border=ft.border.all(1, BORDER_LIGHT),
            bgcolor="#3a2f1f",
            padding=ft.padding.symmetric(horizontal=34, vertical=18),  # bigger
            on_click=lambda e: complete_current_card(e),  # resolves at click time
            content=ft.Text(
                "Complete task",
                color=TEXT_MAIN,
                size=16,
                weight=ft.FontWeight.BOLD,
            ),
        ),
    )


    def refresh():
        top_packs.value = str(state["unopenedPacks"])
        top_tasks.value = str(total_slayer_tasks())
        top_opened.value = str(int(state.get("packsOpened", 0)))
        
        complete_btn_section.visible = bool(state.get("activeCardId"))


        left_packs.value = top_packs.value
        left_tasks.value = top_tasks.value        

        page.update()

    def pick_card(card: dict):
        if state.get("lastPackPickedId"):
            return

        state["activeCardId"] = card["id"]
        state["lastPackPickedId"] = card["id"]

        # Pick completes the pack selection -> clear pending safety
        state["pendingPackOptionIds"] = []

        if not is_repeatable(card) and card["id"] not in state["obtainedCardIds"]:
            state["obtainedCardIds"].append(card["id"])

        if card.get("type") == "UNLOCK":
            apply_unlock_effects(state, card)

        if card.get("gate"):
            state["activeGate"] = resolve_gate(card["gate"])
        else:
            state["activeGate"] = None

        save()
        refresh()
        render_pack_from_state()
        snack("Card selected!")


    def render_pack_from_state():
        # If user restarted with a pending pack, always prefer that
        if state.get("pendingPackOptionIds") and not state.get("lastPackOptionIds"):
            state["lastPackOptionIds"] = list(state["pendingPackOptionIds"])
            state["lastPackPickedId"] = None
            save()

        ids = list(state.get("lastPackOptionIds") or [])
        picked_id = state.get("lastPackPickedId")

        pack_options_row.controls.clear()


        if not ids:
            pack_empty.visible = True
            pack_options_row.visible = False
            page.update()
            return

        options = [cards_by_id[cid] for cid in ids if cid in cards_by_id]
        if not options:
            pack_empty.visible = True
            pack_options_row.visible = False
            page.update()
            return

        pack_empty.visible = False
        pack_options_row.visible = True

        has_picked = bool(picked_id)

        def make_tile(card: dict) -> ft.Control:
            cid = card.get("id")
            is_picked = (picked_id == cid)

            tile_opacity = 1.0 if (not has_picked or is_picked) else 0.33
            tile_border = ft.border.all(2 if is_picked else 1, ACCENT if is_picked else BORDER_LIGHT)
            tile_bg = "#3a2f1f" if is_picked else "#2b241a"

            click_handler = (lambda e, c=card: pick_card(c)) if not has_picked else None

            badge = None
            if is_picked:
                badge = ft.Container(
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                    border_radius=999,
                    bgcolor="#1a1510",
                    border=ft.border.all(1, ACCENT),
                    content=ft.Text("PICKED", color=ACCENT, size=11, weight=ft.FontWeight.BOLD),
                )

            # ✅ NO ft.Expanded() — use expand=1 on Container instead (works on older Flet)
            return ft.Container(
                expand=1,
                height=260,          # taller / less wide feel
                opacity=tile_opacity,
                padding=14,
                border_radius=12,
                bgcolor=tile_bg,
                border=tile_border,
                on_click=click_handler,
                content=ft.Column(
                    spacing=8,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(
                                    card.get("title", cid or "?"),
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXT_MAIN,
                                ),
                                badge if badge else ft.Container(width=0, height=0),
                            ],
                        ),
                        ft.Text(f"[{card.get('type','?')}]", color=ACCENT),
                        ft.Text(card.get("description", ""), color=TEXT_DIM),
                        ft.Text("Click to choose" if not has_picked else "", size=12, color=TEXT_DIM),
                    ],
                ),
            )

        for c in options:
            pack_options_row.controls.append(make_tile(c))

        page.update()

    def draw_pack_options(eligible: list[dict], draw_n: int) -> list[dict]:
        pool = eligible[:]
        options = []

        def remove_from_pool(picked_id: str):
            nonlocal pool
            pool = [x for x in pool if x["id"] != picked_id]

        if draw_n == 3:
            nonquests = [c for c in pool if c.get("type") != "QUEST"]
            if nonquests:
                first = weighted_pick(nonquests)
                options.append(first)
                remove_from_pool(first["id"])

        while len(options) < draw_n and pool:
            quest_count = sum(1 for o in options if o.get("type") == "QUEST")
            remaining = draw_n - len(options)
            nonquests_left = [c for c in pool if c.get("type") != "QUEST"]

            if draw_n == 3 and remaining == 1 and quest_count >= 2 and nonquests_left:
                pick = weighted_pick(nonquests_left)
            else:
                pick = weighted_pick(pool)
                if draw_n == 3 and pick.get("type") == "QUEST" and quest_count >= 2 and nonquests_left:
                    pick = weighted_pick(nonquests_left)

            options.append(pick)
            remove_from_pool(pick["id"])

        return options

    def open_pack(_):
        if state.get("activeCardId"):
            snack("You already have an active card.")
            return

        # Safety: if pending exists, always reuse it (no reroll / no extra pack consumed)
        pending_ids = list(state.get("pendingPackOptionIds") or [])
        if pending_ids:
            state["lastPackOptionIds"] = pending_ids[:]
            state["lastPackPickedId"] = None
            save()
            refresh()
            render_pack_from_state()
            return

        if state["unopenedPacks"] <= 0:
            snack("No packs available.")
            return

        if state.get("activeGate") and not gate_satisfied(state):
            g = state["activeGate"]
            snack(f"Blocked by gate: reach {g.get('skill')} {g.get('level')}.")
            return

        obtained = set(state["obtainedCardIds"])
        completed = set(state["completedCardIds"])

        eligible = []
        for c in all_cards:
            if (not is_repeatable(c)) and (c["id"] in obtained or c["id"] in completed):
                continue
            if not check_requires(state, c):
                continue
            eligible.append(c)

        if not eligible:
            snack("No eligible cards left.")
            return

        draw_n = min(int(config.get("cardsPerPack", 3)), len(eligible))
        options = draw_pack_options(eligible, draw_n)
        option_ids = [c["id"] for c in options]

        state["unopenedPacks"] -= 1
        state["packsOpened"] = int(state.get("packsOpened", 0)) + 1

        # pending safety (no free reroll if app closes)
        state["pendingPackOptionIds"] = option_ids[:]

        # visible pack
        state["lastPackOptionIds"] = option_ids[:]
        state["lastPackPickedId"] = None

        save()
        refresh()
        render_pack_from_state()

    def complete_task_for_master(master_id: str):
        masters = state["slayerMasters"]
        st = masters[master_id]

        st["tasks"] = int(st.get("tasks", 0)) + 1
        st["sinceLastPack"] = int(st.get("sinceLastPack", 0)) + 1

        max_packs = int(st.get("maxPacks", 0))
        found = int(st.get("packsFound", 0))
        can_still_drop = found < max_packs

        chance = slayer_pack_chance_for(st) if can_still_drop else 0.0

        if can_still_drop and secrets.randbelow(10_000) < int(chance * 10_000):
            state["unopenedPacks"] += 1
            st["packsFound"] = found + 1
            st["sinceLastPack"] = 0
            save()
            refresh()
            snack(f"{config_master_name(master_id)} task complete → pack found!")
            set_status(f"{config_master_name(master_id)} gave you a pack!", QUEST_GREEN)
        else:
            save()
            refresh()
            if not can_still_drop:
                snack(f"{config_master_name(master_id)} task complete → no packs left for this master.")
                set_status(f"{config_master_name(master_id)} has no packs left.", TEXT_DIM)
            else:
                snack(f"{config_master_name(master_id)} task complete → no pack this time.")
                set_status(f"{config_master_name(master_id)} did not give you a pack this time.", QUEST_RED)

    # Minimal placeholders for dialogs (keep yours if you want)
    def open_task_log_window(_):
        dlg = ft.AlertDialog(modal=True)
        list_view = ft.ListView(expand=True, spacing=6, padding=10)

        header_stats = ft.Text("", color=TEXT_DIM, size=11)

        def rebuild():
            list_view.controls.clear()
            logs = list(state.get("taskLog", []))

            if not logs:
                header_stats.value = "No entries yet."
                list_view.controls.append(ft.Text("No completed tasks yet.", color=TEXT_DIM))
                page.update()
                return

            # Keep FULL history in save.json,
            # but only render the last N to keep UI snappy.
            render_limit = 500
            shown = logs[-render_limit:]
            header_stats.value = f"Showing last {len(shown)} of {len(logs)} entries"

            for e in reversed(shown):  # newest first
                ts = e.get("ts", "")
                title = e.get("title", e.get("cardId", "?"))
                typ = e.get("type", "?")
                detail = e.get("detail", "")

                list_view.controls.append(
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=10, vertical=8),
                        border_radius=10,
                        bgcolor="#15110d",
                        border=ft.border.all(1, BORDER_LIGHT),
                        content=ft.Column(
                            spacing=2,
                            controls=[
                                ft.Text(title, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                                ft.Text(f"{ts} • {typ}", color=TEXT_DIM, size=11),
                                ft.Text(detail, color=ACCENT, size=11) if detail else ft.Container(height=0),
                            ],
                        ),
                    )
                )

            page.update()

        rebuild()

        dlg.content = ft.Container(
            width=560,
            height=560,
            bgcolor=PANEL_BG,
            border=ft.border.all(1, BORDER_DARK),
            border_radius=14,
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Text("Task Log", size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                    header_stats,
                                ],
                            ),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text("X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                            ),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        bgcolor=PANEL_INNER,
                        border=ft.border.all(1, BORDER_LIGHT),
                        border_radius=12,
                        content=list_view,
                    ),
                ],
            ),
        )

        open_dialog(dlg)

        # ---------- Skills window ----------
    def asset_exists(rel_path: str) -> bool:
        return os.path.exists(os.path.join(ASSETS_DIR, rel_path.replace("/", os.sep)))

    def tracked_skills():
        items = []
        for skill, cap in (state.get("skillCaps", {}) or {}).items():
            cap_i = int(cap)
            if cap_i >= 99:
                continue
            items.append((skill, cap_i))
        items.sort(key=lambda x: x[0].lower())
        return items

    def skill_tile(skill: str, cap: int):
        icon_rel = f"skills/{skill.lower()}.png"
        has_icon = asset_exists(icon_rel)

        icon = (
            ft.Image(
                src=icon_rel,
                width=34,
                height=34,
                fit=ft.ImageFit.CONTAIN,
                opacity=1.0 if cap > 1 else 0.35,
            )
            if has_icon
            else ft.Text(
                skill[:2].upper(),
                color=TEXT_MAIN,
                opacity=1.0 if cap > 1 else 0.35,
                weight=ft.FontWeight.BOLD,
            )
        )

        lock_rel = "ui/lock.png"
        lock_control = (
            ft.Image(src=lock_rel, width=22, height=22, opacity=0.95)
            if asset_exists(lock_rel)
            else ft.Text("🔒", size=16, opacity=0.95)
        )

        cap_badge = ft.Container(
            padding=ft.padding.symmetric(horizontal=6, vertical=2),
            bgcolor="#2a241a",
            border=ft.border.all(1, BORDER_LIGHT),
            border_radius=6,
            content=ft.Text(str(cap), size=12, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
        )

        return ft.Container(
            width=84,
            height=60,
            border_radius=8,
            bgcolor="#1a1510",
            border=ft.border.all(1, BORDER_LIGHT),
            content=ft.Stack(
                controls=[
                    ft.Container(expand=True, alignment=ft.alignment.center, content=icon),
                    ft.Container(expand=True, alignment=ft.alignment.center, content=lock_control, visible=(cap <= 1)),
                    ft.Container(expand=True, alignment=ft.alignment.top_right, padding=6, content=cap_badge, visible=(cap > 1)),
                ]
            ),
        )

    def open_skills_window(_):
        tiles = [skill_tile(skill, cap) for skill, cap in tracked_skills()]

        if hasattr(ft, "GridView"):
            grid = ft.GridView(
                expand=True,
                max_extent=90,
                child_aspect_ratio=1.35,
                spacing=8,
                run_spacing=8,
            )
            grid.controls = tiles
            grid_content = grid
        else:
            grid_content = ft.Row(controls=tiles, wrap=True, spacing=8, run_spacing=8)

        dlg = ft.AlertDialog(modal=True)
        dlg.content = ft.Container(
            width=420,
            height=360,
            bgcolor=PANEL_BG,
            border=ft.border.all(1, BORDER_DARK),
            border_radius=14,
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("Unlocked Skills", size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text("X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                            ),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        bgcolor=PANEL_INNER,
                        border=ft.border.all(1, BORDER_LIGHT),
                        border_radius=12,
                        padding=12,
                        content=grid_content,
                    ),
                ],
            ),
        )
        open_dialog(dlg)

    def is_repeatable(card: dict) -> bool:
        return bool(card.get("repeatable", False))

    def resolve_gate(gate: dict) -> dict:
        if not gate:
            return None
        g = dict(gate)

        if g.get("kind") == "MARKS_OF_GRACE":
            mn = int(g.get("min", 1))
            mx = int(g.get("max", mn))
            if mx < mn:
                mx = mn
            g["amount"] = mn + secrets.randbelow(mx - mn + 1)

        return g

    def draw_pack_options(eligible: list[dict], draw_n: int) -> list[dict]:
        pool = eligible[:]
        options = []

        def remove_from_pool(picked_id: str):
            nonlocal pool
            pool = [x for x in pool if x["id"] != picked_id]

        # If drawing 3 and have non-quests, force at least 1 non-quest
        if draw_n == 3:
            nonquests = [c for c in pool if c.get("type") != "QUEST"]
            if nonquests:
                first = weighted_pick(nonquests)
                options.append(first)
                remove_from_pool(first["id"])

        while len(options) < draw_n and pool:
            quest_count = sum(1 for o in options if o.get("type") == "QUEST")
            remaining = draw_n - len(options)

            nonquests_left = [c for c in pool if c.get("type") != "QUEST"]

            # If last slot would make 3 quests and we have non-quests, force non-quest
            if draw_n == 3 and remaining == 1 and quest_count >= 2 and nonquests_left:
                pick = weighted_pick(nonquests_left)
            else:
                pick = weighted_pick(pool)
                if draw_n == 3 and pick.get("type") == "QUEST" and quest_count >= 2 and nonquests_left:
                    pick = weighted_pick(nonquests_left)

            options.append(pick)
            remove_from_pool(pick["id"])

        return options

    # ---------- Quest log ----------
    quest_filter = {"mode": "ALL"}  # ALL | ACTIVE | COMPLETE | INCOMPLETE

    def all_quests():
        qs = [c for c in all_cards if c.get("type") == "QUEST"]
        qs.sort(key=lambda x: x.get("title", "").lower())
        return qs

    def quest_status(qid: str) -> str:
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

    def open_quests_window(_):
        dlg = ft.AlertDialog(modal=True)
        list_view = ft.ListView(expand=True, spacing=2, padding=10)

        header_title = ft.Text("Quest List", size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)
        header_stats = ft.Text("", color=TEXT_DIM)

        def rebuild():
            qs = all_quests()
            completed_ids = set(state.get("completedCardIds", []))

            completed_count = sum(1 for q in qs if q["id"] in completed_ids)
            header_stats.value = f"Completed: {completed_count}/{len(qs)}"

            list_view.controls.clear()

            for q in qs:
                qid = q["id"]
                status = quest_status(qid)

                mode = quest_filter["mode"]
                if mode == "COMPLETE" and status != "COMPLETE":
                    continue
                if mode == "ACTIVE" and status != "ACTIVE":
                    continue
                if mode == "INCOMPLETE" and status == "COMPLETE":
                    continue

                meta = q.get("meta", {}) or {}
                meta_bits = []
                if meta.get("difficulty"):
                    meta_bits.append(str(meta["difficulty"]))
                if isinstance(meta.get("questPoints"), int) and meta["questPoints"] > 0:
                    meta_bits.append(f'{meta["questPoints"]} QP')
                if meta.get("members") is True:
                    meta_bits.append("Members")
                meta_line = " • ".join(meta_bits)

                list_view.controls.append(
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        border_radius=8,
                        bgcolor="#15110d",
                        border=ft.border.all(1, BORDER_LIGHT),
                        content=ft.Column(
                            spacing=1,
                            controls=[
                                ft.Text(q.get("title", qid), color=quest_color(status), size=16, weight=ft.FontWeight.BOLD),
                                ft.Text(meta_line, color=TEXT_DIM, size=11) if meta_line else ft.Container(height=0),
                            ],
                        ),
                    )
                )

            page.update()

        def set_filter(mode: str):
            quest_filter["mode"] = mode
            rebuild()

        filters_row = ft.Row(
            spacing=10,
            controls=[
                osrs_button("All", lambda e: set_filter("ALL")),
                osrs_button("Active", lambda e: set_filter("ACTIVE")),
                osrs_button("Completed", lambda e: set_filter("COMPLETE")),
                osrs_button("Incomplete", lambda e: set_filter("INCOMPLETE")),
            ],
        )

        rebuild()

        dlg.content = ft.Container(
            width=520,
            height=540,
            bgcolor=PANEL_BG,
            border=ft.border.all(1, BORDER_DARK),
            border_radius=14,
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(spacing=2, controls=[header_title, header_stats]),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text("X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                            ),
                        ],
                    ),
                    filters_row,
                    ft.Container(
                        expand=True,
                        bgcolor=PANEL_INNER,
                        border=ft.border.all(1, BORDER_LIGHT),
                        border_radius=12,
                        content=list_view,
                    ),
                ],
            ),
        )

        open_dialog(dlg)

    # ---------- Notes dialog ----------
    def open_notes_window(_):
        dlg = ft.AlertDialog(modal=True)
        dlg.content = ft.Container(
            width=520,
            bgcolor=PANEL_BG,
            border=ft.border.all(1, BORDER_DARK),
            border_radius=14,
            padding=12,
            content=ft.Column(
                tight=True,
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("Notes", size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text("X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                            ),
                        ],
                    ),
                    ft.Container(
                        bgcolor=PANEL_INNER,
                        border=ft.border.all(1, BORDER_LIGHT),
                        border_radius=12,
                        padding=12,
                        content=ft.Text(NOTES_TEXT, color=TEXT_DIM),
                    ),
                ],
            ),
        )
        open_dialog(dlg)

    def complete_current_card(_):
        cid = state.get("activeCardId")
        if not cid:
            snack("No active card.")
            return
        card = cards_by_id.get(cid, {"id": cid, "type": "?"})
        log_completed(card)
        complete_active_card(state, repeatable=is_repeatable(card))
        save()
        refresh()
        snack("Completed!")

    def open_slayer_masters_window(_):
        dlg = ft.AlertDialog(modal=True)
        list_view = ft.ListView(expand=True, spacing=10, padding=8)

        def rebuild():
            list_view.controls.clear()
            for mm in config.get("slayerMasters", []):
                portrait = mm.get("portrait")
                mid = mm["id"]
                name = mm["name"]

                st = state["slayerMasters"].get(
                    mid, {"tasks": 0, "packsFound": 0, "maxPacks": int(mm["maxPacks"])}
                )
                tasks = int(st.get("tasks", 0))
                found = int(st.get("packsFound", 0))
                maxp = int(st.get("maxPacks", mm["maxPacks"]))

                # ✅ ADD THIS BLOCK HERE (before `row = ...`)
                if portrait and os.path.exists(os.path.join(ASSETS_DIR, portrait.replace("/", os.sep))):
                    img = ft.Image(src=portrait, width=44, height=44, fit=ft.ImageFit.CONTAIN)
                else:
                    img = ft.Container(
                        width=44,
                        height=44,
                        alignment=ft.alignment.center,
                        bgcolor="#1a1510",
                        border=ft.border.all(1, BORDER_LIGHT),
                        border_radius=8,
                        content=ft.Text(name[:1], color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                    )

                row = ft.Container(
                    padding=12,
                    border_radius=12,
                    bgcolor="#1a1510",
                    border=ft.border.all(1, BORDER_LIGHT),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            # ✅ CHANGE THIS LEFT SIDE to include the portrait + text
                            ft.Row(
                                spacing=12,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    img,
                                    ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text(name, size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                                            ft.Text(f"Lifetime Tasks: {tasks}", color=TEXT_DIM),
                                            ft.Text(f"Packs Found: {found}/{maxp}", color=ACCENT),
                                        ],
                                    ),
                                ],
                            ),
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=14, vertical=10),
                                border_radius=10,
                                bgcolor="#2b241a",
                                border=ft.border.all(1, BORDER_LIGHT),
                                on_click=lambda e, x=mid: (complete_task_for_master(x), rebuild()),
                                content=ft.Text("Complete Task", color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                            ),
                        ],
                    ),
                )
                list_view.controls.append(row)
            page.update()

        rebuild()

        dlg.content = ft.Container(
            width=520,
            height=540,
            bgcolor=PANEL_BG,
            border=ft.border.all(1, BORDER_DARK),
            border_radius=14,
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("Slayer Masters", size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text("X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                            ),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        bgcolor=PANEL_INNER,
                        border=ft.border.all(1, BORDER_LIGHT),
                        border_radius=12,
                        content=list_view,
                    ),
                ],
            ),
        )
        open_dialog(dlg)

    top_bar = ft.Container(
        height=64,
        padding=ft.padding.symmetric(horizontal=14, vertical=10),
        bgcolor="#15110d",
        border=ft.border.all(1, BORDER_LIGHT),
        border_radius=12,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("RuneCards", size=22, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=10, vertical=8),
                            border_radius=10,
                            border=ft.border.all(1, BORDER_LIGHT),
                            bgcolor="#1a1510",
                            content=ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Image(src="ui/PackIco.png", width=22, height=22),
                                    ft.Text("Packs", color=TEXT_DIM),
                                    top_packs,
                                ],
                            ),
                        ),
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=10, vertical=8),
                            border_radius=10,
                            border=ft.border.all(1, BORDER_LIGHT),
                            bgcolor="#1a1510",
                            content=ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Text("Packs Opened", color=TEXT_DIM),
                                    top_opened,
                                ],
                            ),
                        ),
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=10, vertical=8),
                            border_radius=10,
                            border=ft.border.all(1, BORDER_LIGHT),
                            bgcolor="#1a1510",
                            content=ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Text("Tasks completed", color=TEXT_DIM),
                                    top_tasks,
                                ],
                            ),
                        ),
                        icon_button("ui/log.png", open_task_log_window, tooltip="Task Log", size=22),
                        icon_button("ui/skills.png", open_skills_window, tooltip="Skills", size=22),
                        icon_button("ui/quests.png", open_quests_window, tooltip="Quests", size=22),
                        icon_button("ui/notes.png", open_notes_window, tooltip="Notes", size=22),
                    ],
                ),
            ],
        ),
    )

    left_panel = panel(
        ft.Column(
            spacing=10,
            controls=[
                ft.Text("Quick actions", size=16, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),

                action_tile(
                    "Open pack",
                    "Pick 1 of 3 cards",
                    open_pack,
                    badge=stat_pill("Packs", left_packs),
                    icon_src="ui/PackIco.png",
                    emoji_fallback="🎴",
                    primary=True,
                ),

                action_tile(
                    "Slayer Masters",
                    "Log a task (rolls for a pack)",
                    open_slayer_masters_window,
                    badge=stat_pill("Tasks", left_tasks),
                    icon_src="ui/slayer.png",
                    emoji_fallback="⚔",
                ),

                ft.Container(height=6),
                ft.Text(f"Save: {SAVE_PATH}", size=11, color=TEXT_DIM),
            ],
        )
    )

    right_panel = panel(
    ft.Column(
        expand=True,
        spacing=14,
        controls=[
            pack_title,
            pack_hint,
            pack_empty,
            pack_options_row,

            # ✅ centered and bigger
            complete_btn_section,
        ],
    )
)


    page.add(
        ft.Container(
            padding=18,
            content=ft.Column(
                expand=True,
                spacing=12,
                controls=[
                    top_bar,
                    ft.Row(
                        expand=True,
                        spacing=14,
                        controls=[
                            ft.Container(width=360, content=left_panel),
                            ft.Container(expand=True, content=right_panel),
                        ],
                    ),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[status_box],
                    ),
                ],
            ),
        )
    )

    refresh()
    render_pack_from_state()


if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
