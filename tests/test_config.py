from pathlib import Path
import tempfile
from unittest.mock import patch

from diff_game.config import (
    load_viewport_config,
    save_viewport_config,
    clear_viewport_config,
)


def test_save_load_clear_viewport_config(tmp_path: Path):
    test_config_file = tmp_path / ".diff_game_viewport.json"

    with patch("diff_game.config.get_viewport_config_path", return_value=test_config_file):
        # Initial: no config
        assert load_viewport_config() is None

        # Save config
        ref = {"x": 30.0, "y": 340.0, "width": 780.0, "height": 400.0}
        tgt = {"x": 32.0, "y": 850.0, "width": 780.0, "height": 400.0}
        saved_path = save_viewport_config(ref, tgt, scale=2.0)
        assert saved_path == test_config_file
        assert test_config_file.exists()

        # Load config
        loaded = load_viewport_config()
        assert loaded is not None
        assert loaded["scale"] == 2.0
        assert loaded["refBox"]["x"] == 30.0
        assert loaded["tgtBox"]["y"] == 850.0

        # Clear config
        assert clear_viewport_config() is True
        assert not test_config_file.exists()
        assert load_viewport_config() is None
