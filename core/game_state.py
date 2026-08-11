from config import BOARD_ROWS, BOARD_COLS
from core.board import Board, Piece, CellType
from core.player import Player, PieceType, PIECE_COUNT, TOTAL_PIECES_PER_SIDE


class GameState:
    def __init__(self):
        self.board = Board()
        self.current_player = Player.RED
        self.winner = Player.EMPTY
        self.is_game_over = False
        self.phase = "setup"
        self.red_setup_done = False
        self.blue_setup_done = False
        self.selected_piece_pos = None
        self.battle_result = None

    def reset(self):
        self.board.reset()
        self.current_player = Player.RED
        self.winner = Player.EMPTY
        self.is_game_over = False
        self.phase = "setup"
        self.red_setup_done = False
        self.blue_setup_done = False
        self.selected_piece_pos = None
        self.battle_result = None

    def start_game(self):
        if self.red_setup_done and self.blue_setup_done:
            self.phase = "playing"
            self.current_player = Player.RED
            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    p = self.board.grid[r][c]
                    if p is not None:
                        p.visible = True
                        if self.board.cell_types[r][c] == CellType.HQ:
                            p.locked = True
            return True
        return False

    def setup_place_piece(self, row, col, piece_type, player):
        if self.phase != "setup":
            return False
        if player == Player.RED and self.red_setup_done:
            return False
        if player == Player.BLUE and self.blue_setup_done:
            return False
        area_rows = self.board.get_player_area_rows(player)
        if row not in area_rows:
            return False
        if self.board.get_piece(row, col) is not None:
            return False
        cell_type = self.board.get_cell_type(row, col)
        if cell_type == CellType.CAMP:
            return False

        area_rows_list = list(area_rows)
        if player == Player.RED:
            front_row = area_rows_list[0]
            back_rows = (area_rows_list[-2], area_rows_list[-1])
        else:
            front_row = area_rows_list[-1]
            back_rows = (area_rows_list[0], area_rows_list[1])

        if piece_type == PieceType.BOMB and row == front_row:
            return False

        if piece_type == PieceType.MINE and row not in back_rows:
            return False

        if piece_type == PieceType.MINE and cell_type == CellType.HQ:
            return False

        if piece_type == PieceType.FLAG:
            if cell_type != CellType.HQ:
                return False
        piece = Piece(piece_type, player)
        return self.board.place_piece(row, col, piece)

    def setup_remove_piece(self, row, col, player):
        if self.phase != "setup":
            return False
        if player == Player.RED and self.red_setup_done:
            return False
        if player == Player.BLUE and self.blue_setup_done:
            return False
        piece = self.board.get_piece(row, col)
        if piece is None or piece.owner != player:
            return False
        self.board.remove_piece(row, col)
        return True

    def get_setup_piece_counts(self, player):
        placed = {}
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = self.board.grid[r][c]
                if p is not None and p.owner == player:
                    pt = p.piece_type
                    placed[pt] = placed.get(pt, 0) + 1
        remaining = {}
        for pt, count in PIECE_COUNT.items():
            remaining[pt] = count - placed.get(pt, 0)
        return placed, remaining

    def is_setup_complete(self, player):
        placed, remaining = self.get_setup_piece_counts(player)
        total_placed = sum(placed.values())
        flag_placed = placed.get(PieceType.FLAG, 0) >= 1
        return total_placed == TOTAL_PIECES_PER_SIDE and flag_placed

    def make_move(self, from_row, from_col, to_row, to_col):
        if self.phase != "playing":
            return False
        if self.is_game_over:
            return False

        piece = self.board.get_piece(from_row, from_col)
        if piece is None or piece.owner != self.current_player:
            return False

        valid_moves = self.board.get_valid_moves(from_row, from_col)
        if (to_row, to_col) not in valid_moves:
            return False

        target = self.board.get_piece(to_row, to_col)
        self.battle_result = None

        if target is not None:
            result = self.board.resolve_battle(piece, target)
            piece.visible = True
            target.visible = True
            self.battle_result = (from_row, from_col, to_row, to_col, piece.piece_type, target.piece_type, piece.owner, target.owner, result)
            if result == "attacker":
                self.board.remove_piece(to_row, to_col)
                self.board.move_piece(from_row, from_col, to_row, to_col)
            elif result == "defender":
                self.board.remove_piece(from_row, from_col)
            elif result == "both":
                self.board.remove_piece(from_row, from_col)
                self.board.remove_piece(to_row, to_col)
        else:
            self.board.move_piece(from_row, from_col, to_row, to_col)

        opponent = Player.RED if self.current_player == Player.BLUE else Player.BLUE

        if self.board.check_flag_captured(opponent):
            self.is_game_over = True
            self.winner = self.current_player
            return True

        if not self.board.has_valid_moves(opponent):
            self.is_game_over = True
            self.winner = self.current_player
            return True

        self.current_player = opponent
        return True

    def get_state_dict(self):
        grid_data = []
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = self.board.grid[r][c]
                if p is not None:
                    grid_data.append((r, c, int(p.piece_type), int(p.owner), 1 if p.locked else 0))
        return {
            "grid": grid_data,
            "current_player": int(self.current_player),
            "is_game_over": self.is_game_over,
            "winner": int(self.winner),
            "phase": self.phase,
            "red_setup_done": self.red_setup_done,
            "blue_setup_done": self.blue_setup_done,
        }

    def load_state_dict(self, state):
        self.board.reset()
        for entry in state["grid"]:
            r, c, pt, owner = entry[0], entry[1], entry[2], entry[3]
            piece = Piece(PieceType(pt), Player(owner))
            if len(entry) > 4 and entry[4]:
                piece.locked = True
            self.board.place_piece(r, c, piece)
        self.current_player = Player(state["current_player"])
        self.is_game_over = state["is_game_over"]
        self.winner = Player(state["winner"])
        self.phase = state.get("phase", "playing")
        self.red_setup_done = state.get("red_setup_done", True)
        self.blue_setup_done = state.get("blue_setup_done", True)