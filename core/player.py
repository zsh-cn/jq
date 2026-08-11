from enum import IntEnum


class Player(IntEnum):
    EMPTY = 0
    RED = 1
    BLUE = 2


class PieceType(IntEnum):
    FLAG = 0
    MINE = 1
    BOMB = 2
    ENGINEER = 3
    PLATOON = 4
    COMPANY = 5
    BATTALION = 6
    REGIMENT = 7
    BRIGADE = 8
    DIVISION = 9
    ARMY = 10
    COMMANDER = 11


PIECE_NAMES = {
    PieceType.FLAG: "军旗",
    PieceType.MINE: "地雷",
    PieceType.BOMB: "炸弹",
    PieceType.ENGINEER: "工兵",
    PieceType.PLATOON: "排长",
    PieceType.COMPANY: "连长",
    PieceType.BATTALION: "营长",
    PieceType.REGIMENT: "团长",
    PieceType.BRIGADE: "旅长",
    PieceType.DIVISION: "师长",
    PieceType.ARMY: "军长",
    PieceType.COMMANDER: "司令",
}

PIECE_COUNT = {
    PieceType.FLAG: 1,
    PieceType.MINE: 3,
    PieceType.BOMB: 2,
    PieceType.ENGINEER: 3,
    PieceType.PLATOON: 3,
    PieceType.COMPANY: 3,
    PieceType.BATTALION: 2,
    PieceType.REGIMENT: 2,
    PieceType.BRIGADE: 2,
    PieceType.DIVISION: 2,
    PieceType.ARMY: 1,
    PieceType.COMMANDER: 1,
}

PIECE_RANK = {
    PieceType.FLAG: 0,
    PieceType.MINE: 0,
    PieceType.BOMB: 0,
    PieceType.ENGINEER: 1,
    PieceType.PLATOON: 2,
    PieceType.COMPANY: 3,
    PieceType.BATTALION: 4,
    PieceType.REGIMENT: 5,
    PieceType.BRIGADE: 6,
    PieceType.DIVISION: 7,
    PieceType.ARMY: 8,
    PieceType.COMMANDER: 9,
}

TOTAL_PIECES_PER_SIDE = 25