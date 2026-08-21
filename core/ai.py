import random
import time
import math

from config import BOARD_ROWS, BOARD_COLS
from core.board import Piece, CellType
from core.player import Player, PieceType, PIECE_RANK

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
        deep_advance = max(0, 12 - r)
        center = 2 - abs(c - 2)
        POSITIONAL_BONUS_RED[(r, c)] = advance * 3 + center * 2 + deep_advance * 5

POSITIONAL_BONUS_BLUE = {}
for r in range(BOARD_ROWS):
    for c in range(BOARD_COLS):
        advance = max(0, r - 7)
        deep_advance = max(0, r - 1)
        center = 2 - abs(c - 2)
        POSITIONAL_BONUS_BLUE[(r, c)] = advance * 3 + center * 2 + deep_advance * 5

COMMANDER_SAFETY_BONUS = 80
FLAG_PROTECTION_BONUS = 40
ENGINEER_MINE_BONUS = 120
CAMP_BONUS = 30
CAMP_STRONG_BONUS = 40
MOBILITY_WEIGHT = 18
ADVANCE_WEIGHT = 3
RAIL_CONTROL_BONUS = 25
COMMANDER_EXPOSED_PENALTY = 120
ENGINEER_ENDGAME_VALUE = 80
FLAG_ATTACK_BONUS = 60
THREAT_FACTOR = 0.5

KEY_RAILWAY_ROWS = (5, 6, 7)
KEY_RAILWAY_COLS = (0, 4)

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

FUTILITY_MARGIN = [0, 80, 160, 240, 350, 500, 700, 900, 1200]
RAZOR_MARGIN = [0, 200, 400, 600, 850, 1100, 1400, 1800, 2200]
PROBCUT_MARGIN = 200
PROBCUT_REDUCTION = 3
ASPIRATION_DELTA = 50
ASPIRATION_MAX = 800


class TranspositionTable:
    def __init__(self, max_size=500000):
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
    def __init__(self, max_depth=24):
        self._moves = [[None, None] for _ in range(max_depth)]

    def add(self, depth, move):
        if depth >= len(self._moves):
            return
        if self._moves[depth][0] != move:
            self._moves[depth][1] = self._moves[depth][0]
            self._moves[depth][0] = move

    def get(self, depth):
        if depth >= len(self._moves):
            return [None, None]
        return self._moves[depth]


STRONG_PIECE_TYPES = (
    PieceType.BRIGADE,
    PieceType.DIVISION,
    PieceType.ARMY,
    PieceType.COMMANDER,
)


class OpponentModel:
    def __init__(self):
        self._move_history = []
        self._capture_history = []
        self._aggression_score = 50
        self._defensive_score = 50
        self._piece_usage = {}
        self._flag_attack_attempts = 0
        self._bomb_usage = 0
        self._engineer_usage = 0
        self._commander_aggression = 0

    def record_move(self, from_r, from_c, to_r, to_c, piece_type, captured_type=None):
        self._move_history.append((from_r, from_c, to_r, to_c, piece_type, captured_type))
        if captured_type is not None:
            self._capture_history.append(captured_type)
            self._aggression_score = min(100, self._aggression_score + 2)
        else:
            self._defensive_score = min(100, self._defensive_score + 1)

        if piece_type == PieceType.BOMB:
            self._bomb_usage += 1
        elif piece_type == PieceType.ENGINEER:
            self._engineer_usage += 1
        elif piece_type == PieceType.COMMANDER:
            self._commander_aggression += 1

        self._piece_usage[piece_type] = self._piece_usage.get(piece_type, 0) + 1

    def get_style(self):
        if self._aggression_score > 65:
            return "aggressive"
        elif self._defensive_score > 65:
            return "defensive"
        return "balanced"

    def get_commander_likely_exposed(self):
        return self._commander_aggression > 3

    def get_bomb_likely_used(self):
        return self._bomb_usage > 0

    def clear(self):
        self._move_history = []
        self._capture_history = []
        self._aggression_score = 50
        self._defensive_score = 50
        self._piece_usage = {}
        self._flag_attack_attempts = 0
        self._bomb_usage = 0
        self._engineer_usage = 0
        self._commander_aggression = 0


class MilitaryChessAI:
    def __init__(self):
        self._max_depth = 10
        self._time_limit = 8.0
        self._start_time = 0
        self._timeout = False
        self._tt = TranspositionTable()
        self._killer = KillerMoves()
        self._history = {}
        self._known_enemy_pieces = {}
        self._nodes_searched = 0
        self._cutoffs = 0
        self._opponent_model = OpponentModel()
        self._layout_history = []
        self._last_layout_type = None
        self._move_count = 0
        self._game_phase_tracker = "opening"
        self._aspiration_fail_count = 0
        self._see_cache = {}

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
        self._known_enemy_pieces = {}
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is not None and p.owner == opponent:
                    self._known_enemy_pieces[(r, c)] = (p.piece_type, p.owner)

    def _get_known_enemy_at(self, r, c):
        return self._known_enemy_pieces.get((r, c), None)

    def auto_setup(self, board, player):
        self._strategic_setup(board, player)

    def _clear_player_area(self, board, player):
        area_rows = list(board.get_player_area_rows(player))
        for r in area_rows:
            for c in range(5):
                if board.get_piece(r, c) is not None:
                    board.remove_piece(r, c)

    def _strategic_setup(self, board, player):
        self._clear_player_area(board, player)

        opponent_style = self._opponent_model.get_style()
        if self._last_layout_type is not None and self._opponent_model._aggression_score > 60:
            layout_type = random.choice(["defensive_fortress", "balanced", "mine_heavy"])
        elif opponent_style == "aggressive":
            layout_type = random.choice(["defensive_fortress", "trap_master", "mine_heavy"])
        elif opponent_style == "defensive":
            layout_type = random.choice(["aggressive_push", "flank_attack", "balanced"])
        else:
            layout_type = random.choice([
                "balanced", "aggressive_push", "defensive_fortress",
                "flank_attack", "trap_master", "mine_heavy"
            ])

        self._last_layout_type = layout_type
        self._layout_history.append(layout_type)

        if player == Player.RED:
            row_map = lambda r: r
        else:
            row_map = lambda r: 12 - r

        if layout_type == "aggressive_push":
            layout = self._layout_aggressive_push()
        elif layout_type == "defensive_fortress":
            layout = self._layout_defensive_fortress()
        elif layout_type == "flank_attack":
            layout = self._layout_flank_attack()
        elif layout_type == "trap_master":
            layout = self._layout_trap_master()
        elif layout_type == "mine_heavy":
            layout = self._layout_mine_heavy()
        else:
            layout = self._layout_balanced()

        flag_col = random.choice([1, 3])
        if flag_col == 1:
            col_map = lambda c: c
        else:
            col_map = lambda c: 4 - c

        for pt, positions in layout.items():
            mapped = [(row_map(r), col_map(c)) for (r, c) in positions]
            random.shuffle(mapped)
            for (r, c) in mapped:
                if board.get_piece(r, c) is None:
                    board.place_piece(r, c, Piece(pt, player))

    def _layout_balanced(self):
        return {
            PieceType.FLAG: [(12, 1)],
            PieceType.COMMANDER: [(12, 4)],
            PieceType.MINE: [(11, 1), (12, 0), (12, 2)],
            PieceType.BOMB: [(11, 2), (9, 1)],
            PieceType.ARMY: [(9, 3)],
            PieceType.DIVISION: [(8, 0), (8, 4)],
            PieceType.BRIGADE: [(10, 0), (10, 4)],
            PieceType.REGIMENT: [(8, 2), (10, 2)],
            PieceType.BATTALION: [(7, 2), (11, 3)],
            PieceType.ENGINEER: [(7, 0), (7, 4), (9, 0)],
            PieceType.COMPANY: [(7, 1), (9, 4), (11, 0)],
            PieceType.PLATOON: [(7, 3), (11, 4), (12, 3)],
        }

    def _layout_aggressive_push(self):
        return {
            PieceType.FLAG: [(12, 1)],
            PieceType.COMMANDER: [(10, 2)],
            PieceType.MINE: [(11, 1), (12, 0), (12, 2)],
            PieceType.BOMB: [(8, 2), (11, 3)],
            PieceType.ARMY: [(7, 2)],
            PieceType.DIVISION: [(7, 0), (7, 4)],
            PieceType.BRIGADE: [(8, 0), (8, 4)],
            PieceType.REGIMENT: [(9, 1), (9, 3)],
            PieceType.BATTALION: [(9, 0), (9, 4)],
            PieceType.ENGINEER: [(7, 1), (7, 3), (10, 0)],
            PieceType.COMPANY: [(10, 4), (11, 0), (11, 4)],
            PieceType.PLATOON: [(11, 2), (12, 4), (12, 3)],
    }

    def _layout_defensive_fortress(self):
        return {
            PieceType.FLAG: [(12, 1)],
            PieceType.COMMANDER: [(12, 4)],
            PieceType.MINE: [(11, 0), (11, 1), (12, 0)],
            PieceType.BOMB: [(11, 3), (11, 4)],
            PieceType.ARMY: [(10, 2)],
            PieceType.DIVISION: [(10, 0), (10, 4)],
            PieceType.BRIGADE: [(9, 0), (9, 4)],
            PieceType.REGIMENT: [(9, 1), (9, 3)],
            PieceType.BATTALION: [(8, 0), (8, 4)],
            PieceType.ENGINEER: [(7, 0), (7, 4), (8, 2)],
            PieceType.COMPANY: [(7, 1), (7, 3), (12, 2)],
            PieceType.PLATOON: [(7, 2), (11, 2), (12, 3)],
    }

    def _layout_flank_attack(self):
        return {
            PieceType.FLAG: [(12, 1)],
            PieceType.COMMANDER: [(12, 4)],
            PieceType.MINE: [(11, 1), (12, 0), (12, 2)],
            PieceType.BOMB: [(11, 2), (9, 1)],
            PieceType.ARMY: [(7, 4)],
            PieceType.DIVISION: [(7, 0), (8, 4)],
            PieceType.BRIGADE: [(8, 0), (9, 4)],
            PieceType.REGIMENT: [(9, 0), (10, 4)],
            PieceType.BATTALION: [(10, 0), (11, 4)],
            PieceType.ENGINEER: [(7, 1), (7, 3), (12, 3)],
            PieceType.COMPANY: [(7, 2), (8, 2), (10, 2)],
            PieceType.PLATOON: [(9, 3), (11, 3), (11, 0)],
    }

    def _layout_trap_master(self):
        return {
            PieceType.FLAG: [(12, 1)],
            PieceType.COMMANDER: [(12, 4)],
            PieceType.MINE: [(11, 1), (12, 0), (12, 2)],
            PieceType.BOMB: [(7, 2), (11, 2)],
            PieceType.ARMY: [(10, 2)],
            PieceType.DIVISION: [(8, 0), (8, 4)],
            PieceType.BRIGADE: [(9, 0), (9, 4)],
            PieceType.REGIMENT: [(7, 0), (7, 4)],
            PieceType.BATTALION: [(10, 0), (10, 4)],
            PieceType.ENGINEER: [(7, 1), (7, 3), (11, 4)],
            PieceType.COMPANY: [(8, 2), (11, 3), (11, 0)],
            PieceType.PLATOON: [(9, 1), (9, 3), (12, 3)],
    }

    def _layout_mine_heavy(self):
        return {
            PieceType.FLAG: [(12, 1)],
            PieceType.COMMANDER: [(12, 4)],
            PieceType.MINE: [(11, 1), (11, 2), (12, 2)],
            PieceType.BOMB: [(11, 0), (11, 4)],
            PieceType.ARMY: [(10, 2)],
            PieceType.DIVISION: [(9, 0), (9, 4)],
            PieceType.BRIGADE: [(8, 0), (8, 4)],
            PieceType.REGIMENT: [(10, 0), (10, 4)],
            PieceType.BATTALION: [(7, 0), (7, 4)],
            PieceType.ENGINEER: [(7, 1), (7, 3), (12, 0)],
            PieceType.COMPANY: [(7, 2), (8, 2), (11, 3)],
            PieceType.PLATOON: [(9, 1), (9, 3), (12, 3)],
    }

    def _compute_adaptive_time(self, board, phase):
        total_pieces = 0
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                if board.get_piece(r, c) is not None:
                    total_pieces += 1

        if phase == "opening":
            base_time = 2.0
        elif phase == "midgame":
            base_time = self._time_limit * 0.35
        else:
            base_time = self._time_limit * 0.45

        move_count = self._move_count
        if move_count < 10:
            time_factor = 0.6
        elif move_count < 20:
            time_factor = 1.0
        elif move_count < 35:
            time_factor = 1.3
        else:
            time_factor = 1.5

        complexity = total_pieces / 30.0
        adaptive_time = base_time * time_factor * complexity
        return min(adaptive_time, self._time_limit * 0.9)

    def get_best_move(self, board, player):
        self._timeout = False
        self._start_time = time.time()
        self._tt.clear()
        self._killer = KillerMoves()
        self._history = {}
        self._nodes_searched = 0
        self._cutoffs = 0
        self._known_enemy_pieces = {}
        self._see_cache = {}
        self._track_enemy_pieces(board, player)
        self._move_count += 1

        movable = board.get_movable_pieces(player)
        if not movable:
            return None

        opponent = Player.RED if player == Player.BLUE else Player.BLUE

        root_moves = []
        for r, c, moves in movable:
            for to_r, to_c in moves:
                score = self._evaluate_move_quick(board, player, opponent, r, c, to_r, to_c)
                root_moves.append((score, r, c, to_r, to_c))

        if not root_moves:
            return None

        total_pieces = 0
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                if board.get_piece(r, c) is not None:
                    total_pieces += 1
        phase = self._game_phase(total_pieces)
        self._game_phase_tracker = phase

        adaptive_time = self._compute_adaptive_time(board, phase)
        self._time_limit = adaptive_time

        best_move = None
        best_score = -float("inf")
        pv_move = None
        prev_score = 0
        alpha = -float("inf")
        beta = float("inf")

        for depth in range(1, self._max_depth + 1):
            if self._timeout:
                break

            if depth >= 3 and prev_score != 0:
                alpha = prev_score - ASPIRATION_DELTA - self._aspiration_fail_count * 100
                beta = prev_score + ASPIRATION_DELTA + self._aspiration_fail_count * 100
                if alpha < -90000:
                    alpha = -float("inf")
                if beta > 90000:
                    beta = float("inf")
            else:
                alpha = -float("inf")
                beta = float("inf")

            ordered = list(root_moves)
            if pv_move is not None:
                for i in range(len(ordered)):
                    s, r, c, to_r, to_c = ordered[i]
                    if (r, c, to_r, to_c) == pv_move:
                        ordered[i] = (s + 200000, r, c, to_r, to_c)
                        break
            ordered.sort(key=lambda x: x[0], reverse=True)

            current_best = None
            current_best_score = -float("inf")
            local_alpha = alpha
            local_beta = beta

            limit = min(len(ordered), 35)
            for i in range(limit):
                if self._timeout:
                    break
                _, r, c, to_r, to_c = ordered[i]
                move = (r, c, to_r, to_c)
                board_copy = board.copy()
                self._simulate_move(board_copy, r, c, to_r, to_c)

                if i == 0:
                    score = self._minimax(board_copy, opponent, depth - 1, local_alpha, local_beta, False, player)
                else:
                    score = self._minimax(board_copy, opponent, depth - 1, local_alpha, local_alpha + 1, False, player)
                    if local_alpha < score < local_beta:
                        score = self._minimax(board_copy, opponent, depth - 1, local_alpha, local_beta, False, player)

                if self._timeout:
                    break

                if score > current_best_score:
                    current_best_score = score
                    current_best = move
                if score > local_alpha:
                    local_alpha = score

            if self._timeout:
                break

            if current_best is not None:
                if current_best_score <= alpha or current_best_score >= beta:
                    self._aspiration_fail_count += 1
                    if self._aspiration_fail_count > 3:
                        alpha = -float("inf")
                        beta = float("inf")
                        self._aspiration_fail_count = 0
                        continue
                else:
                    self._aspiration_fail_count = 0

                best_move = current_best
                best_score = current_best_score
                pv_move = current_best
                prev_score = current_best_score

        if best_move is None:
            for s, r, c, to_r, to_c in root_moves:
                best_move = (r, c, to_r, to_c)
                break

        if best_move is not None:
            fr, fc, tr, tc = best_move
            piece = board.get_piece(fr, fc)
            target = board.get_piece(tr, tc)
            if piece is not None:
                cap_type = target.piece_type if target is not None else None
                self._opponent_model.record_move(fr, fc, tr, tc, piece.piece_type, cap_type)

        return best_move

    def _minimax(self, board, current_player, depth, alpha, beta, maximizing, ai_player, tt_move=None):
        self._nodes_searched += 1

        if self._nodes_searched % 2048 == 0:
            if time.time() - self._start_time > self._time_limit:
                self._timeout = True
        if self._timeout:
            return self._evaluate(board, ai_player)

        hash_key = self._compute_zobrist_hash(board)
        tt_entry = self._tt.lookup(hash_key)
        if tt_entry is not None and tt_move is None:
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

        static_eval = self._evaluate(board, ai_player)

        if depth <= 3 and not maximizing:
            futility_margin = FUTILITY_MARGIN[min(depth, len(FUTILITY_MARGIN) - 1)]
            if static_eval - futility_margin >= beta:
                return static_eval - futility_margin

        if depth <= 2 and not maximizing:
            razor_margin = RAZOR_MARGIN[min(depth, len(RAZOR_MARGIN) - 1)]
            if static_eval + razor_margin <= alpha:
                q_score = self._quiescence_search(board, current_player, alpha, beta, True, ai_player, 1)
                if q_score <= alpha:
                    return q_score

        if depth >= 3 and maximizing:
            if self._try_null_move(board, current_player, depth, alpha, beta, maximizing, ai_player):
                return beta

        if depth >= 4 and tt_move is None:
            probe_depth = depth - PROBCUT_REDUCTION
            if probe_depth > 0:
                threshold = beta + PROBCUT_MARGIN
                probe_score = self._minimax(board, current_player, probe_depth, threshold - 1, threshold, maximizing, ai_player)
                if probe_score >= threshold:
                    return beta

        all_moves = []
        for r, c, moves in movable:
            for to_r, to_c in moves:
                move_score = self._order_move_score(board, current_player, opponent, r, c, to_r, to_c, depth, tt_move)
                all_moves.append((move_score, r, c, to_r, to_c))

        all_moves.sort(key=lambda x: x[0], reverse=True)

        if len(all_moves) == 0:
            opp = Player.RED if current_player == Player.BLUE else Player.BLUE
            return 100000 if opp == ai_player else -100000

        limit = min(len(all_moves), 28)
        best_value = -float("inf") if maximizing else float("inf")
        best_move = None

        LMR_THRESHOLD = 6
        for i in range(limit):
            _, r, c, to_r, to_c = all_moves[i]
            move = (r, c, to_r, to_c)
            target = board.get_piece(to_r, to_c)
            is_capture = target is not None
            killers = self._killer.get(depth)
            is_killer = (killers[0] == move or killers[1] == move)
            is_tt_move = (tt_move is not None and move == tt_move)

            board_copy = board.copy()
            self._simulate_move(board_copy, r, c, to_r, to_c)

            new_depth = depth - 1
            reduced = False
            if i >= LMR_THRESHOLD and depth >= 3 and not is_capture and not is_killer and not is_tt_move:
                reduction = 1
                if i >= LMR_THRESHOLD + 4:
                    reduction = 2
                new_depth = max(0, depth - 1 - reduction)
                reduced = True

            if i == 0:
                child = self._minimax(board_copy, opponent, new_depth, alpha, beta, not maximizing, ai_player)
            else:
                if maximizing:
                    child = self._minimax(board_copy, opponent, new_depth, alpha, alpha + 1, not maximizing, ai_player)
                    if alpha < child < beta:
                        child = self._minimax(board_copy, opponent, depth - 1, alpha, beta, not maximizing, ai_player)
                else:
                    child = self._minimax(board_copy, opponent, new_depth, beta - 1, beta, not maximizing, ai_player)
                    if alpha < child < beta:
                        child = self._minimax(board_copy, opponent, depth - 1, alpha, beta, not maximizing, ai_player)

            if self._timeout:
                break

            if maximizing:
                if child > best_value:
                    best_value = child
                    best_move = move
                if best_value > alpha:
                    alpha = best_value
            else:
                if child < best_value:
                    best_value = child
                    best_move = move
                if best_value < beta:
                    beta = best_value

            if alpha >= beta:
                self._cutoffs += 1
                if not is_capture and best_move is not None:
                    self._killer.add(depth, best_move)
                    self._history[best_move] = self._history.get(best_move, 0) + depth * depth
                break

        if best_move is not None and not self._timeout:
            if maximizing:
                flag = TT_LOWER if best_value >= beta else TT_EXACT
            else:
                flag = TT_UPPER if best_value <= alpha else TT_EXACT
            self._tt.store(hash_key, depth, flag, best_value, best_move)

        return best_value

    def _try_null_move(self, board, current_player, depth, alpha, beta, maximizing, ai_player):
        if depth < 3 or not maximizing:
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
            attacker = board.get_piece(r, c)
            if attacker is None:
                continue
            atk_val = PIECE_VALUES.get(attacker.piece_type, 0)
            atk_rank = PIECE_RANK.get(attacker.piece_type, 0)
            for to_r, to_c in moves:
                target = board.get_piece(to_r, to_c)
                if target is not None and target.owner == opponent:
                    if target.piece_type == PieceType.FLAG:
                        score = 1000000
                    else:
                        def_val = PIECE_VALUES.get(target.piece_type, 0)
                        def_rank = PIECE_RANK.get(target.piece_type, 0)
                        result = board.resolve_battle(attacker, target)
                        if result == "attacker":
                            score = def_val * 10 - atk_val
                        elif result == "both":
                            score = def_val - atk_val
                        else:
                            continue
                    captures.append((score, r, c, to_r, to_c))
        return captures

    def _order_move_score(self, board, player, opponent, from_r, from_c, to_r, to_c, depth, tt_move=None):
        move = (from_r, from_c, to_r, to_c)
        if tt_move is not None and move == tt_move:
            return 200000
        killers = self._killer.get(depth)
        if killers[0] == move:
            return 100000
        if killers[1] == move:
            return 50000

        target = board.get_piece(to_r, to_c)
        if target is not None and target.owner == opponent:
            attacker = board.get_piece(from_r, from_c)
            if target.piece_type == PieceType.FLAG:
                return 150000
            result = board.resolve_battle(attacker, target)
            mvv = PIECE_VALUES.get(target.piece_type, 0)
            lva = PIECE_VALUES.get(attacker.piece_type, 0) if attacker else 0
            if result == "attacker":
                see_score = self._see(board, player, from_r, from_c, to_r, to_c)
                return 40000 + mvv * 10 - lva + see_score
            elif result == "both":
                return 20000 + mvv - lva
            else:
                return -mvv * 5

        hist = self._history.get(move, 0)
        if hist > 0:
            return 30000 + min(hist, 20000)

        return self._evaluate_move_quick(board, player, opponent, from_r, from_c, to_r, to_c)

    def _see(self, board, player, from_r, from_c, to_r, to_c):
        cache_key = (from_r, from_c, to_r, to_c)
        if cache_key in self._see_cache:
            return self._see_cache[cache_key]

        attacker = board.get_piece(from_r, from_c)
        target = board.get_piece(to_r, to_c)
        if attacker is None or target is None:
            return 0

        result = board.resolve_battle(attacker, target)
        gain = 0

        if result == "attacker":
            gain = PIECE_VALUES.get(target.piece_type, 0)
        elif result == "both":
            gain = PIECE_VALUES.get(target.piece_type, 0) - PIECE_VALUES.get(attacker.piece_type, 0)
        else:
            gain = -PIECE_VALUES.get(attacker.piece_type, 0) * 2

        if gain > 200:
            gain += 30
        elif gain < -200:
            gain -= 30

        self._see_cache[cache_key] = gain
        return gain

    def _simulate_move(self, board, from_r, from_c, to_r, to_c):
        piece = board.get_piece(from_r, from_c)
        target = board.get_piece(to_r, to_c)
        if target is not None:
            result = board.resolve_battle(piece, target)
            if result == "attacker":
                piece.visible = True
                target.visible = True
                board.remove_piece(to_r, to_c)
                board.move_piece(from_r, from_c, to_r, to_c)
            elif result == "defender":
                piece.visible = True
                target.visible = True
                board.remove_piece(from_r, from_c)
            elif result == "both":
                piece.visible = True
                target.visible = True
                board.remove_piece(from_r, from_c)
                board.remove_piece(to_r, to_c)
        else:
            piece.visible = True
            board.move_piece(from_r, from_c, to_r, to_c)

    def _game_phase(self, total_pieces):
        if total_pieces > 30:
            return "opening"
        elif total_pieces > 15:
            return "midgame"
        else:
            return "endgame"

    def _threat_score(self, board, ai_player):
        opponent = Player.RED if ai_player == Player.BLUE else Player.BLUE
        score = 0
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is None:
                    continue
                if p.piece_type in (PieceType.FLAG, PieceType.MINE):
                    continue
                ct = board.get_cell_type(r, c)
                if ct == CellType.CAMP:
                    continue
                val = PIECE_VALUES.get(p.piece_type, 0)
                threatened = False
                can_attack = False
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if not board.is_valid_position(nr, nc):
                        continue
                    nct = board.get_cell_type(nr, nc)
                    if nct == CellType.CAMP:
                        continue
                    ep = board.get_piece(nr, nc)
                    if ep is None:
                        continue
                    if ep.owner == opponent and p.owner == ai_player:
                        if board.resolve_battle(ep, p) == "attacker":
                            threatened = True
                    elif ep.owner == ai_player and p.owner == opponent:
                        if board.resolve_battle(ep, p) == "attacker":
                            can_attack = True
                if p.owner == ai_player:
                    if threatened:
                        score -= int(val * THREAT_FACTOR)
                else:
                    if can_attack:
                        score += int(val * THREAT_FACTOR)
        return score

    def _coordination_score(self, board, ai_player):
        opponent = Player.RED if ai_player == Player.BLUE else Player.BLUE
        score = 0
        strong_positions = []
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is not None and p.owner == ai_player and p.piece_type in STRONG_PIECE_TYPES:
                    strong_positions.append((r, c, p))

        for i in range(len(strong_positions)):
            for j in range(i + 1, len(strong_positions)):
                r1, c1, p1 = strong_positions[i]
                r2, c2, p2 = strong_positions[j]
                dist = abs(r1 - r2) + abs(c1 - c2)
                if dist <= 3:
                    score += 15
                if dist <= 2:
                    score += 25

        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is not None and p.owner == ai_player and p.piece_type == PieceType.ENGINEER:
                    for r2, c2, p2 in strong_positions:
                        if abs(r - r2) + abs(c - c2) <= 4:
                            score += 10
                            break

        return score

    def _trap_detection_score(self, board, ai_player):
        opponent = Player.RED if ai_player == Player.BLUE else Player.BLUE
        score = 0

        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is None or p.owner != ai_player:
                    continue
                if p.piece_type in (PieceType.FLAG, PieceType.MINE, PieceType.BOMB):
                    continue

                ct = board.get_cell_type(r, c)
                if ct == CellType.CAMP:
                    continue

                threatening = 0
                protecting = 0
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if not board.is_valid_position(nr, nc):
                        continue
                    nct = board.get_cell_type(nr, nc)
                    if nct == CellType.CAMP:
                        continue
                    np = board.get_piece(nr, nc)
                    if np is None:
                        continue
                    if np.owner == opponent:
                        result = board.resolve_battle(np, p)
                        if result == "attacker":
                            threatening += 1
                    elif np.owner == ai_player:
                        result = board.resolve_battle(p, np)
                        if result == "attacker":
                            protecting += 1

                if threatening > 0 and protecting == 0:
                    val = PIECE_VALUES.get(p.piece_type, 0)
                    score -= int(val * 0.6)
                elif threatening > 0 and protecting >= threatening:
                    score += 30

        return score

    def _flag_attack_score(self, board, ai_player):
        opponent = Player.RED if ai_player == Player.BLUE else Player.BLUE
        flag_pos = None
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is not None and p.owner == opponent and p.piece_type == PieceType.FLAG:
                    flag_pos = (r, c)
                    break
            if flag_pos:
                break
        if flag_pos is None:
            return 0
        fr, fc = flag_pos
        score = 0
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is None or p.owner != ai_player:
                    continue
                if p.piece_type in (PieceType.FLAG, PieceType.MINE):
                    continue
                dist = abs(r - fr) + abs(c - fc)
                if dist <= 6:
                    val = PIECE_VALUES.get(p.piece_type, 0)
                    rank = PIECE_RANK.get(p.piece_type, 0)
                    if rank > 0:
                        score += int(val * 0.2) * (7 - dist)
                    else:
                        score += int(val * 0.1) * (7 - dist)
        return score

    def _opponent_adaptation_score(self, board, ai_player):
        opponent = Player.RED if ai_player == Player.BLUE else Player.BLUE
        score = 0

        style = self._opponent_model.get_style()
        if style == "aggressive":
            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    p = board.get_piece(r, c)
                    if p is None or p.owner != ai_player:
                        continue
                    if p.piece_type in (PieceType.BOMB, PieceType.MINE):
                        continue
                    ct = board.get_cell_type(r, c)
                    if ct == CellType.CAMP:
                        score += 15
                    if ct == CellType.HQ:
                        score += 20
        elif style == "defensive":
            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    p = board.get_piece(r, c)
                    if p is None or p.owner != ai_player:
                        continue
                    if p.piece_type in (PieceType.FLAG, PieceType.MINE, PieceType.BOMB):
                        continue
                    if ai_player == Player.RED:
                        score += max(0, 6 - r) * 5
                    else:
                        score += max(0, r - 7) * 5

        if self._opponent_model.get_bomb_likely_used():
            if self._opponent_model._bomb_usage >= 2:
                score += 80

        return score

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
        my_commander_exposed = False
        my_commander_pos = None
        opp_commander_exposed = False
        my_engineer_count = 0
        opp_engineer_count = 0
        opp_mine_count = 0
        my_mine_count = 0
        rail_control = 0

        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is None:
                    continue
                total_pieces += 1
                val = PIECE_VALUES.get(p.piece_type, 0)
                ct = board.get_cell_type(r, c)
                if p.owner == ai_player:
                    my_piece_count += 1
                    my_value += val
                    if p.piece_type == PieceType.FLAG:
                        my_flag = True
                        my_flag_pos = (r, c)
                    elif p.piece_type == PieceType.COMMANDER:
                        my_commander_alive = True
                        my_commander_pos = (r, c)
                        if ct != CellType.HQ:
                            my_commander_exposed = True
                    elif p.piece_type == PieceType.ENGINEER:
                        my_engineer_count += 1
                    elif p.piece_type == PieceType.MINE:
                        my_mine_count += 1
                    else:
                        if enemy_direction == 1:
                            advance_score += (my_back_row - r) * ADVANCE_WEIGHT
                        else:
                            advance_score += (r - my_back_row) * ADVANCE_WEIGHT
                    positional_score += pos_table.get((r, c), 0)
                    if ct == CellType.CAMP:
                        my_value += CAMP_BONUS
                        if p.piece_type in STRONG_PIECE_TYPES:
                            my_value += CAMP_STRONG_BONUS
                    if ct == CellType.RAILWAY:
                        if r in KEY_RAILWAY_ROWS or c in KEY_RAILWAY_COLS:
                            rail_control += RAIL_CONTROL_BONUS
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
                        if ct != CellType.HQ:
                            opp_commander_exposed = True
                    elif p.piece_type == PieceType.ENGINEER:
                        opp_engineer_count += 1
                    elif p.piece_type == PieceType.MINE:
                        opp_mine_count += 1
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
                        val = PIECE_VALUES.get(p.piece_type, 0)
                        protect_score += int(val * 0.15)
                    if p is not None and p.owner == opponent:
                        protect_score -= 60
            my_value += protect_score

        commander_score = 0
        if my_commander_alive and not opp_commander_alive:
            commander_score += COMMANDER_SAFETY_BONUS * 2
        elif not my_commander_alive and opp_commander_alive:
            commander_score -= COMMANDER_SAFETY_BONUS * 2
        if my_commander_exposed:
            if my_commander_pos is not None and my_flag_pos is not None:
                dist_to_flag = abs(my_commander_pos[0] - my_flag_pos[0]) + abs(my_commander_pos[1] - my_flag_pos[1])
                if dist_to_flag <= 2:
                    commander_score -= COMMANDER_EXPOSED_PENALTY // 2
                else:
                    commander_score -= COMMANDER_EXPOSED_PENALTY
            else:
                commander_score -= COMMANDER_EXPOSED_PENALTY
        if opp_commander_exposed:
            commander_score += COMMANDER_EXPOSED_PENALTY

        engineer_score = (my_engineer_count - opp_engineer_count) * 30

        threat_score = self._threat_score(board, ai_player)
        flag_attack_score = self._flag_attack_score(board, ai_player)
        coordination_score = self._coordination_score(board, ai_player)
        trap_score = self._trap_detection_score(board, ai_player)
        adaptation_score = self._opponent_adaptation_score(board, ai_player)

        if opp_flag_pos:
            ofr, ofc = opp_flag_pos
            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    p = board.get_piece(r, c)
                    if p is None or p.owner != ai_player:
                        continue
                    if p.piece_type in (PieceType.FLAG, PieceType.MINE):
                        continue
                    dist = abs(r - ofr) + abs(c - ofc)
                    if dist <= 5:
                        flag_attack_score += FLAG_ATTACK_BONUS * (6 - dist)

        total_score = (my_value - opp_value) + mobility_score + advance_score + positional_score
        total_score += commander_score + engineer_score + threat_score + flag_attack_score + rail_control
        total_score += coordination_score + trap_score + adaptation_score

        phase = self._game_phase(total_pieces)
        if phase == "endgame":
            if my_engineer_count > 0 and opp_mine_count > 0:
                total_score += my_engineer_count * ENGINEER_ENDGAME_VALUE
            if my_mine_count > 0:
                total_score += my_mine_count * 40
            if my_commander_alive and opp_commander_alive:
                total_score += int(my_value * 0.05)
            if my_engineer_count > opp_engineer_count:
                total_score += (my_engineer_count - opp_engineer_count) * 50
            if not my_commander_alive and opp_commander_alive:
                total_score -= 30
        elif phase == "midgame":
            if my_commander_alive and opp_commander_alive:
                total_score += int(my_value * 0.03)
        elif phase == "opening":
            if my_piece_count > opp_piece_count:
                total_score += (my_piece_count - opp_piece_count) * 10

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
                    see_bonus = self._see(board, player, from_r, from_c, to_r, to_c)
                    score += see_bonus
            elif result == "defender":
                my_loss = PIECE_VALUES.get(piece.piece_type, 0)
                score -= my_loss * 4
                if piece.piece_type in (PieceType.COMMANDER, PieceType.ARMY, PieceType.DIVISION):
                    score -= 600
                if piece.piece_type in (PieceType.BRIGADE, PieceType.REGIMENT):
                    score -= 300
            elif result == "both":
                attacker_val = PIECE_VALUES.get(piece.piece_type, 0)
                defender_val = PIECE_VALUES.get(target.piece_type, 0)
                if piece.piece_type == PieceType.BOMB:
                    if target.piece_type in (PieceType.COMMANDER, PieceType.ARMY, PieceType.DIVISION):
                        score += 500
                    elif target.piece_type in (PieceType.BRIGADE, PieceType.REGIMENT):
                        score += defender_val - attacker_val + 100
                    else:
                        score += defender_val - attacker_val
                else:
                    if target.piece_type in (PieceType.COMMANDER, PieceType.ARMY, PieceType.DIVISION):
                        score += defender_val - attacker_val + 200
                    else:
                        score += defender_val - attacker_val
        else:
            to_cell = board.get_cell_type(to_r, to_c)
            if to_cell == CellType.CAMP:
                score += 50
            if piece.piece_type == PieceType.ENGINEER:
                score += 8
            if enemy_direction == 1:
                move_forward = to_r < from_r
                if move_forward:
                    rows_advanced = from_r - to_r
                    score += rows_advanced * 15
                elif to_r > from_r:
                    score -= 5
            else:
                move_forward = to_r > from_r
                if move_forward:
                    rows_advanced = to_r - from_r
                    score += rows_advanced * 15
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

        threat_score = self._is_threatening_flag(board, player, to_r, to_c, piece)
        if threat_score > 0:
            score += threat_score

        near_flag = threat_score > 200

        if self._exposes_valuable_piece(board, player, from_r, from_c, to_r, to_c):
            if near_flag:
                score -= 150
            else:
                score -= 500

        if self._is_piece_in_danger(board, player, to_r, to_c, piece):
            if near_flag:
                score -= 100
            else:
                score -= 400

        if self._will_be_in_danger(board, player, opponent, from_r, from_c, to_r, to_c):
            if near_flag:
                score -= 150
            else:
                score -= 500

        if target is not None and self._is_suicide_attack(board, player, from_r, from_c, to_r, to_c):
            if near_flag:
                score -= 200
            else:
                score -= 800

        if self._detects_trap(board, player, to_r, to_c, piece):
            score -= 300

        return score

    def _detects_trap(self, board, player, to_r, to_c, piece):
        if piece is None or piece.piece_type in (PieceType.FLAG, PieceType.MINE):
            return False
        opponent = Player.RED if player == Player.BLUE else Player.BLUE
        danger_count = 0
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = to_r + dr, to_c + dc
            if not board.is_valid_position(nr, nc):
                continue
            ct = board.get_cell_type(nr, nc)
            if ct == CellType.CAMP:
                continue
            p = board.get_piece(nr, nc)
            if p is not None and p.owner == opponent:
                result = board.resolve_battle(p, piece)
                if result == "attacker":
                    danger_count += 1
                elif result == "both":
                    danger_count += 1
        return danger_count >= 2

    def _is_suicide_attack(self, board, player, from_r, from_c, to_r, to_c):
        piece = board.get_piece(from_r, from_c)
        target = board.get_piece(to_r, to_c)
        if piece is None or target is None:
            return False
        if target.owner == player:
            return False
        atk_rank = PIECE_RANK.get(piece.piece_type, 0)
        def_rank = PIECE_RANK.get(target.piece_type, 0)
        if atk_rank == 0 or def_rank == 0:
            return False
        if atk_rank < def_rank:
            if piece.piece_type != PieceType.BOMB:
                return True
        if piece.piece_type == PieceType.BOMB:
            if target.piece_type not in (PieceType.COMMANDER, PieceType.ARMY, PieceType.DIVISION, PieceType.BRIGADE):
                if def_rank <= atk_rank:
                    return True
        return False

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

    def _is_threatening_flag(self, board, player, to_r, to_c, piece=None):
        opponent = Player.RED if player == Player.BLUE else Player.BLUE
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = board.get_piece(r, c)
                if p is not None and p.owner == opponent and p.piece_type == PieceType.FLAG:
                    distance = abs(to_r - r) + abs(to_c - c)
                    if distance <= 5:
                        if piece is not None:
                            val = PIECE_VALUES.get(piece.piece_type, 0)
                            base = int(val * 0.4)
                        else:
                            base = 300
                        return base * (6 - distance)
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