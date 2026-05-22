from app.game.timer import SandTimer


def test_starts_at_starting_ms():
    t = SandTimer(60000)
    assert t.remaining_ms == 60000
    assert not t.expired


def test_tick_decrements():
    t = SandTimer(60000)
    t.tick(1000)
    assert t.remaining_ms == 59000


def test_paused_tick_no_op():
    t = SandTimer(60000)
    t.pause()
    t.tick(5000)
    assert t.remaining_ms == 60000


def test_expires_at_zero():
    t = SandTimer(1000)
    t.tick(1500)
    assert t.remaining_ms == 0
    assert t.expired


def test_bonus_cannot_exceed_starting():
    t = SandTimer(60000)
    t.tick(10000)
    t.add_bonus(99999)
    assert t.remaining_ms == 60000


def test_bonus_adds_correctly():
    t = SandTimer(60000)
    t.tick(20000)
    t.add_bonus(5000)
    assert t.remaining_ms == 45000


def test_reset_restores_starting():
    t = SandTimer(60000)
    t.tick(50000)
    t.reset()
    assert t.remaining_ms == 60000


def test_flip_inverts_remaining_giving_more_time_late():
    """Per rules: flipping the timer with little time left gives you a lot of time
    (because the elapsed sand was big — it's now above)."""
    t = SandTimer(180000)
    t.tick(170000)             # 10s remaining
    t.flip()
    assert t.remaining_ms == 170000


def test_flip_inverts_remaining_giving_less_time_early():
    """Flipping early in the game gives you LESS time (the small elapsed pile flips above)."""
    t = SandTimer(180000)
    t.tick(20000)              # 160s remaining
    t.flip()
    assert t.remaining_ms == 20000


def test_double_flip_returns_to_original():
    t = SandTimer(180000)
    t.tick(50000)
    t.flip()
    t.flip()
    assert t.remaining_ms == 130000
