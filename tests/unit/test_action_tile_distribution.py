import pytest

from app.game.action_tiles import ALL_ACTIONS, distribute, union_of_actions


@pytest.mark.parametrize("n", list(range(1, 9)))
def test_distribution_sizes_match_player_count(n):
    pids = [f"p{i}" for i in range(n)]
    d = distribute(pids, seed=42)
    assert set(d.keys()) == set(pids)


@pytest.mark.parametrize("n", list(range(1, 9)))
def test_distribution_covers_all_actions(n):
    pids = [f"p{i}" for i in range(n)]
    d = distribute(pids, seed=42)
    assert union_of_actions(d) == ALL_ACTIONS


@pytest.mark.parametrize("n", list(range(2, 8)))
def test_no_single_player_has_all_actions(n):
    pids = [f"p{i}" for i in range(n)]
    d = distribute(pids, seed=42)
    for tile in d.values():
        assert tile.actions != ALL_ACTIONS


def test_solo_player_gets_all_actions():
    d = distribute(["solo"], seed=0)
    assert d["solo"].actions == ALL_ACTIONS


def test_too_many_players_rejected():
    with pytest.raises(ValueError):
        distribute([f"p{i}" for i in range(9)])


def test_distribution_is_deterministic_with_seed():
    pids = ["a", "b", "c", "d"]
    a = distribute(pids, seed=123)
    b = distribute(pids, seed=123)
    assert {pid: t.actions for pid, t in a.items()} == {pid: t.actions for pid, t in b.items()}
