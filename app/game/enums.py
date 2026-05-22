from enum import Enum, IntEnum


class Color(str, Enum):
    """Hero colors — matching the published game:
    Barbarian=YELLOW, Mage=PURPLE, Elf=GREEN, Dwarf=ORANGE.
    """
    YELLOW = "Y"   # Barbarian (sword)
    PURPLE = "P"   # Mage (vial)
    GREEN = "G"    # Elf (bow)
    ORANGE = "O"   # Dwarf (axe)


HERO_NAME: dict[Color, str] = {
    Color.YELLOW: "Barbarian",
    Color.PURPLE: "Mage",
    Color.GREEN: "Elf",
    Color.ORANGE: "Dwarf",
}


class Direction(IntEnum):
    N = 0
    E = 1
    S = 2
    W = 3

    def opposite(self) -> "Direction":
        return Direction((self + 2) % 4)

    def rotate(self, r: int) -> "Direction":
        return Direction((self + r) % 4)


DIR_VECTOR: dict[Direction, tuple[int, int]] = {
    Direction.N: (-1, 0),
    Direction.E: (0, 1),
    Direction.S: (1, 0),
    Direction.W: (0, -1),
}


class ActionType(str, Enum):
    MOVE_N = "MOVE_N"
    MOVE_E = "MOVE_E"
    MOVE_S = "MOVE_S"
    MOVE_W = "MOVE_W"
    ESCALATOR = "ESCALATOR"
    VORTEX = "VORTEX"
    EXPLORE = "EXPLORE"


def action_for_direction(direction: Direction) -> ActionType:
    return {
        Direction.N: ActionType.MOVE_N,
        Direction.E: ActionType.MOVE_E,
        Direction.S: ActionType.MOVE_S,
        Direction.W: ActionType.MOVE_W,
    }[direction]


class Feature(str, Enum):
    # Item spaces (heroes steal from these — matched by color)
    ITEM_Y = "item_y"
    ITEM_P = "item_p"
    ITEM_G = "item_g"
    ITEM_O = "item_o"
    # Exit spaces
    EXIT_Y = "exit_y"
    EXIT_P = "exit_p"
    EXIT_G = "exit_g"
    EXIT_O = "exit_o"
    # Vortex spaces (teleport destinations, color-matched)
    VORTEX_Y = "vortex_y"
    VORTEX_P = "vortex_p"
    VORTEX_G = "vortex_g"
    VORTEX_O = "vortex_o"
    # Exploration anchors (only the matching-color pawn triggers exploration)
    EXPLORE_Y = "explore_y"
    EXPLORE_P = "explore_p"
    EXPLORE_G = "explore_g"
    EXPLORE_O = "explore_o"
    # Sand-Timer space (one-use, flips the timer)
    SAND_TIMER = "sand_timer"
    # Crystal Ball (Mage-only; scenario 5+, lets explore place 2 tiles)
    CRYSTAL_BALL = "crystal_ball"
    # Security Camera (yellow tile; disabled by Barbarian; 2+ active blocks timer flips)
    CAMERA = "camera"
    # Out-of-Order marker (placed on used sand-timer / crystal-ball / camera squares)
    OUT_OF_ORDER = "out_of_order"
    # Starting central squares (any hero can begin here, placed randomly)
    START = "start"
    # Orange one-way wall: only Dwarf may pass (modeled as a passage feature)
    DWARF_PASSAGE = "dwarf_passage"


ITEM_FOR_COLOR: dict[Color, Feature] = {
    Color.YELLOW: Feature.ITEM_Y,
    Color.PURPLE: Feature.ITEM_P,
    Color.GREEN: Feature.ITEM_G,
    Color.ORANGE: Feature.ITEM_O,
}

EXIT_FOR_COLOR: dict[Color, Feature] = {
    Color.YELLOW: Feature.EXIT_Y,
    Color.PURPLE: Feature.EXIT_P,
    Color.GREEN: Feature.EXIT_G,
    Color.ORANGE: Feature.EXIT_O,
}

VORTEX_FOR_COLOR: dict[Color, Feature] = {
    Color.YELLOW: Feature.VORTEX_Y,
    Color.PURPLE: Feature.VORTEX_P,
    Color.GREEN: Feature.VORTEX_G,
    Color.ORANGE: Feature.VORTEX_O,
}

EXPLORE_FOR_COLOR: dict[Color, Feature] = {
    Color.YELLOW: Feature.EXPLORE_Y,
    Color.PURPLE: Feature.EXPLORE_P,
    Color.GREEN: Feature.EXPLORE_G,
    Color.ORANGE: Feature.EXPLORE_O,
}


class Phase(str, Enum):
    WAITING = "waiting"
    EXPLORING = "exploring"        # phase 1: get all heroes to their items
    ESCAPING = "escaping"          # phase 2: items stolen, get all heroes to exits
    FINISHED = "finished"


class Outcome(str, Enum):
    WIN = "win"
    LOSS_TIME = "loss_time"
