from utils.persistence import (
    save_state,
    load_state
)


def test_save_and_load():

    data = {
        "destination": "Seattle"
    }

    save_state(data)

    loaded = load_state()

    assert loaded["destination"] == "Seattle"