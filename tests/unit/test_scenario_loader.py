import os

from app.game.scenarios import load_scenarios
from app.game.tile_loader import load_tiles_from_file


def test_loads_scenarios():
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app", "data"))
    scenarios = load_scenarios(os.path.join(data_dir, "scenarios.json"))
    assert 1 in scenarios
    s1 = scenarios[1]
    assert s1.starting_timer_ms > 0
    assert s1.min_players <= s1.max_players


def test_scenario_tile_ids_exist():
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app", "data"))
    scenarios = load_scenarios(os.path.join(data_dir, "scenarios.json"))
    tiles = load_tiles_from_file(os.path.join(data_dir, "tiles.json"))
    for s in scenarios.values():
        assert s.start_tile in tiles, f"scenario {s.id} start_tile {s.start_tile} missing"
        for tid in s.deck_tile_ids:
            assert tid in tiles, f"scenario {s.id} deck tile {tid} missing"
