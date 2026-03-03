import os

import flet as ft


def _align(name: str, x: float, y: float):
    if hasattr(ft, "alignment") and hasattr(ft.alignment, name):
        return getattr(ft.alignment, name)
    return ft.Alignment(x, y)


HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
CARDS_PATH = os.path.join(HERE, "cards.json")
QUESTS_PATH = os.path.join(HERE, "quests.json")

APP_DATA_DIR = os.getenv("FLET_APP_STORAGE_DATA")
if not APP_DATA_DIR:
    APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".runecards")

SAVE_DIR = APP_DATA_DIR
SAVE_PATH = os.path.join(SAVE_DIR, "save.json")
CLOUD_CFG_PATH = os.path.join(SAVE_DIR, "cloud.json")
CLOUD_SESSION_PATH = os.path.join(SAVE_DIR, "cloud_session.json")

ASSETS_DIR = os.path.join(HERE, "assets")

CLOUD_TABLE = "saves"

ALIGN_CENTER = _align("center", 0.0, 0.0)
ALIGN_TOP_RIGHT = _align("top_right", 1.0, -1.0)
ALIGN_TOP_LEFT = _align("top_left", -1.0, -1.0)
ALIGN_BOTTOM_RIGHT = _align("bottom_right", 1.0, 1.0)
ALIGN_BOTTOM_LEFT = _align("bottom_left", -1.0, 1.0)
ALIGN_CENTER_LEFT = _align("center_left", -1.0, 0.0)
ALIGN_CENTER_RIGHT = _align("center_right", 1.0, 0.0)
ALIGN_TOP_CENTER = _align("top_center", 0.0, -1.0)
ALIGN_BOTTOM_CENTER = _align("bottom_center", 0.0, 1.0)

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

SLAYER_START_MULT = 2.3
SLAYER_END_MULT = 0.50
SLAYER_CURVE = 1.0
SLAYER_PITY_PER_TASK = 0.04
SLAYER_PITY_CAP = 0.25
SLAYER_CHANCE_CAP = 0.90

NOTES_TEXT = (
    "- Packs stack.\n"
    "- You can only have 1 active card.\n"
    "- Slayer Masters have finite pack pools."
)
