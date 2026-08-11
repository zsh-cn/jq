import random
import time

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


class MilitaryChessAI:
    def __init__(self):
        self._max_depth = 8
        self._time_limit = 8.0
        self._start_time = 0
        self._timeout = False
        self._tt = TranspositionTable()
        self._killer = KillerMoves()
        self._history = {}
        self._known_enemy_pieces = {}
        self._nodes_searched = 0
        self._cutoffs = 0

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

        if player == Player.RED:
            row_map = lambda r: r
        else:
            row_map = lambda r: 12 - r

        flag_col = random.choice([1, 3])
        if flag_col == 1:
            col_map = lambda c: c
        else:
            col_map = lambda c: 4 - c

        base_layout = {
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

        for pt, positions in base_layout.items():
            mapped = [(row_map(r), col_map(c)) for (r, c) in positions]
            random.shuffle(mapped)
            for (r, c) in mapped:
                if board.get_piece(r, c) is None:
                    board.place_piece(r, c, Piece(pt, player))

    def get_best_move(self, board, player):
        self._timeout = False
        self._start_time = time.time()
        self._tt.clear()
        self._killer = KillerMoves()
        self._history = {}
        self._nodes_searched = 0
        self._cutoffs = 0
        self._known_enemy_pieces = {}
        self._track_enemy_pieces(board, player)

        movable = board.get_movable_pieces(player)
        if not movable:
            return None

        opponent = Player.RED if player == Player.BLUE else Player.BLUE

        root_moves = []
        for r, c, moves in movable:
            for to_r, to_c in moves:
                score = self._evaluate_move_quick(board, player, opponent, r, c, to_r, to_c)
                root_moves.append((score, r, c, to_r, to_c))

        best_move = None
        best_score = -float("inf")
        pv_move = None

        for depth in range(1, self._max_depth + 1):
            if self._timeout:
                break

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
            alpha = -float("inf")
            beta = float("inf")

            limit = min(len(ordered), 30)
            for i in range(limit):
                if self._timeout:
                    break
                _, r, c, to_r, to_c = ordered[i]
                move = (r, c, to_r, to_c)
                board_copy = board.copy()
                self._simulate_move(board_copy, r, c, to_r, to_c)

                if i == 0:
                    score = self._minimax(board_copy, opponent, depth - 1, alpha, beta, False, player)
                else:
                    score = self._minimax(board_copy, opponent, depth - 1, alpha, alpha + 1, False, player)
                    if alpha < score < beta:
                        score = self._minimax(board_copy, opponent, depth - 1, alpha, beta, False, player)

                if self._timeout:
                    break

                if score > current_best_score:
                    current_best_score = score
                    current_best = move
                if score > alpha:
                    alpha = score

            if not self._timeout and current_best is not None:
                best_move = current_best
                best_score = current_best_score
                pv_move = current_best

        if best_move is None:
            for s, r, c, to_r, to_c in root_moves:
                best_move = (r, c, to_r, to_c)
                break

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

        if depth >= 3 and maximizing:
            if self._try_null_move(board, current_player, depth, alpha, beta, maximizing, ai_player):
                return beta

        all_moves = []
        for r, c, moves in movable:
            for to_r, to_c in moves:
                move_score = self._order_move_score(board, current_player, opponent, r, c, to_r, to_c, depth, tt_move)
                all_moves.append((move_score, r, c, to_r, to_c))

        all_moves.sort(key=lambda x: x[0], reverse=True)

        limit = min(len(all_moves), 24)
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
                new_depth = depth - 2
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
                return 40000 + mvv * 10 - lva
            elif result == "both":
                return 20000 + mvv - lva
            else:
                return -mvv * 5

        hist = self._history.get(move, 0)
        if hist > 0:
            return 30000 + min(hist, 20000)

        return self._evaluate_move_quick(board, player, opponent, from_r, from_c, to_r, to_c)

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
                if p.piece_type not in (PieceType.COMMANDER, PieceType.ARMY, PieceType.DIVISION, PieceType.BRIGADE):
                    continue
                dist = abs(r - fr) + abs(c - fc)
                if dist <= 4:
                    val = PIECE_VALUES.get(p.piece_type, 0)
                    score += int(val * 0.08) * (5 - dist)
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

        total_score = (my_value - opp_value) + mobility_score + advance_score + positional_score
        total_score += commander_score + engineer_score + threat_score + flag_attack_score + rail_control

        phase = self._game_phase(total_pieces)
        if phase == "endgame":
            if my_engineer_count > 0 and opp_mine_count > 0:
                total_score += my_engineer_count * ENGINEER_ENDGAME_VALUE
            if my_mine_count > 0:
                total_score += my_mine_count * 40
            if my_commander_alive and opp_commander_alive:
                total_score += my_value * 0.05
            if my_engineer_count > opp_engineer_count:
                total_score += (my_engineer_count - opp_engineer_count) * 50
        elif phase == "midgame":
            if my_commander_alive and opp_commander_alive:
                total_score += my_value * 0.03

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

        threat_score = self._is_threatening_flag(board, player, to_r, to_c, piece)
        if threat_score > 0:
            score += threat_score

        if self._exposes_valuable_piece(board, player, from_r, from_c, to_r, to_c):
            score -= 500

        if self._is_piece_in_danger(board, player, to_r, to_c, piece):
            score -= 400

        if self._will_be_in_danger(board, player, opponent, from_r, from_c, to_r, to_c):
            score -= 500

        if target is not None and self._is_suicide_attack(board, player, from_r, from_c, to_r, to_c):
            score -= 800

        return score

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
                    if distance <= 3:
                        if piece is not None:
                            val = PIECE_VALUES.get(piece.piece_type, 0)
                            base = int(val * 0.15)
                        else:
                            base = 120
                        return base * (4 - distance)
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