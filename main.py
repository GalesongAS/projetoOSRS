import secrets
import os
import flet as ft
from datetime import datetime
import traceback

from app_constants import (
    ACCENT,
    ALIGN_BOTTOM_LEFT,
    ALIGN_CENTER,
    ALIGN_TOP_RIGHT,
    ASSETS_DIR,
    BORDER_DARK,
    BORDER_LIGHT,
    CARDS_PATH,
    CLOUD_CFG_PATH,
    CLOUD_TABLE,
    CONFIG_PATH,
    NOTES_TEXT as APP_NOTES_TEXT,
    OSRS_BG,
    PANEL_BG,
    PANEL_INNER,
    QUEST_GREEN,
    QUEST_RED,
    QUESTS_PATH,
    QUEST_YELLOW,
    SAVE_DIR,
    SAVE_PATH,
    SLAYER_CHANCE_CAP,
    SLAYER_CURVE,
    SLAYER_END_MULT,
    SLAYER_PITY_CAP,
    SLAYER_PITY_PER_TASK,
    SLAYER_START_MULT,
    TEXT_DIM,
    TEXT_MAIN,
)
from app_storage import default_save, migrate_save, read_json, write_json
from cloud_store import CloudStore
from game_logic import (
    apply_unlock_effects,
    check_requires,
    complete_active_card,
    draw_pack_options,
    fmt_pct,
    gate_amount_text,
    gate_range_text,
    gate_satisfied,
    is_repeatable,
    quest_color,
    quest_status,
    resolve_gate,
    slayer_pack_chance_for,
    tracked_skills,
    validate_cards,
    weighted_pick,
)
from ui_components import action_tile, icon_button, osrs_button, panel, stat_pill


NOTES_TEXT = (
    "• Packs stack.\n"
    "• You can only have 1 active card.\n"
    "• Slayer Masters have finite pack pools."
)


# ---------- IO ----------
NOTES_TEXT = APP_NOTES_TEXT


# ---------- Card logic ----------
def _legacy_action_tile(
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
    fallback_text = emoji_fallback if emoji_fallback.isascii() else title[:4]

    icon_ok = False
    if icon_src:
        icon_ok = os.path.exists(
            os.path.join(ASSETS_DIR, icon_src.replace("/", os.sep))
        )

    icon_control = (
        ft.Image(src=icon_src, width=24, height=24, fit=ft.BoxFit.CONTAIN)
        if icon_ok
        else ft.Text(fallback_text, size=18, color=TEXT_MAIN)
    )

    return ft.Container(
        padding=12,
        border_radius=12,
        bgcolor=bg,
        border=ft.Border.all(1, BORDER_LIGHT),
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
                            border=ft.Border.all(1, BORDER_LIGHT),
                            alignment=ALIGN_CENTER,
                            content=icon_control,
                        ),
                        ft.Column(
                            spacing=1,
                            controls=[
                                ft.Text(
                                    title,
                                    size=14,
                                    color=TEXT_MAIN,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(subtitle, color=TEXT_DIM, size=11),
                            ],
                        ),
                    ],
                ),
                badge if badge else ft.Container(width=0, height=0),
            ],
        ),
    )


def _legacy_fmt_pct(p: float) -> str:
    return f"{p * 100:.1f}%"


def main(page: ft.Page):

    selected_pack_id = None

    config = read_json(CONFIG_PATH)
    all_cards = read_json(CARDS_PATH)
    all_quest_cards = read_json(QUESTS_PATH)
    page.fonts = {"OSRS": "fonts/RunescapeChat.ttf"}
    page.theme = ft.Theme(font_family="OSRS")
    cards_by_id = {c["id"]: c for c in all_cards if isinstance(c, dict) and "id" in c}
    for c in all_quest_cards:
        if isinstance(c, dict) and "id" in c:
            cards_by_id[c["id"]] = c

    page.title = "RuneCards"
    page.bgcolor = OSRS_BG

    platform = (os.getenv("FLET_PLATFORM") or "").lower()
    if platform in ("windows", "macos", "linux"):
        page.window_width = 1300
        page.window_height = 900

    cloud_cfg = read_json(CLOUD_CFG_PATH) if os.path.exists(CLOUD_CFG_PATH) else {}
    if not isinstance(cloud_cfg, dict):
        cloud_cfg = {}

    cloud_cfg.setdefault("mode", "local")  # "local" | "cloud"
    cloud_cfg.setdefault("url", "")
    cloud_cfg.setdefault("anon_key", "")
    cloud_cfg.setdefault("slot", "default")

    def save_cloud_cfg():
        write_json(CLOUD_CFG_PATH, cloud_cfg)

    def cloud_on() -> bool:
        return (
            cloud_cfg.get("mode") == "cloud"
            and bool(cloud_cfg["url"].strip())
            and bool(cloud_cfg["anon_key"].strip())
        )

    def cloud_ready() -> bool:
        return bool(cloud and cloud.enabled())

    cloud = None
    if cloud_on():
        cloud = CloudStore(
            url=cloud_cfg["url"],
            anon_key=cloud_cfg["anon_key"],
            table=CLOUD_TABLE,
            storage_dir=SAVE_DIR,
        )

    def cloud_slot():
        return (cloud_cfg.get("slot") or "default").strip()

    def open_cloud_window(_=None):
        dlg = ft.AlertDialog(modal=True)

        mode_switch = ft.Switch(
            label="Enable cloud saves (Supabase)",
            value=(cloud_cfg.get("mode") == "cloud"),
        )
        url_tf = ft.TextField(
            label="Supabase URL", value=cloud_cfg.get("url", ""), dense=True
        )
        key_tf = ft.TextField(
            label="Supabase anon key",
            value=cloud_cfg.get("anon_key", ""),
            dense=True,
            password=True,
            can_reveal_password=True,
        )

        def save_settings(_e=None):
            cloud_cfg["mode"] = "cloud" if mode_switch.value else "local"
            cloud_cfg["url"] = (url_tf.value or "").strip()
            cloud_cfg["anon_key"] = (key_tf.value or "").strip()
            save_cloud_cfg()

            # rebuild cloud object
            nonlocal cloud
            cloud = None
            if cloud_on():
                cloud = CloudStore(
                    url=cloud_cfg["url"],
                    anon_key=cloud_cfg["anon_key"],
                    table=CLOUD_TABLE,
                    storage_dir=SAVE_DIR,
                )

            if cloud_cfg["mode"] == "cloud" and not cloud_ready():
                snack("Cloud settings saved, but Supabase support is unavailable.")
            else:
                snack("Cloud settings saved.")

        def do_pull(_e=None):
            save_settings()
            if not cloud_ready():
                snack("Cloud is disabled, misconfigured, or unavailable.")
                return

            pulled = cloud.pull(cloud_slot())
            if isinstance(pulled, dict):
                state.clear()
                state.update(migrate_save(pulled, config))
                write_json(SAVE_PATH, state)
                refresh()
                render_pack_from_state()
                snack("Pulled ✅")
            else:
                snack("No cloud save found for this slot.")

        def do_push(_e=None):
            save_settings()
            if not cloud_ready():
                snack("Cloud is disabled, misconfigured, or unavailable.")
                return
            ok = cloud.push(cloud_slot(), cloud_slot(), state, cloud_meta())
            snack("Pushed ✅" if ok else "Push failed ❌")

        dlg.content = ft.Container(
            width=560,
            bgcolor=PANEL_BG,
            border=ft.Border.all(1, BORDER_DARK),
            border_radius=14,
            padding=12,
            content=ft.Column(
                tight=True,
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                "Cloud Saves",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXT_MAIN,
                            ),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.Border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text(
                                    "X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD
                                ),
                            ),
                        ],
                    ),
                    ft.Container(
                        bgcolor=PANEL_INNER,
                        border=ft.Border.all(1, BORDER_LIGHT),
                        border_radius=12,
                        padding=12,
                        content=ft.Column(
                            tight=True,
                            spacing=10,
                            controls=[
                                mode_switch,
                                url_tf,
                                key_tf,
                                ft.Row(
                                    spacing=10,
                                    controls=[
                                        osrs_button(
                                            "Save settings", save_settings, primary=True
                                        ),
                                        osrs_button(
                                            "Choose save", open_save_picker_window
                                        ),
                                        osrs_button("Pull", do_pull),
                                        osrs_button("Push", do_push),
                                    ],
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

        open_dialog(dlg)

    def open_save_picker_window(_=None):
        dlg = ft.AlertDialog(modal=True)
        list_view = ft.ListView(expand=True, spacing=8, padding=8)

        current_slot_txt = ft.Text("", color=TEXT_DIM, size=11)

        new_name_tf = ft.TextField(
            label="New save name (slot)",
            dense=True,
            value="main" if not cloud_cfg.get("slot") else "",
        )

        def refresh_list():
            rows = cloud_list_saves()
            list_view.controls.clear()

            current_slot_txt.value = (
                f"Current slot: {cloud_slot()}"
                if (cloud_cfg.get("slot") or "").strip()
                else "Current slot: (none selected)"
            )

            if not rows:
                list_view.controls.append(
                    ft.Text(
                        "No cloud saves found for this account yet.", color=TEXT_DIM
                    )
                )
                page.update()
                return

            for r in rows:
                uid = str(r.get("user_id") or "")
                slot = str(r.get("slot") or "default")
                name = str(r.get("name") or slot)
                updated = str(r.get("updated_at") or "")

                data = r.get("data") or {}
                packs_opened = int(data.get("packsOpened", 0))
                slayer_tasks = int(
                    sum(
                        int(v.get("tasks", 0))
                        for v in (data.get("slayerMasters") or {}).values()
                    )
                )
                last_task = ""
                tl = data.get("taskLog") or []
                if tl:
                    last_task = str(tl[-1].get("title") or "")

                subtitle = (
                    f"Packs opened: {packs_opened} • Slayer tasks: {slayer_tasks}"
                )
                if last_task:
                    subtitle += f"\nLast task: {last_task}"
                if updated:
                    subtitle += f"\nUpdated: {updated}"

                def pick_slot(e, chosen_slot=slot):
                    cloud_cfg["slot"] = chosen_slot
                    save_cloud_cfg()

                    pulled = cloud.pull(chosen_slot) if cloud_ready() else None
                    if isinstance(pulled, dict):
                        state.clear()
                        state.update(migrate_save(pulled, config))
                        write_json(SAVE_PATH, state)
                        refresh()
                        render_pack_from_state()
                        snack("Selected save loaded (this device is now linked to it).")
                    else:
                        snack("Selected save has no data.")

                    close_dialog(dlg)

                list_view.controls.append(
                    ft.Container(
                        padding=12,
                        border_radius=12,
                        bgcolor="#15110d",
                        border=ft.Border.all(1, BORDER_LIGHT),
                        on_click=pick_slot,
                        content=ft.Column(
                            spacing=4,
                            controls=[
                                ft.Text(
                                    name,
                                    color=TEXT_MAIN,
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(subtitle, color=TEXT_DIM, size=11),
                                ft.Text(f"slot: {slot}", color=ACCENT, size=11),
                                ft.Text(
                                    f"user_id: {uid[:8]}…", color=TEXT_DIM, size=10
                                ),
                            ],
                        ),
                    )
                )

            page.update()

        def create_new_save(_e=None):
            name = (new_name_tf.value or "").strip()
            if not name:
                snack("Enter a save name.")
                return

            cloud_cfg["slot"] = name
            save_cloud_cfg()

            ok = cloud.push(name, name, state, cloud_meta()) if cloud_ready() else False
            snack("New save created." if ok else "Failed to create save.")
            refresh_list()

        dlg.content = ft.Container(
            width=620,
            height=620,
            bgcolor=PANEL_BG,
            border=ft.Border.all(1, BORDER_DARK),
            border_radius=14,
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                "Choose Cloud Save",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXT_MAIN,
                            ),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.Border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text(
                                    "X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD
                                ),
                            ),
                        ],
                    ),
                    current_slot_txt,
                    ft.Divider(height=1, color=BORDER_LIGHT),
                    ft.Container(
                        bgcolor=PANEL_INNER,
                        border=ft.Border.all(1, BORDER_LIGHT),
                        border_radius=12,
                        expand=True,
                        content=list_view,
                    ),
                    ft.Divider(height=1, color=BORDER_LIGHT),
                    new_name_tf,
                    ft.Row(
                        spacing=10,
                        controls=[
                            osrs_button(
                                "Create new save", create_new_save, primary=True
                            ),
                            osrs_button("Refresh list", lambda e: refresh_list()),
                        ],
                    ),
                ],
            ),
        )

        open_dialog(dlg)
        refresh_list()

    def cloud_list_saves():
        if not cloud_ready():
            return []
        return cloud.list_slots()

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

    validate_cards(all_cards)
    if os.path.exists(SAVE_PATH):
        state = migrate_save(read_json(SAVE_PATH), config)
    else:
        state = default_save(config)

    # if a pack was opened but not picked, keep showing the same options after restart
    pending = list(state.get("pendingPackOptionIds") or [])
    if pending:
        if not state.get("lastPackOptionIds"):
            state["lastPackOptionIds"] = pending[:]
        # you haven't picked yet, so force None
        state["lastPackPickedId"] = None

    write_json(SAVE_PATH, state)

    def cloud_meta():
        # keep your existing meta logic if you want
        return {
            "packs_opened": int(state.get("packsOpened", 0)),
            "slayer_tasks": int(
                sum(
                    int(v.get("tasks", 0))
                    for v in state.get("slayerMasters", {}).values()
                )
            ),
            "last_task_title": (
                str((state.get("taskLog") or [{}])[-1].get("title") or "")
                if state.get("taskLog")
                else ""
            ),
        }

    # NEW bootstrap
    if cloud_ready():
        pulled = cloud.pull(cloud_slot())
        if isinstance(pulled, dict):
            state.clear()
            state.update(migrate_save(pulled, config))
            write_json(SAVE_PATH, state)
        else:
            # seed cloud with local
            cloud.push(cloud_slot(), cloud_slot(), state, cloud_meta())

    status_text = ft.Text("", size=12, color=TEXT_DIM)
    status_box = ft.Container(
        visible=False,
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=12,
        bgcolor="#15110d",
        border=ft.Border.all(1, BORDER_LIGHT),
        content=status_text,
    )

    def set_status(msg: str, color: str):
        status_text.value = msg
        status_text.color = color
        status_box.visible = True
        page.update()

    def save():
        write_json(SAVE_PATH, state)
        if cloud_ready():
            cloud.push(cloud_slot(), cloud_slot(), state, cloud_meta())

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
        return sum(
            int(v.get("tasks", 0)) for v in state.get("slayerMasters", {}).values()
        )

    def config_master_name(master_id: str) -> str:
        for mm in config.get("slayerMasters", []):
            if mm["id"] == master_id:
                return mm.get("name", master_id)
        return master_id

    top_packs = ft.Text(color=TEXT_MAIN, size=14, weight=ft.FontWeight.BOLD)
    top_tasks = ft.Text(color=TEXT_MAIN, weight=ft.FontWeight.BOLD)
    top_opened = ft.Text(color=TEXT_MAIN, weight=ft.FontWeight.BOLD)

    show_save_path = False
    save_path_text = ft.Text("", color=TEXT_DIM, size=11)
    save_toggle_text = ft.Text(
        "Show", size=11, color=TEXT_MAIN, weight=ft.FontWeight.BOLD
    )

    def toggle_save_path(_):
        nonlocal show_save_path
        show_save_path = not show_save_path
        refresh()

    def resolve_gate(gate: dict) -> dict:
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
            return f"Requirement: {mn}–{mx} {unit_plural}."

        if kind == "MARKS_OF_GRACE":
            return (
                "Requirement: Collect "
                + fmt_range("Mark of grace", "Marks of grace")[13:]
            )
        if kind == "DIARIES":
            return (
                "Requirement: Complete "
                + fmt_range("achievement diary", "achievement diaries")[13:]
            )
        return ""

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

        chance = end_chance + (start_chance - end_chance) * (
            remaining_ratio**SLAYER_CURVE
        )

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
    pack_title = ft.Text(
        "Pack opening — pick 1 of 3",
        size=18,
        weight=ft.FontWeight.BOLD,
        color=TEXT_MAIN,
    )
    pack_hint = ft.Text(
        "Pick one card. After picking, the other 2 remain (dimmed).",
        color=TEXT_DIM,
        size=11,
    )

    empty_title = ft.Text("", size=22, weight=ft.FontWeight.BOLD, color=TEXT_MAIN)
    empty_desc = ft.Text("", size=13, color=TEXT_DIM)

    pack_empty = ft.Container(
        padding=0,
        content=ft.Column(
            tight=True,
            spacing=6,
            controls=[
                empty_title,
                empty_desc,
            ],
        ),
    )
    pack_empty.visible = True

    pack_options_row = ft.Row(
        spacing=12,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )
    pack_options_row.visible = False

    complete_btn_section = ft.Container(
        alignment=ALIGN_CENTER,
        padding=ft.Padding.only(top=10),
        visible=False,
        content=ft.Container(
            border_radius=14,
            border=ft.Border.all(1, BORDER_LIGHT),
            bgcolor="#3a2f1f",
            padding=ft.Padding.symmetric(horizontal=34, vertical=18),
            on_click=lambda e: complete_current_card(e),
            content=ft.Text(
                "Complete task",
                color=TEXT_MAIN,
                size=16,
                weight=ft.FontWeight.BOLD,
            ),
        ),
    )

    pick_btn_section = ft.Container(
        alignment=ALIGN_CENTER,
        padding=ft.Padding.only(top=10),
        visible=False,
        content=ft.Container(
            border_radius=14,
            border=ft.Border.all(1, BORDER_LIGHT),
            bgcolor="#3a2f1f",
            padding=ft.Padding.symmetric(horizontal=34, vertical=18),
            on_click=lambda e: confirm_pick(e),
            content=ft.Text(
                "Pick task",
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

        save_path_text.value = (
            f"Save: {SAVE_PATH}" if show_save_path else "Save path: (hidden)"
        )
        save_toggle_text.value = "Hide" if show_save_path else "Show"

        has_options = bool(state.get("lastPackOptionIds"))
        has_confirmed_pick = bool(state.get("lastPackPickedId"))
        has_active = bool(state.get("activeCardId"))

        pick_btn_section.visible = (
            has_options
            and (not has_confirmed_pick)
            and (not has_active)
            and (selected_pack_id is not None)
        )

        complete_btn_section.visible = has_active

        page.update()

    def select_card(card: dict):
        nonlocal selected_pack_id
        if state.get("lastPackPickedId"):
            return  # already confirmed
        selected_pack_id = card["id"]
        refresh()
        render_pack_from_state()

    def commit_pick(card: dict):
        nonlocal selected_pack_id

        # lock it in
        state["activeCardId"] = card["id"]
        state["lastPackPickedId"] = card["id"]
        selected_pack_id = card["id"]

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
        snack("Task picked!")

    def confirm_pick(_):
        if state.get("lastPackPickedId"):
            return  # already confirmed
        if not selected_pack_id:
            snack("Select a card first.")
            return
        card = cards_by_id.get(selected_pack_id)
        if not card:
            snack("Selected card missing from data.")
            return
        commit_pick(card)

    def render_pack_from_state():
        if state.get("pendingPackOptionIds") and not state.get("lastPackOptionIds"):
            state["lastPackOptionIds"] = list(state["pendingPackOptionIds"])
            state["lastPackPickedId"] = None
            save()

        ids = list(state.get("lastPackOptionIds") or [])
        picked_id = state.get("lastPackPickedId")

        pack_options_row.controls.clear()

        if not ids:
            pack_options_row.visible = False
            pack_empty.visible = True
            pack_title.value = "No packs yet"
            pack_hint.value = "Select a card, then click Pick task."
            empty_title.value = "No packs yet."
            empty_desc.value = "Go to Slayer Masters and log tasks to roll for packs."

            # Dynamic empty state
            if state.get("activeCardId"):
                c = cards_by_id.get(state["activeCardId"], {"title": "Active task"})
                pack_title.value = "Task in progress"
                pack_hint.value = "Complete your current task to open another pack."
                empty_title.value = c.get("title", "Active task")
                desc = c.get("description", "")
                req = gate_amount_text(state.get("activeGate"))
                empty_desc.value = f"{desc}\n\n{req}" if req else desc
            else:
                pack_title.value = ""
                if state.get("unopenedPacks", 0) > 0:
                    pack_hint.value = ""
                    empty_title.value = "You have packs ready."
                    empty_desc.value = "Open a pack to get new tasks and unlocks."
                else:
                    pack_hint.value = ""
                    empty_title.value = "No packs yet."
                    empty_desc.value = (
                        "Go to Slayer Masters and log tasks to roll for packs."
                    )

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

        pack_title.value = f"Pack opening — pick 1 of {len(options)}"
        pack_hint.value = "Pick one card."

        def make_tile(card: dict) -> ft.Control:
            cid = card.get("id")

            has_confirmed = bool(picked_id)
            is_selected = selected_pack_id == cid
            is_picked = picked_id == cid

            if has_confirmed:
                tile_opacity = 1.0 if is_picked else 0.33
                tile_border = ft.Border.all(
                    2 if is_picked else 1, ACCENT if is_picked else BORDER_LIGHT
                )
                tile_bg = "#3a2f1f" if is_picked else "#2b241a"
                click_handler = None
                badge_text = "PICKED" if is_picked else None
                hint_text = ""
            else:
                tile_opacity = 1.0
                tile_border = ft.Border.all(
                    2 if is_selected else 1, ACCENT if is_selected else BORDER_LIGHT
                )
                tile_bg = "#3a2f1f" if is_selected else "#2b241a"
                click_handler = lambda e, c=card: select_card(c)
                badge_text = "SELECTED" if is_selected else None
                hint_text = "Click to select"

            badge = None
            if badge_text:
                badge = ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    border_radius=999,
                    bgcolor="#1a1510",
                    border=ft.Border.all(1, ACCENT),
                    content=ft.Text(
                        badge_text, color=ACCENT, size=11, weight=ft.FontWeight.BOLD
                    ),
                )

            desc = card.get("description", "") or ""

            if card.get("gate"):
                if has_confirmed and is_picked and state.get("activeCardId") == cid:
                    req = gate_amount_text(state.get("activeGate"))
                else:
                    req = gate_range_text(card.get("gate"))

                if req:
                    desc = f"{desc}\n\n{req}"

            return ft.Container(
                expand=1,
                height=260,
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
                        ft.Text(desc, color=TEXT_DIM),
                        ft.Text(hint_text, size=12, color=TEXT_DIM),
                    ],
                ),
            )

        for c in options:
            pack_options_row.controls.append(make_tile(c))

        page.update()

    def open_pack(_):
        nonlocal selected_pack_id
        if state.get("activeCardId"):
            snack("You already have an active card.")
            return

        pending_ids = list(state.get("pendingPackOptionIds") or [])
        if pending_ids:
            state["lastPackOptionIds"] = pending_ids[:]
            state["lastPackPickedId"] = None
            selected_pack_id = None
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
        for source in (all_cards, all_quest_cards):
            for c in source:
                if (not is_repeatable(c)) and (
                    c["id"] in obtained or c["id"] in completed
                ):
                    continue
                if not check_requires(state, c):
                    continue
                eligible.append(c)

        if not eligible:
            snack("No eligible cards left.")
            return

        draw_n = min(int(config.get("cardsPerPack", 4)), len(eligible))
        options = draw_pack_options(eligible, draw_n)
        option_ids = [c["id"] for c in options]

        state["unopenedPacks"] -= 1
        state["packsOpened"] = int(state.get("packsOpened", 0)) + 1

        state["pendingPackOptionIds"] = option_ids[:]

        state["lastPackOptionIds"] = option_ids[:]
        state["lastPackPickedId"] = None
        selected_pack_id = None

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
                snack(
                    f"{config_master_name(master_id)} task complete → no packs left for this master."
                )
                set_status(
                    f"{config_master_name(master_id)} has no packs left.", TEXT_DIM
                )
            else:
                snack(
                    f"{config_master_name(master_id)} task complete → no pack this time."
                )
                set_status(
                    f"{config_master_name(master_id)} did not give you a pack this time.",
                    QUEST_RED,
                )

    def open_task_log_window(_):
        dlg = ft.AlertDialog(modal=True)
        list_view = ft.ListView(expand=True, spacing=6, padding=10)

        header_stats = ft.Text("", color=TEXT_DIM, size=11)

        def rebuild():
            list_view.controls.clear()
            logs = list(state.get("taskLog", []))

            if not logs:
                header_stats.value = "No entries yet."
                list_view.controls.append(
                    ft.Text("No completed tasks yet.", color=TEXT_DIM)
                )
                page.update()
                return

            # Keep FULL history in save.json,
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
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        border_radius=10,
                        bgcolor="#15110d",
                        border=ft.Border.all(1, BORDER_LIGHT),
                        content=ft.Column(
                            spacing=2,
                            controls=[
                                ft.Text(
                                    title, color=TEXT_MAIN, weight=ft.FontWeight.BOLD
                                ),
                                ft.Text(f"{ts} • {typ}", color=TEXT_DIM, size=11),
                                (
                                    ft.Text(detail, color=ACCENT, size=11)
                                    if detail
                                    else ft.Container(height=0)
                                ),
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
            border=ft.Border.all(1, BORDER_DARK),
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
                                    ft.Text(
                                        "Task Log",
                                        size=18,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXT_MAIN,
                                    ),
                                    header_stats,
                                ],
                            ),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.Border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text(
                                    "X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD
                                ),
                            ),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        bgcolor=PANEL_INNER,
                        border=ft.Border.all(1, BORDER_LIGHT),
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
                fit=ft.BoxFit.CONTAIN,
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
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
            bgcolor="#2a241a",
            border=ft.Border.all(1, BORDER_LIGHT),
            border_radius=6,
            content=ft.Text(
                str(cap), size=12, weight=ft.FontWeight.BOLD, color=TEXT_MAIN
            ),
        )

        return ft.Container(
            width=84,
            height=82,
            border_radius=8,
            bgcolor="#1a1510",
            border=ft.Border.all(1, BORDER_LIGHT),
            content=ft.Stack(
                controls=[
                    ft.Container(expand=True, alignment=ALIGN_CENTER, content=icon),
                    ft.Container(
                        expand=True,
                        alignment=ALIGN_CENTER,
                        content=lock_control,
                        visible=(cap <= 1),
                    ),
                    ft.Container(
                        expand=True,
                        alignment=ALIGN_TOP_RIGHT,
                        padding=6,
                        content=cap_badge,
                        visible=(cap > 1),
                    ),
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
            border=ft.Border.all(1, BORDER_DARK),
            border_radius=14,
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                "Unlocked Skills",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXT_MAIN,
                            ),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.Border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text(
                                    "X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD
                                ),
                            ),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        bgcolor=PANEL_INNER,
                        border=ft.Border.all(1, BORDER_LIGHT),
                        border_radius=12,
                        padding=12,
                        content=grid_content,
                    ),
                    ft.Text(
                        "Top-right number is your unlocked cap for that skill.",
                        color=TEXT_DIM,
                        size=11,
                    ),
                ],
            ),
        )
        open_dialog(dlg)

    def is_repeatable(card: dict) -> bool:
        return bool(card.get("repeatable", False))

    def draw_pack_options(eligible: list[dict], draw_n: int) -> list[dict]:
        pool = eligible[:]
        options: list[dict] = []

        def remove_from_pool(picked_id: str):
            nonlocal pool
            pool = [x for x in pool if x["id"] != picked_id]

        # If any eligible quest exists, guarantee at least one quest in the pack.
        quests = [c for c in pool if c.get("type") == "QUEST"]
        if quests:
            first = weighted_pick(quests)
            options.append(first)
            remove_from_pool(first["id"])

        while len(options) < draw_n and pool:
            pick = weighted_pick(pool)
            options.append(pick)
            remove_from_pool(pick["id"])

        return options

    # ---------- Quest log ----------
    quest_filter = {"mode": "ALL"}  # ALL | ACTIVE | COMPLETE | INCOMPLETE

    def all_quests():
        qs = [c for c in all_quest_cards if c.get("type") == "QUEST"]
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

        header_title = ft.Text(
            "Quest List", size=18, weight=ft.FontWeight.BOLD, color=TEXT_MAIN
        )
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
                difficulty = str(meta.get("difficulty") or "").strip()
                meta_line = difficulty

                list_view.controls.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border_radius=8,
                        bgcolor="#15110d",
                        border=ft.Border.all(1, BORDER_LIGHT),
                        content=ft.Column(
                            spacing=1,
                            controls=[
                                ft.Text(
                                    q.get("title", qid),
                                    color=quest_color(status),
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                (
                                    ft.Text(meta_line, color=TEXT_DIM, size=11)
                                    if meta_line
                                    else ft.Container(height=0)
                                ),
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
                osrs_button("Completed", lambda e: set_filter("COMPLETE")),
                osrs_button("Incomplete", lambda e: set_filter("INCOMPLETE")),
            ],
        )

        rebuild()

        dlg.content = ft.Container(
            width=520,
            height=540,
            bgcolor=PANEL_BG,
            border=ft.Border.all(1, BORDER_DARK),
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
                                border=ft.Border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text(
                                    "X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD
                                ),
                            ),
                        ],
                    ),
                    filters_row,
                    ft.Container(
                        expand=True,
                        bgcolor=PANEL_INNER,
                        border=ft.Border.all(1, BORDER_LIGHT),
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
            border=ft.Border.all(1, BORDER_DARK),
            border_radius=14,
            padding=12,
            content=ft.Column(
                tight=True,
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                "Notes",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXT_MAIN,
                            ),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.Border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text(
                                    "X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD
                                ),
                            ),
                        ],
                    ),
                    ft.Container(
                        bgcolor=PANEL_INNER,
                        border=ft.Border.all(1, BORDER_LIGHT),
                        border_radius=12,
                        padding=12,
                        content=ft.Text(NOTES_TEXT, color=TEXT_DIM),
                    ),
                ],
            ),
        )
        open_dialog(dlg)

    def complete_current_card(_):
        try:
            cid = state.get("activeCardId")
            if not cid:
                msg = "No active card."
                snack(msg)
                set_status(msg, TEXT_DIM)
                return
            if not gate_satisfied(state):
                msg = gate_amount_text(state.get("activeGate")) or "Gate not satisfied."
                snack(msg)
                set_status(msg, TEXT_DIM)
                return

            card = cards_by_id.get(cid, {"id": cid, "type": "?"})
            log_completed(card)
            completed = complete_active_card(state, repeatable=is_repeatable(card))

            if not completed:
                msg = f"Could not complete active card: {cid}"
                print(msg)
                snack("Could not complete task. Check terminal for details.")
                set_status(msg, QUEST_RED)
                return

            save()
            refresh()
            snack("Completed!")
            set_status(
                f"Completed: {card.get('title', cid)}",
                QUEST_GREEN,
            )
        except Exception:
            traceback.print_exc()
            snack("Error while completing task. Check terminal for details.")
            set_status("Task completion failed. See terminal traceback.", QUEST_RED)

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

                can_still_drop = found < maxp
                chance = slayer_pack_chance_for(st) if can_still_drop else 0.0
                chance_text = fmt_pct(chance)

                if portrait and os.path.exists(
                    os.path.join(ASSETS_DIR, portrait.replace("/", os.sep))
                ):
                    img = ft.Image(
                        src=portrait, width=44, height=44, fit=ft.BoxFit.CONTAIN
                    )
                else:
                    img = ft.Container(
                        width=44,
                        height=44,
                        alignment=ALIGN_CENTER,
                        bgcolor="#1a1510",
                        border=ft.Border.all(1, BORDER_LIGHT),
                        border_radius=8,
                        content=ft.Text(
                            name[:1], color=TEXT_MAIN, weight=ft.FontWeight.BOLD
                        ),
                    )

                chance_badge = ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    border_radius=999,
                    bgcolor="#15110d",
                    border=ft.Border.all(1, BORDER_LIGHT),
                    content=ft.Text(
                        chance_text if can_still_drop else "0.0%",
                        color=ACCENT if can_still_drop else TEXT_DIM,
                        size=14,
                        weight=ft.FontWeight.BOLD,
                    ),
                )

                row = ft.Container(
                    padding=12,
                    border_radius=12,
                    bgcolor="#1a1510",
                    border=ft.Border.all(1, BORDER_LIGHT),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Row(
                                spacing=12,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    img,
                                    ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Row(
                                                spacing=10,
                                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                                controls=[
                                                    ft.Text(
                                                        name,
                                                        size=18,
                                                        weight=ft.FontWeight.BOLD,
                                                        color=TEXT_MAIN,
                                                    ),
                                                    chance_badge,
                                                ],
                                            ),
                                            ft.Text(
                                                f"Lifetime Tasks: {tasks}",
                                                color=TEXT_DIM,
                                            ),
                                            ft.Text(
                                                f"Packs Found: {found}/{maxp}",
                                                color=ACCENT,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            ft.Container(
                                padding=ft.Padding.symmetric(
                                    horizontal=14, vertical=10
                                ),
                                border_radius=10,
                                bgcolor="#2b241a",
                                border=ft.Border.all(1, BORDER_LIGHT),
                                on_click=lambda e, x=mid: (
                                    complete_task_for_master(x),
                                    rebuild(),
                                ),
                                content=ft.Text(
                                    "Complete Task",
                                    color=TEXT_MAIN,
                                    weight=ft.FontWeight.BOLD,
                                ),
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
            border=ft.Border.all(1, BORDER_DARK),
            border_radius=14,
            padding=12,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                "Slayer Masters",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXT_MAIN,
                            ),
                            ft.Container(
                                padding=6,
                                border_radius=8,
                                border=ft.Border.all(1, BORDER_LIGHT),
                                bgcolor="#2b241a",
                                on_click=lambda e: close_dialog(dlg),
                                content=ft.Text(
                                    "X", color=TEXT_MAIN, weight=ft.FontWeight.BOLD
                                ),
                            ),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        bgcolor=PANEL_INNER,
                        border=ft.Border.all(1, BORDER_LIGHT),
                        border_radius=12,
                        content=list_view,
                    ),
                ],
            ),
        )
        open_dialog(dlg)

    top_bar = ft.Container(
        height=64,
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        bgcolor="#15110d",
        border=ft.Border.all(1, BORDER_LIGHT),
        border_radius=12,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    "Welcome to RuneCards!",
                    size=22,
                    weight=ft.FontWeight.BOLD,
                    color=TEXT_MAIN,
                ),
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                            border_radius=10,
                            border=ft.Border.all(1, BORDER_LIGHT),
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
                            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                            border_radius=10,
                            border=ft.Border.all(1, BORDER_LIGHT),
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
                            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                            border_radius=10,
                            border=ft.Border.all(1, BORDER_LIGHT),
                            bgcolor="#1a1510",
                            content=ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Text("Tasks completed", color=TEXT_DIM),
                                    top_tasks,
                                ],
                            ),
                        ),
                        icon_button(
                            "ui/log.png",
                            open_task_log_window,
                            tooltip="Task Log",
                            size=22,
                        ),
                        icon_button(
                            "ui/skills.png",
                            open_skills_window,
                            tooltip="Skills",
                            size=22,
                        ),
                        icon_button(
                            "ui/Quests.png",
                            open_quests_window,
                            tooltip="Quests",
                            size=22,
                        ),
                        icon_button(
                            "ui/notes.png", open_notes_window, tooltip="Notes", size=22
                        ),
                    ],
                ),
            ],
        ),
    )

    left_panel = panel(
        ft.Column(
            spacing=10,
            controls=[
                action_tile(
                    "Open pack",
                    f"Pick 1 of {int(config.get('cardsPerPack', 3))} cards",
                    open_pack,
                    icon_src="ui/PackIco.png",
                    emoji_fallback="🎴",
                    primary=True,
                ),
                action_tile(
                    "Slayer Masters",
                    "Log a task (rolls for a pack)",
                    open_slayer_masters_window,
                    icon_src="ui/slayer.png",
                    emoji_fallback="⚔",
                ),
                action_tile(
                    "Cloud saves",
                    "Local / Supabase sync settings",
                    open_cloud_window,  # ✅ add this
                    icon_src=None,
                    emoji_fallback="☁",
                ),
                ft.Container(height=6),
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        save_path_text,
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                            border_radius=10,
                            bgcolor="#2b241a",
                            border=ft.Border.all(1, BORDER_LIGHT),
                            on_click=toggle_save_path,
                            content=save_toggle_text,
                        ),
                    ],
                ),
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
                pick_btn_section,
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
    ft.run(main, assets_dir="assets")
