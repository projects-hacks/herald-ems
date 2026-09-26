"""Two apps on one checkout (the demo on 8100, a teammate on 8103) must not share one saved call: HERALD_RUN_DIR
gives an instance its own state, audio and photos, while reference data stays shared."""
from pathlib import Path

from herald.config import Settings


def test_run_dir_separates_the_call_but_not_reference_data(tmp_path):
    shared = Settings.from_env({"HERALD_DATA_DIR": str(tmp_path / "data")})
    mine = Settings.from_env({"HERALD_DATA_DIR": str(tmp_path / "data"), "HERALD_RUN_DIR": str(tmp_path / "8103")})
    for attr in ("state_dir", "audio_dir", "photo_dir"):
        assert getattr(mine, attr).parent == tmp_path / "8103" and getattr(mine, attr) != getattr(shared, attr)
    assert mine.protocols_dir == shared.protocols_dir and mine.terminology_index == shared.terminology_index


def test_without_a_run_dir_the_call_stays_where_it_was():
    s = Settings.from_env({})
    assert s.state_dir == s.root / "data" / "state" and isinstance(s.state_dir, Path)
