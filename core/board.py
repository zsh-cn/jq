from collections import deque

from config import BOARD_ROWS, BOARD_COLS
from core.player import Player, PieceType, PIECE_NAMES, PIECE_RANK


BORDER_ROW_TOP = 5
BORDER_ROW_BOTTOM = 7
BORDER_CONNECTED_COLS = (0, 2, 4)
MOUNTAIN_COLS = (1, 3)
FRONT_LINE_ROW = 6


class CellType:
    ROAD = 0
    RAILWAY = 1
    CAMP = 2
    HQ = 3
    MOUNTAIN = 4


class Piece:
    def __init__(self, piece_type, owner):
        self.piece_type = piece_type
        self.owner = owner
        self.visible = True
        self.locked = False

    @property
    def name(self):
        return PIECE_NAMES.get(self.piece_type, "?")

    @property
    def rank(self):
        return PIECE_RANK.get(self.piece_type, 0)


class Board:
    def __init__(self):
        self.grid = [[None for _ in range(BOARD_COLS)] for _ in range(BOARD_ROWS)]
        self.cell_types = self._init_cell_types()
        self.history = []

    def _init_cell_types(self):
        types = [[CellType.ROAD for _ in range(BOARD_COLS)] for _ in range(BOARD_ROWS)]

        types[0][1] = CellType.HQ
        types[0][3] = CellType.HQ
        for c in range(BOARD_COLS):
            types[1][c] = CellType.RAILWAY
        types[2][1] = CellType.CAMP
        types[2][3] = CellType.CAMP
        types[3][2] = CellType.CAMP
        types[4][1] = CellType.CAMP
        types[4][3] = CellType.CAMP
        for r in range(2, 5):
            types[r][0] = CellType.RAILWAY
            types[r][4] = CellType.RAILWAY
        for c in range(BOARD_COLS):
            types[5][c] = CellType.RAILWAY

        types[6][0] = CellType.RAILWAY
        types[6][2] = CellType.RAILWAY
        types[6][4] = CellType.RAILWAY
        for c in MOUNTAIN_COLS:
            types[FRONT_LINE_ROW][c] = CellType.MOUNTAIN

        for c in range(BOARD_COLS):
            types[7][c] = CellType.RAILWAY
        types[8][1] = CellType.CAMP
        types[8][3] = CellType.CAMP
        types[9][2] = CellType.CAMP
        types[10][1] = CellType.CAMP
        types[10][3] = CellType.CAMP
        for r in range(8, 11):
            types[r][0] = CellType.RAILWAY
            types[r][4] = CellType.RAILWAY
        for c in range(BOARD_COLS):
            types[11][c] = CellType.RAILWAY
        types[12][1] = CellType.HQ
        types[12][3] = CellType.HQ

        return types

    def _is_mountain(self, r, c):
        return self.cell_types[r][c] == CellType.MOUNTAIN

    def _is_no_stop_cell(self, r, c):
        return r == FRONT_LINE_ROW and self.cell_types[r][c] == CellType.RAILWAY

    def _is_border_crossing(self, r1, c1, r2, c2):
        if (r1 == BORDER_ROW_TOP and r2 == BORDER_ROW_BOTTOM) or \
           (r1 == BORDER_ROW_BOTTOM and r2 == BORDER_ROW_TOP):
            return c1 not in BORDER_CONNECTED_COLS
        if (r1 == BORDER_ROW_TOP and r2 == FRONT_LINE_ROW) or \
           (r1 == FRONT_LINE_ROW and r2 == BORDER_ROW_TOP):
            return c1 not in BORDER_CONNECTED_COLS
        if (r1 == BORDER_ROW_BOTTOM and r2 == FRONT_LINE_ROW) or \
           (r1 == FRONT_LINE_ROW and r2 == BORDER_ROW_BOTTOM):
            return c1 not in BORDER_CONNECTED_COLS
        return False

    def _can_enter_cell(self, r, c, owner):
        if not self.is_valid_position(r, c):
            return False
        if self._is_mountain(r, c):
            return False
        piece = self.grid[r][c]
        if piece is not None and piece.owner == owner:
            return False
        return True

    def _are_orthogonally_connected(self, r1, c1, r2, c2):
        if self._is_mountain(r2, c2):
            return False
        if self._is_border_crossing(r1, c1, r2, c2):
            return False
        return True

    def reset(self):
        self.grid = [[None for _ in range(BOARD_COLS)] for _ in range(BOARD_ROWS)]
        self.history = []

    def copy(self):
        new_board = Board()
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                if self.grid[r][c] is not None:
                    p = self.grid[r][c]
                    new_piece = Piece(p.piece_type, p.owner)
                    new_piece.visible = p.visible
                    new_piece.locked = p.locked
                    new_board.grid[r][c] = new_piece
        new_board.history = list(self.history)
        return new_board

    def _can_target_be_attacked(self, tr, tc):
        if self.cell_types[tr][tc] == CellType.CAMP:
            return False
        return True

    def place_piece(self, row, col, piece):
        if not (0 <= row < BOARD_ROWS and 0 <= col < BOARD_COLS):
            return False
        ct = self.cell_types[row][col]
        if ct in (CellType.MOUNTAIN, CellType.CAMP):
            return False
        if self.grid[row][col] is not None:
            return False
        self.grid[row][col] = piece
        return True

    def remove_piece(self, row, col):
        piece = self.grid[row][col]
        self.grid[row][col] = None
        return piece

    def move_piece(self, from_row, from_col, to_row, to_col):
        piece = self.grid[from_row][from_col]
        if piece is None:
            return False
        self.grid[from_row][from_col] = None
        self.grid[to_row][to_col] = piece
        if self.cell_types[to_row][to_col] == CellType.HQ:
            piece.locked = True
        self.history.append((from_row, from_col, to_row, to_col, piece.piece_type, piece.owner))
        return True

    def get_cell_type(self, row, col):
        if 0 <= row < BOARD_ROWS and 0 <= col < BOARD_COLS:
            return self.cell_types[row][col]
        return None

    def is_valid_position(self, row, col):
        return 0 <= row < BOARD_ROWS and 0 <= col < BOARD_COLS

    def get_piece(self, row, col):
        if self.is_valid_position(row, col):
            return self.grid[row][col]
        return None

    def is_empty(self, row, col):
        return self.is_valid_position(row, col) and self.grid[row][col] is None

    def get_player_area_rows(self, player):
        if player == Player.RED:
            return range(7, 13)
        else:
            return range(0, 6)

    def get_piece_positions(self, player):
        positions = []
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = self.grid[r][c]
                if p is not None and p.owner == player:
                    positions.append((r, c))
        return positions

    def get_movable_pieces(self, player):
        movable = []
        for r, c in self.get_piece_positions(player):
            p = self.grid[r][c]
            if p.piece_type == PieceType.FLAG:
                continue
            if p.piece_type == PieceType.MINE:
                continue
            if p.locked:
                continue
            moves = self.get_valid_moves(r, c)
            if moves:
                movable.append((r, c, moves))
        return movable

    def get_valid_moves(self, row, col):
        piece = self.grid[row][col]
        if piece is None:
            return []
        if piece.piece_type == PieceType.FLAG:
            return []
        if piece.piece_type == PieceType.MINE:
            return []
        if piece.locked:
            return []
        if self.cell_types[row][col] == CellType.HQ:
            return []

        moves = []
        cell_type = self.cell_types[row][col]
        is_engineer = piece.piece_type == PieceType.ENGINEER

        if cell_type == CellType.RAILWAY:
            if is_engineer:
                moves = self._get_engineer_railway_moves(row, col, piece.owner)
            else:
                moves = self._get_straight_railway_moves(row, col, piece.owner)
            existing = set(moves)
            for ar, ac in self._get_adjacent_moves(row, col, piece.owner):
                if (ar, ac) not in existing:
                    moves.append((ar, ac))
        else:
            moves = self._get_adjacent_moves(row, col, piece.owner)

        return moves

    def _get_adjacent_moves(self, row, col, owner):
        moves = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row + dr, col + dc
            if not self.is_valid_position(nr, nc):
                continue
            if not self._are_orthogonally_connected(row, col, nr, nc):
                continue
            if self._is_no_stop_cell(nr, nc):
                continue
            if self.cell_types[nr][nc] == CellType.HQ:
                if self.grid[nr][nc] is not None:
                    if self.grid[nr][nc].owner != owner:
                        if self._can_target_be_attacked(nr, nc):
                            moves.append((nr, nc))
                else:
                    moves.append((nr, nc))
                continue
            if self.grid[nr][nc] is not None:
                if self.grid[nr][nc].owner != owner:
                    if self._can_target_be_attacked(nr, nc):
                        moves.append((nr, nc))
            else:
                moves.append((nr, nc))
        return moves

    def _get_straight_railway_moves(self, row, col, owner):
        moves = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            cr, cc = row + dr, col + dc
            while self.is_valid_position(cr, cc):
                if self._is_mountain(cr, cc):
                    break
                if self._is_border_crossing(cr - dr, cc - dc, cr, cc):
                    break
                if self.cell_types[cr][cc] != CellType.RAILWAY:
                    break
                is_no_stop = self._is_no_stop_cell(cr, cc)
                if self.grid[cr][cc] is not None:
                    if self.grid[cr][cc].owner != owner:
                        if self._can_target_be_attacked(cr, cc) and not is_no_stop:
                            moves.append((cr, cc))
                    break
                if not is_no_stop:
                    moves.append((cr, cc))
                cr += dr
                cc += dc
        return moves

    def _get_engineer_railway_moves(self, row, col, owner):
        moves = []
        visited = set()
        visited.add((row, col))
        queue = deque([(row, col)])

        while queue:
            cr, cc = queue.popleft()
            current_on_rail = (self.cell_types[cr][cc] == CellType.RAILWAY)
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = cr + dr, cc + dc
                if not self.is_valid_position(nr, nc):
                    continue
                if self._is_mountain(nr, nc):
                    continue
                if (nr, nc) in visited:
                    continue
                visited.add((nr, nc))
                if self._is_border_crossing(cr, cc, nr, nc):
                    continue
                next_on_rail = (self.cell_types[nr][nc] == CellType.RAILWAY)
                if not next_on_rail:
                    continue
                target = self.grid[nr][nc]
                is_no_stop = self._is_no_stop_cell(nr, nc)
                if target is not None:
                    if target.owner != owner:
                        if self._can_target_be_attacked(nr, nc) and not is_no_stop:
                            moves.append((nr, nc))
                    continue
                if not is_no_stop:
                    moves.append((nr, nc))
                if current_on_rail:
                    queue.append((nr, nc))

        return moves

    def resolve_battle(self, attacker_piece, defender_piece):
        atk_type = attacker_piece.piece_type
        def_type = defender_piece.piece_type

        if def_type == PieceType.FLAG:
            return "attacker"

        if atk_type == PieceType.BOMB:
            return "both"
        if def_type == PieceType.BOMB:
            return "both"

        if atk_type == PieceType.ENGINEER and def_type == PieceType.MINE:
            return "attacker"
        if def_type == PieceType.MINE:
            return "defender"

        atk_rank = PIECE_RANK.get(atk_type, 0)
        def_rank = PIECE_RANK.get(def_type, 0)

        if atk_rank > def_rank:
            return "attacker"
        elif atk_rank < def_rank:
            return "defender"
        else:
            return "both"

    def check_flag_captured(self, player):
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = self.grid[r][c]
                if p is not None and p.owner == player and p.piece_type == PieceType.FLAG:
                    return False
        return True

    def has_valid_moves(self, player):
        return len(self.get_movable_pieces(player)) > 0