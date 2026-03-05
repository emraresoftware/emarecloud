"""
EmareCloud — Config I/O
RAID protokolleri ve legacy ayarlar için config.json okuma/yazma.
"""

import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')


def load_config() -> dict:
    """config.json — sadece RAID protokolleri ve legacy ayarlar için."""
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"servers": [], "settings": {}, "raid_protocols": []}


def save_config(config: dict):
    """config.json'a yazar."""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
