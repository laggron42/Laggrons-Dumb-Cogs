import enum


class Phase(enum.IntEnum):
    PENDING = 0
    REGISTER = 1
    AWAITING = 2
    ONGOING = 3
    DONE = 4


class MatchPhase(enum.IntEnum):
    PENDING = 0
    ON_HOLD = 1
    ONGOING = 2
    DONE = 3


class EventPhase(enum.IntEnum):
    MANUAL = 0
    PENDING = 1
    ONGOING = 2
    ON_HOLD = 3
    DONE = 4


class StageListType(enum.IntEnum):
    STAGES = 0
    COUNTERPICKS = 1
