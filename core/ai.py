import random
import time
import math
from config import BOARD_ROWS, BOARD_COLS
from core.board import Board, Piece, CellType
from core.player import Player, PieceType, PIECE_NAMES, PIECE_RANK, PIECE_COUNT, TOTAL_PIECES_PER_SIDE


PIECE_VALUES = {
    PieceType.FLAG: 10000,
    PieceType.COMMANDER: 900,
    PieceType.ARMY: 800,
    PieceType.DIVISION: 700,
    PieceType.BRIGADE: 600,
    PieceType.REGIMENT: 500,
    PieceType.BATTALION: 400,
    PieceType.COMPANY: 300,
    PieceType.PLATOON: 200,
    PieceType.ENGINEER: 250,
    PieceType.BOMB: 500,
    PieceType.MINE: 150,
}

POSITIONAL_BONUS_RED = {}
for r in range(BOARD_ROWS):
    for c in range(BOARD_COLS):
        advance = max(0, 6 - r)
        center = 2 - abs(c - 2)
        POSITIONAL_BONUS_RED[(r, c)] = advance * 3 + center * 2

POSITIONAL_BONUS_BLUE = {}
for r in range(BOARD_ROWS):
    for c in range(BOARD_COLS):
        advance = max(0, r - 7)
        center = 2 - abs(c - 2)
        POSITIONAL_BONUS_BLUE[(r, c)] = advance * 3 + center * 2

COMMANDER_SAFETY_BONUS = 80
FLAG_PROTECTION_BONUS = 40
ENGINEER_MINE_BONUS = 120
CAMP_BONUS = 30
MOBILITY_WEIGHT = 18
ADVANCE_WEIGHT = 3

ZOBRIST_PIECE_TABLE = {}
ZOBRIST_PLAYER_TABLE = {}
for pt in PieceType:
    for p in Player:
        if p == Player.EMPTY:
            continue
        ZOBRIST_PIECE_TABLE[(pt, p)] = random.getrandbits(64)
for p in Player:
    if p == Player.EMPTY:
        continue
    ZOBRIST_PLAYER_TABLE[p] = random.getrandbits(64)

TT_EXACT = 0
TT_LOWER = 1
TT_UPPER = 2


class TranspositionTable:
    def __init__(self, max_size=100000):
        self._table = {}
        self._max_size = max_size

    def clear(self):
        self._table.clear()

    def store(self, hash_key, depth, flag, value, best_move=None):
        if len(self._table) >= self._max_size:
            self._table.clear()
        entry = self._table.get(hash_key)
        if entry is not None and entry[0] >= depth:
            return
        self._table[hash_key] = (depth, flag, value, best_move)

    def lookup(self, hash_key):
        return self._table.get(hash_key, None)


class KillerMoves:
    def __init__(self, max_depth=20):
        self._moves = [[None, None] for _ in range(max_depth)]

    def add(self, depth, move):
        if self._moves[depth][0] != move:
            self._moves[depth][1] = self._moves[depth][0]
            self._moves[depth][0] = move

    def get(self, depth):
        return self._moves[depth]


class MilitaryChessAI:
    def __init__(self):
        self._max_depth = 4
        self._time_limit = 3.0
        self._start_time = 0
        self._timeout = False
        self._tt = TranspositionTable()
        self._killer = KillerMoves()
        self._known_enemy_pieces = {}
        self._nodes_searched = 0
        self._cutoffs = 0
        self._difficulty = "hard"

    def set_difficulty(self, level):
        self._difficulty = level
        if level == "easy":
            self._max_depth = 1
            self._time_limit = 0.5
        elif level == "medium":
            self._max_depth = 2
            self._time_limit = 1.5
        elif level == "hard":
            self._max_depth = 4
            self._time_limit = 3.0

    def _compute_zobrist_hash(self, board):
        h = 0
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is not None:
                    h ^= ZOBRIST_PIECE_TABLE[(p.piece_type, p.owner)]
        return h

    def _track_enemy_pieces(self, board, ai_player):
        opponent = Player.RED if ai_player == Player.BLUE else Player.BLUE
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is not None and p.owner == opponent:
                    self._known_enemy_pieces[(r, c)] = (p.piece_type, p.owner)

    def _get_known_enemy_at(self, r, c):
        return self._known_enemy_pieces.get((r, c), None)

    def auto_setup(self, board, player):
        patterns = [
            self._setup_aggressive,
            self._setup_defensive,
            self._setup_balanced,
            self._setup_flank_attack,
            self._setup_trap_master,
        ]
        pattern = random.choice(patterns)
        pattern(board, player)

    def _clear_player_area(self, board, player):
        area_rows = list(board.get_player_area_rows(player))
        for r in area_rows:
            for c in range(5):
                if board.get_piece(r, c) is not None:
                    board.remove_piece(r, c)

    def _get_area_info(self, board, player):
        area_rows = sorted(list(board.get_player_area_rows(player)))
        positions = []
        for r in area_rows:
            for c in range(5):
                ct = board.get_cell_type(r, c)
                if ct != CellType.CAMP:
                    positions.append((r, c, ct))
        hq_positions = [(r, c) for r, c, ct in positions if ct == CellType.HQ]
        normal_positions = [(r, c) for r, c, ct in positions if ct != CellType.HQ]
        if player == Player.RED:
            front_row = area_rows[0]
            back_rows = (area_rows[-2], area_rows[-1])
            front_rows = [area_rows[0], area_rows[1]]
            mid_rows = [area_rows[2], area_rows[3]]
        else:
            front_row = area_rows[-1]
            back_rows = (area_rows[0], area_rows[1])
            front_rows = [area_rows[-2], area_rows[-1]]
            mid_rows = [area_rows[-4], area_rows[-3]]
        return hq_positions, normal_positions, front_row, back_rows, front_rows, mid_rows

    def _setup_aggressive(self, board, player):
        self._clear_player_area(board, player)
        hq_positions, normal_positions, front_row, back_rows, front_rows, mid_rows = self._get_area_info(board, player)

        flag_pos = random.choice(hq_positions)
        board.place_piece(flag_pos[0], flag_pos[1], Piece(PieceType.FLAG, player))
        other_hq = [hq for hq in hq_positions if hq != flag_pos]

        back_positions = [(r, c) for r, c in normal_positions if r in back_rows]
        random.shuffle(back_positions)
        mine_count = 0
        for r, c in back_positions:
            if mine_count >= PIECE_COUNT[PieceType.MINE]:
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(PieceType.MINE, player))
                mine_count += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        if other_hq:
            hq = other_hq[0]
            if board.get_piece(hq[0], hq[1]) is None:
                board.place_piece(hq[0], hq[1], Piece(PieceType.COMMANDER, player))

        front_positions = [(r, c) for r, c in normal_positions if r in front_rows]
        random.shuffle(front_positions)
        strong_order = [PieceType.ARMY, PieceType.DIVISION, PieceType.BRIGADE, PieceType.REGIMENT]
        placed_front = 0
        for r, c in front_positions:
            if placed_front >= len(strong_order):
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(strong_order[placed_front], player))
                placed_front += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        mid_positions = [(r, c) for r, c in normal_positions if r in mid_rows]
        random.shuffle(mid_positions)
        bomb_count = 0
        for r, c in mid_positions:
            if bomb_count >= PIECE_COUNT[PieceType.BOMB]:
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(PieceType.BOMB, player))
                bomb_count += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        remaining_pieces = []
        for pt, count in PIECE_COUNT.items():
            placed_in_area = 0
            area_rows = list(board.get_player_area_rows(player))
            for r in area_rows:
                for c in range(5):
                    p = board.get_piece(r, c)
                    if p is not None and p.owner == player and p.piece_type == pt:
                        placed_in_area += 1
            for _ in range(count - placed_in_area):
                remaining_pieces.append(pt)
        random.shuffle(remaining_pieces)

        available = [(r, c) for r, c in normal_positions if board.get_piece(r, c) is None]
        random.shuffle(available)
        for pt in remaining_pieces:
            for r, c in available:
                if board.get_piece(r, c) is None:
                    board.place_piece(r, c, Piece(pt, player))
                    available.remove((r, c))
                    break

    def _setup_defensive(self, board, player):
        self._clear_player_area(board, player)
        hq_positions, normal_positions, front_row, back_rows, front_rows, mid_rows = self._get_area_info(board, player)

        flag_pos = random.choice(hq_positions)
        board.place_piece(flag_pos[0], flag_pos[1], Piece(PieceType.FLAG, player))
        other_hq = [hq for hq in hq_positions if hq != flag_pos]

        back_positions = [(r, c) for r, c in normal_positions if r in back_rows]
        random.shuffle(back_positions)
        mine_count = 0
        for r, c in back_positions:
            if mine_count >= PIECE_COUNT[PieceType.MINE]:
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(PieceType.MINE, player))
                mine_count += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        if other_hq:
            hq = other_hq[0]
            if board.get_piece(hq[0], hq[1]) is None:
                board.place_piece(hq[0], hq[1], Piece(PieceType.COMMANDER, player))

        nearby_flag = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = flag_pos[0] + dr, flag_pos[1] + dc
            if board.is_valid_position(nr, nc) and board.get_cell_type(nr, nc) != CellType.CAMP:
                nearby_flag.append((nr, nc))
        random.shuffle(nearby_flag)
        bomb_count = 0
        for r, c in nearby_flag:
            if bomb_count >= PIECE_COUNT[PieceType.BOMB]:
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(PieceType.BOMB, player))
                bomb_count += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        mid_positions = [(r, c) for r, c in normal_positions if r in mid_rows]
        random.shuffle(mid_positions)
        strong_order = [PieceType.ARMY, PieceType.DIVISION, PieceType.BRIGADE]
        placed_strong = 0
        for r, c in mid_positions:
            if placed_strong >= len(strong_order):
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(strong_order[placed_strong], player))
                placed_strong += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        remaining_pieces = []
        for pt, count in PIECE_COUNT.items():
            placed_in_area = 0
            area_rows = list(board.get_player_area_rows(player))
            for r in area_rows:
                for c in range(5):
                    p = board.get_piece(r, c)
                    if p is not None and p.owner == player and p.piece_type == pt:
                        placed_in_area += 1
            for _ in range(count - placed_in_area):
                remaining_pieces.append(pt)
        random.shuffle(remaining_pieces)

        available = [(r, c) for r, c in normal_positions if board.get_piece(r, c) is None]
        random.shuffle(available)
        for pt in remaining_pieces:
            for r, c in available:
                if board.get_piece(r, c) is None:
                    board.place_piece(r, c, Piece(pt, player))
                    available.remove((r, c))
                    break

    def _setup_balanced(self, board, player):
        self._clear_player_area(board, player)
        hq_positions, normal_positions, front_row, back_rows, front_rows, mid_rows = self._get_area_info(board, player)

        flag_pos = random.choice(hq_positions)
        board.place_piece(flag_pos[0], flag_pos[1], Piece(PieceType.FLAG, player))
        other_hq = [hq for hq in hq_positions if hq != flag_pos]

        back_positions = [(r, c) for r, c in normal_positions if r in back_rows]
        random.shuffle(back_positions)
        mine_count = 0
        for r, c in back_positions:
            if mine_count >= PIECE_COUNT[PieceType.MINE]:
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(PieceType.MINE, player))
                mine_count += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        if other_hq:
            hq = other_hq[0]
            if board.get_piece(hq[0], hq[1]) is None:
                board.place_piece(hq[0], hq[1], Piece(PieceType.COMMANDER, player))

        front_positions = [(r, c) for r, c in normal_positions if r in front_rows]
        random.shuffle(front_positions)
        front_pieces = [PieceType.BATTALION, PieceType.REGIMENT, PieceType.PLATOON, PieceType.COMPANY]
        random.shuffle(front_pieces)
        placed_front = 0
        for r, c in front_positions:
            if placed_front >= len(front_pieces):
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(front_pieces[placed_front], player))
                placed_front += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        mid_positions = [(r, c) for r, c in normal_positions if r in mid_rows]
        random.shuffle(mid_positions)
        mid_pieces = [PieceType.ARMY, PieceType.DIVISION, PieceType.BRIGADE]
        placed_mid = 0
        for r, c in mid_positions:
            if placed_mid >= len(mid_pieces):
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(mid_pieces[placed_mid], player))
                placed_mid += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        bomb_positions = [(r, c) for r, c in normal_positions if r != front_row]
        random.shuffle(bomb_positions)
        bomb_count = 0
        for r, c in bomb_positions:
            if bomb_count >= PIECE_COUNT[PieceType.BOMB]:
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(PieceType.BOMB, player))
                bomb_count += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        remaining_pieces = []
        for pt, count in PIECE_COUNT.items():
            placed_in_area = 0
            area_rows = list(board.get_player_area_rows(player))
            for r in area_rows:
                for c in range(5):
                    p = board.get_piece(r, c)
                    if p is not None and p.owner == player and p.piece_type == pt:
                        placed_in_area += 1
            for _ in range(count - placed_in_area):
                remaining_pieces.append(pt)
        random.shuffle(remaining_pieces)

        available = [(r, c) for r, c in normal_positions if board.get_piece(r, c) is None]
        random.shuffle(available)
        for pt in remaining_pieces:
            for r, c in available:
                if board.get_piece(r, c) is None:
                    board.place_piece(r, c, Piece(pt, player))
                    available.remove((r, c))
                    break

    def _setup_flank_attack(self, board, player):
        self._clear_player_area(board, player)
        hq_positions, normal_positions, front_row, back_rows, front_rows, mid_rows = self._get_area_info(board, player)

        flag_pos = random.choice(hq_positions)
        board.place_piece(flag_pos[0], flag_pos[1], Piece(PieceType.FLAG, player))
        other_hq = [hq for hq in hq_positions if hq != flag_pos]

        back_positions = [(r, c) for r, c in normal_positions if r in back_rows]
        random.shuffle(back_positions)
        mine_count = 0
        for r, c in back_positions:
            if mine_count >= PIECE_COUNT[PieceType.MINE]:
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(PieceType.MINE, player))
                mine_count += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        if other_hq:
            hq = other_hq[0]
            if board.get_piece(hq[0], hq[1]) is None:
                board.place_piece(hq[0], hq[1], Piece(PieceType.COMMANDER, player))

        flank_c = random.choice([0, 4])
        flank_positions = [(r, c) for r, c in normal_positions if c == flank_c and r in front_rows]
        if not flank_positions:
            flank_positions = [(r, c) for r, c in normal_positions if r in front_rows]
        random.shuffle(flank_positions)
        strong_pieces = [PieceType.ARMY, PieceType.DIVISION, PieceType.BRIGADE]
        for i, (r, c) in enumerate(flank_positions):
            if i >= len(strong_pieces):
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(strong_pieces[i], player))
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        bomb_positions = [(r, c) for r, c in normal_positions if r != front_row]
        random.shuffle(bomb_positions)
        bomb_count = 0
        for r, c in bomb_positions:
            if bomb_count >= PIECE_COUNT[PieceType.BOMB]:
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(PieceType.BOMB, player))
                bomb_count += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        remaining_pieces = []
        for pt, count in PIECE_COUNT.items():
            placed_in_area = 0
            area_rows = list(board.get_player_area_rows(player))
            for r in area_rows:
                for c in range(5):
                    p = board.get_piece(r, c)
                    if p is not None and p.owner == player and p.piece_type == pt:
                        placed_in_area += 1
            for _ in range(count - placed_in_area):
                remaining_pieces.append(pt)
        random.shuffle(remaining_pieces)

        available = [(r, c) for r, c in normal_positions if board.get_piece(r, c) is None]
        random.shuffle(available)
        for pt in remaining_pieces:
            for r, c in available:
                if board.get_piece(r, c) is None:
                    board.place_piece(r, c, Piece(pt, player))
                    available.remove((r, c))
                    break

    def _setup_trap_master(self, board, player):
        self._clear_player_area(board, player)
        hq_positions, normal_positions, front_row, back_rows, front_rows, mid_rows = self._get_area_info(board, player)

        flag_pos = random.choice(hq_positions)
        board.place_piece(flag_pos[0], flag_pos[1], Piece(PieceType.FLAG, player))
        other_hq = [hq for hq in hq_positions if hq != flag_pos]

        back_positions = [(r, c) for r, c in normal_positions if r in back_rows]
        random.shuffle(back_positions)
        mine_count = 0
        for r, c in back_positions:
            if mine_count >= PIECE_COUNT[PieceType.MINE]:
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(PieceType.MINE, player))
                mine_count += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        if other_hq:
            hq = other_hq[0]
            if board.get_piece(hq[0], hq[1]) is None:
                board.place_piece(hq[0], hq[1], Piece(PieceType.COMMANDER, player))

        front_row_positions = [(r, c) for r, c in normal_positions if r == front_row]
        random.shuffle(front_row_positions)
        bait_positions = front_row_positions[:2]
        trap_pieces = [PieceType.PLATOON, PieceType.COMPANY]
        for i, (r, c) in enumerate(bait_positions):
            if i >= len(trap_pieces):
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(trap_pieces[i], player))
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        nearby_positions = [(r, c) for r, c in normal_positions if r in front_rows and board.get_piece(r, c) is None]
        random.shuffle(nearby_positions)
        ambush_pieces = [PieceType.ARMY, PieceType.DIVISION]
        for i, (r, c) in enumerate(nearby_positions):
            if i >= len(ambush_pieces):
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(ambush_pieces[i], player))
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        bomb_positions = [(r, c) for r, c in normal_positions if r != front_row]
        random.shuffle(bomb_positions)
        bomb_count = 0
        for r, c in bomb_positions:
            if bomb_count >= PIECE_COUNT[PieceType.BOMB]:
                break
            if board.get_piece(r, c) is None:
                board.place_piece(r, c, Piece(PieceType.BOMB, player))
                bomb_count += 1
                if (r, c) in normal_positions:
                    normal_positions.remove((r, c))

        remaining_pieces = []
        for pt, count in PIECE_COUNT.items():
            placed_in_area = 0
            area_rows = list(board.get_player_area_rows(player))
            for r in area_rows:
                for c in range(5):
                    p = board.get_piece(r, c)
                    if p is not None and p.owner == player and p.piece_type == pt:
                        placed_in_area += 1
            for _ in range(count - placed_in_area):
                remaining_pieces.append(pt)
        random.shuffle(remaining_pieces)

        available = [(r, c) for r, c in normal_positions if board.get_piece(r, c) is None]
        random.shuffle(available)
        for pt in remaining_pieces:
            for r, c in available:
                if board.get_piece(r, c) is None:
                    board.place_piece(r, c, Piece(pt, player))
                    available.remove((r, c))
                    break

    def get_best_move(self, board, player):
        self._timeout = False
        self._start_time = time.time()
        self._tt.clear()
        self._killer = KillerMoves()
        self._nodes_searched = 0
        self._cutoffs = 0
        self._known_enemy_pieces = {}
        self._track_enemy_pieces(board, player)

        movable = board.get_movable_pieces(player)
        if not movable:
            return None

        opponent = Player.RED if player == Player.BLUE else Player.BLUE

        scored_moves = []
        for r, c, moves in movable:
            for to_r, to_c in moves:
                score = self._evaluate_move_quick(board, player, opponent, r, c, to_r, to_c)
                scored_moves.append((score, r, c, to_r, to_c))

        scored_moves.sort(key=lambda x: x[0], reverse=True)

        best_move = None
        best_score = -float("inf")

        for depth in range(1, self._max_depth + 1):
            if self._timeout:
                break

            current_best = None
            current_best_score = -float("inf")
            alpha = -float("inf")
            beta = float("inf")

            limit = min(len(scored_moves), 30)
            for i in range(limit):
                if self._timeout:
                    break
                _, r, c, to_r, to_c = scored_moves[i]
                board_copy = board.copy()
                self._simulate_move(board_copy, r, c, to_r, to_c)
                score = self._minimax(board_copy, opponent, depth - 1, alpha, beta, False, player)

                if self._timeout:
                    break

                if score > current_best_score:
                    current_best_score = score
                    current_best = (r, c, to_r, to_c)
                if score > alpha:
                    alpha = score

            if not self._timeout and current_best is not None:
                best_move = current_best
                best_score = current_best_score

        if best_move is None and scored_moves:
            best_move = (scored_moves[0][1], scored_moves[0][2], scored_moves[0][3], scored_moves[0][4])

        return best_move

    def _minimax(self, board, current_player, depth, alpha, beta, maximizing, ai_player):
        self._nodes_searched += 1

        if self._timeout or time.time() - self._start_time > self._time_limit:
            self._timeout = True
            return self._evaluate(board, ai_player)

        hash_key = self._compute_zobrist_hash(board)
        tt_entry = self._tt.lookup(hash_key)
        if tt_entry is not None:
            tt_depth, tt_flag, tt_value, tt_move = tt_entry
            if tt_depth >= depth:
                if tt_flag == TT_EXACT:
                    return tt_value
                elif tt_flag == TT_LOWER and tt_value >= beta:
                    return tt_value
                elif tt_flag == TT_UPPER and tt_value <= alpha:
                    return tt_value

        if depth <= 0:
            return self._quiescence_search(board, current_player, alpha, beta, maximizing, ai_player, 3)

        if board.check_flag_captured(current_player):
            opp = Player.RED if current_player == Player.BLUE else Player.BLUE
            return 100000 + depth if opp == ai_player else -100000 - depth

        movable = board.get_movable_pieces(current_player)
        if not movable:
            opp = Player.RED if current_player == Player.BLUE else Player.BLUE
            return 100000 if opp == ai_player else -100000

        opponent = Player.RED if current_player == Player.BLUE else Player.BLUE

        if self._try_null_move(board, current_player, depth, alpha, beta, maximizing, ai_player):
            return beta

        all_moves = []
        for r, c, moves in movable:
            for to_r, to_c in moves:
                move_score = self._order_move_score(board, current_player, opponent, r, c, to_r, to_c, depth)
                all_moves.append((move_score, r, c, to_r, to_c))

        all_moves.sort(key=lambda x: x[0], reverse=maximizing)

        limit = min(len(all_moves), 20)
        best_value = -float("inf") if maximizing else float("inf")
        best_move = None

        for i in range(limit):
            _, r, c, to_r, to_c = all_moves[i]
            board_copy = board.copy()
            self._simulate_move(board_copy, r, c, to_r, to_c)
            child = self._minimax(board_copy, opponent, depth - 1, alpha, beta, not maximizing, ai_player)

            if maximizing:
                if child > best_value:
                    best_value = child
                    best_move = (r, c, to_r, to_c)
                if best_value > alpha:
                    alpha = best_value
            else:
                if child < best_value:
                    best_value = child
                    best_move = (r, c, to_r, to_c)
                if best_value < beta:
                    beta = best_value

            if alpha >= beta:
                self._cutoffs += 1
                if best_move is not None:
                    self._killer.add(depth, best_move)
                break

        if best_move is not None:
            if maximizing:
                flag = TT_LOWER if best_value >= beta else TT_EXACT
            else:
                flag = TT_UPPER if best_value <= alpha else TT_EXACT
            self._tt.store(hash_key, depth, flag, best_value, best_move)

        return best_value

    def _try_null_move(self, board, current_player, depth, alpha, beta, maximizing, ai_player):
        if depth < 3:
            return False
        if not maximizing:
            return False
        total_pieces = 0
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                if board.get_piece(r, c) is not None:
                    total_pieces += 1
        if total_pieces < 15:
            return False

        opponent = Player.RED if current_player == Player.BLUE else Player.BLUE
        null_depth = depth - 3
        if null_depth <= 0:
            return False

        score = self._minimax(board, opponent, null_depth, beta - 1, beta, False, ai_player)
        return score >= beta

    def _quiescence_search(self, board, current_player, alpha, beta, maximizing, ai_player, max_depth):
        stand_pat = self._evaluate(board, ai_player)
        if max_depth <= 0:
            return stand_pat

        if maximizing:
            if stand_pat >= beta:
                return beta
            if stand_pat > alpha:
                alpha = stand_pat
        else:
            if stand_pat <= alpha:
                return alpha
            if stand_pat < beta:
                beta = stand_pat

        opponent = Player.RED if current_player == Player.BLUE else Player.BLUE
        capture_moves = self._get_capture_moves(board, current_player, opponent)

        if not capture_moves:
            return stand_pat

        capture_moves.sort(key=lambda m: m[0], reverse=maximizing)

        for _, r, c, to_r, to_c in capture_moves:
            board_copy = board.copy()
            self._simulate_move(board_copy, r, c, to_r, to_c)
            score = self._quiescence_search(board_copy, opponent, alpha, beta, not maximizing, ai_player, max_depth - 1)

            if maximizing:
                if score > alpha:
                    alpha = score
                if alpha >= beta:
                    break
            else:
                if score < beta:
                    beta = score
                if alpha >= beta:
                    break

        return alpha if maximizing else beta

    def _get_capture_moves(self, board, player, opponent):
        captures = []
        movable = board.get_movable_pieces(player)
        for r, c, moves in movable:
            for to_r, to_c in moves:
                target = board.get_piece(to_r, to_c)
                if target is not None and target.owner == opponent:
                    score = PIECE_VALUES.get(target.piece_type, 0)
                    if target.piece_type == PieceType.FLAG:
                        score = 1000000
                    captures.append((score, r, c, to_r, to_c))
        return captures

    def _order_move_score(self, board, player, opponent, from_r, from_c, to_r, to_c, depth):
        move = (from_r, from_c, to_r, to_c)
        killers = self._killer.get(depth)
        if killers[0] == move:
            return 100000
        if killers[1] == move:
            return 50000

        score = self._evaluate_move_quick(board, player, opponent, from_r, from_c, to_r, to_c)
        return score

    def _simulate_move(self, board, from_r, from_c, to_r, to_c):
        piece = board.get_piece(from_r, from_c)
        target = board.get_piece(to_r, to_c)
        if target is not None:
            result = board.resolve_battle(piece, target)
            if result == "attacker":
                board.remove_piece(to_r, to_c)
                board.move_piece(from_r, from_c, to_r, to_c)
            elif result == "defender":
                board.remove_piece(from_r, from_c)
            elif result == "both":
                board.remove_piece(from_r, from_c)
                board.remove_piece(to_r, to_c)
        else:
            board.move_piece(from_r, from_c, to_r, to_c)

    def _evaluate(self, board, ai_player):
        opponent = Player.RED if ai_player == Player.BLUE else Player.BLUE

        if ai_player == Player.RED:
            enemy_direction = 1
            my_back_row = BOARD_ROWS - 1
            pos_table = POSITIONAL_BONUS_RED
        else:
            enemy_direction = -1
            my_back_row = 0
            pos_table = POSITIONAL_BONUS_BLUE

        total_pieces = 0
        my_value = 0
        opp_value = 0
        my_flag = False
        opp_flag = False
        my_flag_pos = None
        opp_flag_pos = None
        my_piece_count = 0
        opp_piece_count = 0
        advance_score = 0
        positional_score = 0
        my_commander_alive = False
        opp_commander_alive = False
        my_engineer_count = 0
        opp_engineer_count = 0

        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is None:
                    continue
                total_pieces += 1
                val = PIECE_VALUES.get(p.piece_type, 0)
                if p.owner == ai_player:
                    my_piece_count += 1
                    my_value += val
                    if p.piece_type == PieceType.FLAG:
                        my_flag = True
                        my_flag_pos = (r, c)
                    elif p.piece_type == PieceType.COMMANDER:
                        my_commander_alive = True
                    elif p.piece_type == PieceType.ENGINEER:
                        my_engineer_count += 1
                    else:
                        if enemy_direction == 1:
                            advance_score += (my_back_row - r) * ADVANCE_WEIGHT
                        else:
                            advance_score += (r - my_back_row) * ADVANCE_WEIGHT
                    positional_score += pos_table.get((r, c), 0)
                    ct = board.get_cell_type(r, c)
                    if ct == CellType.CAMP:
                        my_value += CAMP_BONUS
                    if p.piece_type == PieceType.ENGINEER:
                        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            nr, nc = r + dr, c + dc
                            if board.is_valid_position(nr, nc):
                                np = board.get_piece(nr, nc)
                                if np is not None and np.owner == opponent and np.piece_type == PieceType.MINE:
                                    my_value += ENGINEER_MINE_BONUS
                else:
                    opp_piece_count += 1
                    opp_value += val
                    if p.piece_type == PieceType.FLAG:
                        opp_flag = True
                        opp_flag_pos = (r, c)
                    elif p.piece_type == PieceType.COMMANDER:
                        opp_commander_alive = True
                    elif p.piece_type == PieceType.ENGINEER:
                        opp_engineer_count += 1
                    ct = board.get_cell_type(r, c)
                    if ct == CellType.CAMP:
                        opp_value += CAMP_BONUS

        if not my_flag:
            return -100000
        if not opp_flag:
            return 100000

        my_mobility = len(board.get_movable_pieces(ai_player))
        opp_mobility = len(board.get_movable_pieces(opponent))
        mobility_score = (my_mobility - opp_mobility) * MOBILITY_WEIGHT

        if my_flag_pos:
            fr, fc = my_flag_pos
            protect_score = 0
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = fr + dr, fc + dc
                if board.is_valid_position(nr, nc):
                    p = board.get_piece(nr, nc)
                    if p is not None and p.owner == ai_player and p.piece_type != PieceType.FLAG:
                        protect_score += FLAG_PROTECTION_BONUS
                    if p is not None and p.owner == opponent:
                        protect_score -= 60
            my_value += protect_score

        commander_score = 0
        if my_commander_alive and not opp_commander_alive:
            commander_score += COMMANDER_SAFETY_BONUS * 2
        elif not my_commander_alive and opp_commander_alive:
            commander_score -= COMMANDER_SAFETY_BONUS * 2

        engineer_score = (my_engineer_count - opp_engineer_count) * 30

        total_score = (my_value - opp_value) + mobility_score + advance_score + positional_score + commander_score + engineer_score

        if total_pieces < 20:
            if my_commander_alive and opp_commander_alive:
                total_score += my_value * 0.05
            if my_engineer_count > opp_engineer_count:
                total_score += (my_engineer_count - opp_engineer_count) * 50

        return total_score

    def _evaluate_move_quick(self, board, player, opponent, from_r, from_c, to_r, to_c):
        piece = board.get_piece(from_r, from_c)
        target = board.get_piece(to_r, to_c)
        score = 0

        if player == Player.RED:
            enemy_direction = 1
        else:
            enemy_direction = -1

        if target is not None:
            known_target = self._get_known_enemy_at(to_r, to_c)
            result = board.resolve_battle(piece, target)
            if result == "attacker":
                if target.piece_type == PieceType.FLAG:
                    score += 1000000
                elif target.piece_type == PieceType.MINE:
                    if piece.piece_type == PieceType.ENGINEER:
                        score += PIECE_VALUES.get(target.piece_type, 0) + 250
                    else:
                        score += PIECE_VALUES.get(target.piece_type, 0) - 100
                else:
                    captured_val = PIECE_VALUES.get(target.piece_type, 0)
                    score += captured_val
                    if target.piece_type in (PieceType.COMMANDER, PieceType.ARMY):
                        score += 150
                    if known_target is not None:
                        score += 50
            elif result == "defender":
                score -= PIECE_VALUES.get(piece.piece_type, 0)
                if piece.piece_type in (PieceType.COMMANDER, PieceType.ARMY):
                    score -= 250
            elif result == "both":
                attacker_val = PIECE_VALUES.get(piece.piece_type, 0)
                defender_val = PIECE_VALUES.get(target.piece_type, 0)
                if piece.piece_type == PieceType.BOMB:
                    if target.piece_type in (PieceType.COMMANDER, PieceType.ARMY, PieceType.DIVISION):
                        score += 400
                    else:
                        score += defender_val - attacker_val
                else:
                    score += defender_val - attacker_val
        else:
            to_cell = board.get_cell_type(to_r, to_c)
            if to_cell == CellType.CAMP:
                score += 50
            if piece.piece_type == PieceType.ENGINEER:
                score += 8
            if enemy_direction == 1:
                if to_r < from_r:
                    score += 8
                elif to_r > from_r:
                    score -= 5
            else:
                if to_r > from_r:
                    score += 8
                elif to_r < from_r:
                    score -= 5
            if piece.piece_type in (PieceType.PLATOON, PieceType.COMPANY, PieceType.BATTALION):
                score += 5

        if piece.piece_type == PieceType.ENGINEER:
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = to_r + dr, to_c + dc
                if board.is_valid_position(nr, nc):
                    p = board.get_piece(nr, nc)
                    if p is not None and p.owner == opponent and p.piece_type == PieceType.MINE:
                        score += 180

        threat_score = self._is_threatening_flag(board, player, to_r, to_c)
        if threat_score > 0:
            score += threat_score

        if self._exposes_valuable_piece(board, player, from_r, from_c, to_r, to_c):
            score -= 500

        if self._is_piece_in_danger(board, player, to_r, to_c, piece):
            score -= 250

        if self._will_be_in_danger(board, player, opponent, from_r, from_c, to_r, to_c):
            score -= 300

        return score

    def _will_be_in_danger(self, board, player, opponent, from_r, from_c, to_r, to_c):
        piece = board.get_piece(from_r, from_c)
        if piece is None or piece.piece_type in (PieceType.FLAG, PieceType.MINE):
            return False

        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            er, ec = to_r + dr, to_c + dc
            if not board.is_valid_position(er, ec):
                continue
            old_piece = board.get_piece(er, ec)
            if old_piece is not None and old_piece.owner == player:
                continue
            ep = board.get_piece(er, ec)
            if ep is not None and ep.owner == opponent:
                battle = board.resolve_battle(ep, piece)
                if battle == "attacker":
                    return True
        return False

    def _is_threatening_flag(self, board, player, to_r, to_c):
        opponent = Player.RED if player == Player.BLUE else Player.BLUE
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is not None and p.owner == opponent and p.piece_type == PieceType.FLAG:
                    distance = abs(to_r - r) + abs(to_c - c)
                    if distance <= 3:
                        return 120 * (4 - distance)
        return 0

    def _exposes_valuable_piece(self, board, player, from_r, from_c, to_r, to_c):
        piece = board.get_piece(from_r, from_c)
        if piece is None:
            return False
        if piece.piece_type in (PieceType.COMMANDER, PieceType.ARMY, PieceType.FLAG):
            opponent = Player.RED if player == Player.BLUE else Player.BLUE
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = to_r + dr, to_c + dc
                if board.is_valid_position(nr, nc):
                    p = board.get_piece(nr, nc)
                    if p is not None and p.owner == opponent:
                        if p.piece_type in (PieceType.BOMB, PieceType.COMMANDER, PieceType.ARMY):
                            return True
        return False

    def _is_piece_in_danger(self, board, player, r, c, piece):
        if piece.piece_type in (PieceType.FLAG, PieceType.MINE):
            return False
        opponent = Player.RED if player == Player.BLUE else Player.BLUE
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if board.is_valid_position(nr, nc):
                ct = board.get_cell_type(nr, nc)
                if ct == CellType.CAMP:
                    continue
                p = board.get_piece(nr, nc)
                if p is not None and p.owner == opponent:
                    result = board.resolve_battle(p, piece)
                    if result == "attacker":
                        return True
        return False