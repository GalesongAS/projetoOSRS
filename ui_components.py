import os

import flet as ft

from app_constants import (
    ALIGN_CENTER,
    ASSETS_DIR,
    BORDER_DARK,
    BORDER_LIGHT,
    PANEL_BG,
    PANEL_INNER,
    TEXT_DIM,
    TEXT_MAIN,
)


def panel(content, padding=16):
    return ft.Container(
        padding=padding,
        bgcolor=PANEL_BG,
        border_radius=14,
        border=ft.Border.all(1, BORDER_DARK),
        content=ft.Container(
            padding=12,
            bgcolor=PANEL_INNER,
            border_radius=12,
            border=ft.Border.all(1, BORDER_LIGHT),
            content=content,
        ),
    )


def osrs_button(text: str, on_click, primary=False):
    return ft.Container(
        border_radius=10,
        border=ft.Border.all(1, BORDER_LIGHT),
        bgcolor=("#3a2f1f" if primary else "#2b241a"),
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        on_click=on_click,
        content=ft.Text(text, size=14, color=TEXT_MAIN, weight=ft.FontWeight.BOLD),
    )


def icon_button(img_src: str, on_click, tooltip: str = "", size: int = 22):
    return ft.Container(
        width=size + 18,
        height=size + 18,
        border_radius=10,
        border=ft.Border.all(1, BORDER_LIGHT),
        bgcolor="#2b241a",
        padding=8,
        tooltip=tooltip or None,
        on_click=on_click,
        content=ft.Image(src=img_src, width=size, height=size, fit=ft.BoxFit.CONTAIN),
    )


def stat_pill(label: str, value_control: ft.Control):
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border_radius=999,
        bgcolor="#1a1510",
        border=ft.Border.all(1, BORDER_LIGHT),
        content=ft.Row(
            tight=True,
            spacing=6,
            controls=[
                ft.Text(label, color=TEXT_DIM, size=12),
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
    emoji_fallback: str = "*",
    primary: bool = False,
):
    bg = "#3a2f1f" if primary else "#15110d"
    fallback_text = emoji_fallback if emoji_fallback.isascii() else title[:4]

    icon_ok = False
    if icon_src:
        icon_ok = os.path.exists(os.path.join(ASSETS_DIR, icon_src.replace("/", os.sep)))

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
