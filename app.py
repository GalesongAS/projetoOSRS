import json
import os
import secrets
import flet as ft

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
        m["id"]: {"tasks": 0, "packsFound": 0, "maxPacks": int(m["maxPacks"])}
        for m in config.get("slayerMasters", [])
    }

    return {
        "version": 3,
        "unopenedPacks": 0,
        "packsOpened": 0,

        "skillCaps": caps,
        "reachedLevels": {},

        "activeCardId": None,
        "activeGate": None,
        "obtainedCardIds": [],
        "completedCardIds": [],

        "slayerMasters": masters,
    }


def migrate_save(state: dict, config: dict) -> dict:
    if "unopenedPacks" not in state:
        state["unopenedPacks"] = 0
    if "packsOpened" not in state:
        state["packsOpened"] = 0
    if "skillCaps" not in state:
        state["skillCaps"] = {}
    if "reachedLevels" not in state:
        state["reachedLevels"] = {}
    if "activeCardId" not in state:
        state["activeCardId"] = None
    if "activeGate" not in state:
        state["activeGate"] = None
    if "obtainedCardIds" not in state:
        state["obtainedCardIds"] = []
    if "completedCardIds" not in state:
        state["completedCardIds"] = []

    # Merge new skills from config
    defaults = config.get("startingCaps", {})
    for skill, cap in defaults.items():
        if skill not in state["skillCaps"]:
            state["skillCaps"][skill] = cap

    # Merge slayer masters from config
    if "slayerMasters" not in state:
        state["slayerMasters"] = {}

    for m in config.get("slayerMasters", []):
        mid = m["id"]
        if mid not in state["slayerMasters"]:
            state["slayerMasters"][mid] = {"tasks": 0, "packsFound": 0, "maxPacks": int(m["maxPacks"])}
        else:
            state["slayerMasters"][mid]["maxPacks"] = int(m["maxPacks"])

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


def complete_active_card(state):
    cid = state.get("activeCardId")
    if not cid:
        return False
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
        tooltip=tooltip or None,     # <-- this is the key line
        on_click=on_click,
        content=ft.Image(src=img_src, width=size, height=size, fit=ft.ImageFit.CONTAIN),
    )



def main(page: ft.Page):
    # Font (must be inside assets/fonts/)
    page.fonts = {"OSRS": "fonts/RunescapeChat.ttf"}
    page.theme = ft.Theme(font_family="OSRS")

    page.title = "RuneCards"
    page.bgcolor = OSRS_BG
    page.window_width = 1200
    page.window_height = 760

    config = read_json(CONFIG_PATH)

    # cards + quests as one pool
    all_cards = read_json(CARDS_PATH)
    if os.path.exists(QUESTS_PATH):
        all_cards.extend(read_json(QUESTS_PATH))
    cards_by_id = {c["id"]: c for c in all_cards}

    if os.path.exists(SAVE_PATH):
        state = migrate_save(read_json(SAVE_PATH), config)
    else:
        state = default_save(config)
    write_json(SAVE_PATH, state)

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

    # ---------- Derived stats ----------
    def total_slayer_tasks():
        return sum(int(v.get("tasks", 0)) for v in state.get("slayerMasters", {}).values())

    def config_master_name(master_id: str) -> str:
        for mm in config.get("slayerMasters", []):
            if mm["id"] == master_id:
                return mm.get("name", master_id)
        return master_id

    # ---------- Top bar texts ----------
    top_packs = ft.Text(color=TEXT_MAIN, weight=ft.FontWeight.BOLD)
    top_tasks = ft.Text(color=TEXT_MAIN, weight=ft.FontWeight.BOLD)
    top_opened = ft.Text(color=TEXT_MAIN, weight=ft.FontWeight.BOLD)

    # ---------- Center "current task" texts ----------
    active_title = ft.Text(size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)
    active_desc = ft.Text(color=TEXT_DIM)
    gate_line = ft.Text(color=ACCENT)

    def why_cant_open_pack() -> str | None:
        if state["unopenedPacks"] <= 0:
            return "No packs available."
        if state.get("activeCardId"):
            return "You already have an active card."
        if state.get("activeGate") and not gate_satisfied(state):
            g = state["activeGate"]
            return f"Blocked by gate: reach {g.get('skill')} {g.get('level')}."
        return None

    def refresh():
        top_packs.value = str(state["unopenedPacks"])
        top_tasks.value = str(total_slayer_tasks())
        top_opened.value = str(int(state.get("packsOpened", 0)))

        cid = state.get("activeCardId")
        if cid:
            c = cards_by_id.get(cid, {"title": cid, "type": "?"})
            active_title.value = f"{c.get('title')} [{c.get('type')}]"
            active_desc.value = c.get("description", "")
        else:
            active_title.value = "No active card"
            active_desc.value = "Open a pack and pick 1 of 3."

        if state.get("activeGate"):
            g = state["activeGate"]
            gate_line.value = f"Gate: reach {g.get('skill')} {g.get('level')} to clear this card."
        else:
            gate_line.value = ""

        page.update()

    # ---------- Skills window ----------
    def asset_exists(rel_path: str) -> bool:
        return os.path.exists(os.path.join(ASSETS_DIR, rel_path.replace("/", os.sep)))

    def tracked_skills():
        items = []
        for skill, cap in state["skillCaps"].items():
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
            ft.Image(src=icon_rel, width=34, height=34, fit=ft.ImageFit.CONTAIN, opacity=1.0 if cap > 1 else 0.35)
            if has_icon
            else ft.Text(skill[:2].upper(), color=TEXT_MAIN, opacity=1.0 if cap > 1 else 0.35, weight=ft.FontWeight.BOLD)
        )

        lock_rel = "ui/lock.png"
        lock_control = (
            ft.Image(src=lock_rel, width=22, height=22, opacity=0.95) if asset_exists(lock_rel)
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
            grid = ft.GridView(expand=True, max_extent=90, child_aspect_ratio=1.35, spacing=8, run_spacing=8)
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

    # ---------- Pack opening ----------
    def open_pack(_):
        reason = why_cant_open_pack()
        if reason:
            snack(reason)
            return

        obtained = set(state["obtainedCardIds"])
        completed = set(state["completedCardIds"])

        eligible = []
        for c in all_cards:
            if c["id"] in obtained or c["id"] in completed:
                continue
            if not check_requires(state, c):
                continue
            eligible.append(c)

        if not eligible:
            snack("No eligible cards left.")
            return

        options = []
        pool = eligible[:]
        draw_n = min(int(config.get("cardsPerPack", 3)), len(pool))
        for _i in range(draw_n):
            pick = weighted_pick(pool)
            options.append(pick)
            pool = [x for x in pool if x["id"] != pick["id"]]

        dlg = ft.AlertDialog(modal=True)

        def pick_card(card):
            state["unopenedPacks"] -= 1
            state["packsOpened"] = int(state.get("packsOpened", 0)) + 1
            state["activeCardId"] = card["id"]
            state["obtainedCardIds"].append(card["id"])

            if card.get("type") == "UNLOCK":
                apply_unlock_effects(state, card)
                if card.get("gate"):
                    state["activeGate"] = card["gate"]
                else:
                    complete_active_card(state)

            save()
            refresh()
            close_dialog(dlg)
            snack("Card selected!")

        def card_view(c):
            return ft.Container(
                width=300,
                padding=14,
                border_radius=12,
                bgcolor="#2b241a",
                border=ft.border.all(1, BORDER_LIGHT),
                on_click=lambda e, card=c: pick_card(card),
                content=ft.Column(
                    spacing=8,
                    controls=[
                        ft.Text(c["title"], size=16, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                        ft.Text(f"[{c['type']}]", color=ACCENT),
                        ft.Text(c.get("description", ""), color=TEXT_DIM),
                        ft.Text("Click to choose", size=12, color=TEXT_DIM),
                    ],
                ),
            )

        dlg.content = ft.Container(
            bgcolor=PANEL_BG,
            border=ft.border.all(1, BORDER_DARK),
            border_radius=14,
            padding=14,
            width=1000,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Text("Pack opening — pick 1 of 3", size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                    ft.Row(controls=[card_view(x) for x in options], wrap=True, spacing=12, run_spacing=12),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.Container(
                                padding=10,
                                border_radius=10,
                                border=ft.border.all(1, BORDER_LIGHT),
                                bgcolor="#1f1a13",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text("Close", color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
                            )
                        ],
                    ),
                ],
            ),
        )
        open_dialog(dlg)

    # ---------- Slayer masters ----------
    def complete_task_for_master(master_id: str):
        masters = state["slayerMasters"]
        m = masters[master_id]
        m["tasks"] = int(m.get("tasks", 0)) + 1

        chance = float(config["packChancePerSlayerTask"])
        can_still_drop = int(m.get("packsFound", 0)) < int(m.get("maxPacks", 0))

        if can_still_drop and secrets.randbelow(10_000) < int(chance * 10_000):
            state["unopenedPacks"] += 1
            m["packsFound"] = int(m.get("packsFound", 0)) + 1
            save()
            refresh()
            snack(f"{config_master_name(master_id)} task complete → pack found!")
        else:
            save()
            refresh()
            if not can_still_drop:
                snack(f"{config_master_name(master_id)} task complete → no packs left for this master.")
            else:
                snack(f"{config_master_name(master_id)} task complete → no pack this time.")

    def open_slayer_masters_window(_):
        dlg = ft.AlertDialog(modal=True)
        list_view = ft.ListView(expand=True, spacing=10, padding=8)

        def rebuild():
            list_view.controls.clear()

            for mm in config.get("slayerMasters", []):
                mid = mm["id"]
                name = mm["name"]
                portrait = mm.get("portrait")

                st = state["slayerMasters"].get(mid, {"tasks": 0, "packsFound": 0, "maxPacks": int(mm["maxPacks"])})
                tasks = int(st.get("tasks", 0))
                found = int(st.get("packsFound", 0))
                maxp = int(st.get("maxPacks", mm["maxPacks"]))

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
                            ft.Row(
                                spacing=12,
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

    # ---------- One-button completion (handles gates) ----------
    def complete_current_card(_):
        cid = state.get("activeCardId")
        if not cid:
            snack("No active card.")
            return

        # If there's a gate and it's not satisfied, ask the confirmation popup
        if state.get("activeGate") and not gate_satisfied(state):
            g = state["activeGate"]
            if g.get("kind") == "REACH_LEVEL":
                skill = g["skill"]
                lvl = int(g["level"])

                confirm = ft.AlertDialog(modal=True)

                def yes(_e):
                    state["reachedLevels"][skill] = lvl
                    # gate_satisfied will now be true, so we complete the card
                    if gate_satisfied(state):
                        complete_active_card(state)
                    save()
                    refresh()
                    close_dialog(confirm)
                    snack(f"Confirmed: reached {skill} {lvl}. Completed!")

                confirm.content = panel(
                    ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[
                            ft.Text("Confirm completion", size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                            ft.Text(f"Did you reach {skill} level {lvl} in-game?", color=TEXT_DIM),
                            ft.Row(
                                spacing=10,
                                controls=[
                                    osrs_button("No", lambda e: close_dialog(confirm)),
                                    osrs_button("Yes", yes, primary=True),
                                ],
                            ),
                        ],
                    ),
                    padding=14,
                )
                open_dialog(confirm)
                return

            snack("Unsupported gate type.")
            return

        # No gate (or already satisfied) -> complete immediately
        complete_active_card(state)
        save()
        refresh()
        snack("Completed!")

    # ---------- Top bar ----------
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
                                    ft.Text("Tasks", color=TEXT_DIM),
                                    top_tasks,
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
                                    ft.Text("Opened", color=TEXT_DIM),
                                    top_opened,
                                ],
                            ),
                        ),
                        icon_button("ui/skills.png", open_skills_window, tooltip="Skills", size=22),
                        icon_button("ui/quests.png", open_quests_window, tooltip="Quests", size=22),
                        icon_button("ui/notes.png", open_notes_window, tooltip="Notes", size=22),
                    ],
                ),
            ],
        ),
    )

    # ---------- Layout ----------
    left_panel = panel(
        ft.Column(
            spacing=12,
            controls=[
                ft.Text("Actions", size=16, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                osrs_button("Open pack", open_pack, primary=True),
                ft.Divider(color=BORDER_LIGHT),
                ft.Text("Slayer", size=16, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                osrs_button("Slayer Masters", open_slayer_masters_window, primary=True),
                ft.Divider(color=BORDER_LIGHT),
                ft.Text(f"Save: {SAVE_PATH}", size=11, color=TEXT_DIM),
            ],
        )
    )

    center_panel = panel(
        ft.Column(
            expand=True,
            spacing=10,
            controls=[
                ft.Text("Current card", size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN),
                active_title,
                active_desc,
                gate_line,
                ft.Row(
                    spacing=10,
                    controls=[
                        osrs_button("Completed", complete_current_card, primary=True),
                    ],
                ),
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
                            ft.Container(expand=True, content=center_panel),
                        ],
                    ),
                ],
            ),
        )
    )

    refresh()


if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
