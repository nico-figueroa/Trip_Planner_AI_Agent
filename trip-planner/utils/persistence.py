import json
from pathlib import Path

STATE_FILE = Path("data/app_state.json")


def save_state(data):

    STATE_FILE.parent.mkdir(
        exist_ok=True
    )

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            indent=2
        )


def load_state():

    if not STATE_FILE.exists():
        return {}

    with open(
        STATE_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)