from app.game.board import inverse_rotate_local, rotate_direction, rotate_local
from app.game.enums import Direction


def test_rotate_local_zero_is_identity():
    for r in range(4):
        for c in range(4):
            assert rotate_local(r, c, 0) == (r, c)


def test_rotate_local_inverse_roundtrip():
    for rot in range(4):
        for lr in range(4):
            for lc in range(4):
                gr, gc = rotate_local(lr, lc, rot)
                ilr, ilc = inverse_rotate_local(gr, gc, rot)
                assert (ilr, ilc) == (lr, lc), f"rot={rot} lr={lr} lc={lc}"


def test_rotate_direction_n_to_e_to_s_to_w():
    assert rotate_direction(Direction.N, 1) == Direction.E
    assert rotate_direction(Direction.N, 2) == Direction.S
    assert rotate_direction(Direction.N, 3) == Direction.W
    assert rotate_direction(Direction.E, 1) == Direction.S
    assert rotate_direction(Direction.W, 1) == Direction.N


def test_corners_stay_corners_under_rotation():
    # Corners should map to corners (4 corners → 4 corners)
    corners = [(0, 0), (0, 3), (3, 0), (3, 3)]
    for rot in range(4):
        rotated = {rotate_local(r, c, rot) for r, c in corners}
        assert rotated == set(corners), f"rotation {rot} broke corners"


def test_full_grid_bijection():
    # Every cell maps to a unique cell at every rotation
    for rot in range(4):
        mapped = {rotate_local(r, c, rot) for r in range(4) for c in range(4)}
        assert len(mapped) == 16
