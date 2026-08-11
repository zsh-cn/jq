import pygame
from config import *
from core.player import Player, PieceType, PIECE_NAMES, TOTAL_PIECES_PER_SIDE
from core.board import CellType
from utils.fonts import get_font
from ui.menu import Button


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.font = get_font(18)
        self.small_font = get_font(14)
        self.tiny_font = get_font(11)
        self.buttons = []
        self.screen_w = WINDOW_WIDTH
        self.screen_h = WINDOW_HEIGHT
        self.cell_w = CELL_WIDTH
        self.cell_h = CELL_HEIGHT
        self.board_offset_x = 0
        self.board_offset_y = 0
        self._hovered_cell = None
        self._selected_cell = None
        self._valid_moves = []

    def set_screen_size(self, w, h):
        self.screen_w = w
        self.screen_h = h
        title_h = TITLE_BAR_HEIGHT
        status_h = STATUS_BAR_HEIGHT

        avail_w = w - 2 * SIDE_PANEL_WIDTH - 2 * MARGIN
        avail_h = h - title_h - status_h - 2 * MARGIN - 10

        cell_w_by_w = avail_w // BOARD_COLS
        cell_h_by_h = avail_h // BOARD_ROWS

        max_cell_w = min(BASE_CELL_WIDTH, cell_w_by_w)
        max_cell_h = min(BASE_CELL_HEIGHT, cell_h_by_h)

        self.cell_w = max(20, max_cell_w)
        self.cell_h = max(14, max_cell_h)

        if self.cell_w > BASE_CELL_WIDTH:
            self.cell_w = BASE_CELL_WIDTH
        if self.cell_h > BASE_CELL_HEIGHT:
            self.cell_h = BASE_CELL_HEIGHT

        self.cell_w = max(20, self.cell_w)
        self.cell_h = max(14, self.cell_h)

        board_width = BOARD_COLS * self.cell_w + 2 * MARGIN
        board_height = BOARD_ROWS * self.cell_h + 2 * MARGIN
        total_width = 2 * SIDE_PANEL_WIDTH + board_width
        left_edge = max(0, (w - total_width) // 2)
        self.board_offset_x = left_edge + SIDE_PANEL_WIDTH
        self.board_offset_y = max(title_h + 5, (h - title_h - status_h - board_height) // 2)
        self._left_panel_x = left_edge + 5
        self._right_panel_x = left_edge + SIDE_PANEL_WIDTH + board_width + 5

    def add_button(self, rect, text, font, callback=None):
        button = Button(rect, text, font, callback)
        self.buttons.append(button)
        return button

    def draw_buttons(self):
        for button in self.buttons:
            button.draw(self.screen)

    def update_hover(self, pos):
        self._hovered_cell = self._screen_to_board(pos)
        for button in self.buttons:
            button.hovered = button.rect.collidepoint(pos)

    def set_selected(self, pos):
        self._selected_cell = pos

    def set_valid_moves(self, moves):
        self._valid_moves = moves

    def draw_board(self, game_state, title="军棋", viewer=None):
        self.screen.fill(BACKGROUND)
        self._draw_title_bar(title)
        self._draw_grid(game_state)
        self._draw_pieces(game_state.board, viewer)
        self._draw_status_bar()

    def _draw_title_bar(self, title="军棋"):
        title_h = TITLE_BAR_HEIGHT
        pygame.draw.rect(self.screen, (60, 60, 60), (0, 0, self.screen_w, title_h))
        pygame.draw.line(self.screen, (40, 40, 40), (0, title_h - 1), (self.screen_w, title_h - 1), 1)
        title_font = get_font(18)
        title_text = title_font.render(title, True, (230, 230, 230))
        self.screen.blit(title_text, (self.screen_w // 2 - title_text.get_width() // 2, title_h // 2 - title_text.get_height() // 2))

    def _draw_grid(self, game_state):
        cw = self.cell_w
        ch = self.cell_h
        board_start_x = self.board_offset_x + MARGIN
        board_start_y = self.board_offset_y + MARGIN + TITLE_BAR_HEIGHT

        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                x = board_start_x + c * cw
                y = board_start_y + r * ch
                ct = game_state.board.get_cell_type(r, c)

                if ct == CellType.CAMP:
                    color = CAMP_COLOR
                elif ct == CellType.HQ:
                    color = HQ_COLOR
                elif ct == CellType.MOUNTAIN:
                    color = MOUNTAIN_COLOR
                else:
                    color = BOARD_BG
                pygame.draw.rect(self.screen, color, (x, y, cw, ch))

                if ct == CellType.RAILWAY:
                    rr = pygame.Rect(x + 2, y + 2, cw - 4, ch - 4)
                    pygame.draw.rect(self.screen, RAILWAY_COLOR, rr, 2)
                    for i in range(1, 4):
                        lx = x + i * cw // 4
                        pygame.draw.line(self.screen, RAILWAY_COLOR,
                                         (lx, y + 4), (lx, y + ch - 4), 1)

                if ct == CellType.HQ:
                    hq_font = self.tiny_font
                    hq_text = hq_font.render("大本营", True, (150, 100, 50))
                    tr = hq_text.get_rect(center=(x + cw // 2, y + ch // 2))
                    self.screen.blit(hq_text, tr)

                if ct == CellType.CAMP:
                    camp_font = self.tiny_font
                    camp_text = camp_font.render("行营", True, (80, 130, 80))
                    tr = camp_text.get_rect(center=(x + cw // 2, y + ch // 2))
                    self.screen.blit(camp_text, tr)

                if ct == CellType.MOUNTAIN:
                    m_font = self.tiny_font
                    m_text = m_font.render("山界", True, (120, 90, 60))
                    tr = m_text.get_rect(center=(x + cw // 2, y + ch // 2))
                    self.screen.blit(m_text, tr)

                pygame.draw.rect(self.screen, LINE_COLOR, (x, y, cw, ch), 1)

        board_bottom = board_start_y + BOARD_ROWS * ch
        pygame.draw.line(self.screen, LINE_COLOR, (board_start_x, board_bottom),
                         (board_start_x + BOARD_COLS * cw, board_bottom), 2)

        self._draw_valid_move_indicators(board_start_x, board_start_y)
        self._draw_selection_indicator(board_start_x, board_start_y)
        self._draw_hover_indicator(board_start_x, board_start_y, game_state)

    def _draw_valid_move_indicators(self, bx, by):
        cw = self.cell_w
        ch = self.cell_h
        for r, c in self._valid_moves:
            s = pygame.Surface((cw - 4, ch - 4), pygame.SRCALPHA)
            s.fill((100, 255, 100, 60))
            self.screen.blit(s, (bx + c * cw + 2, by + r * ch + 2))

    def _draw_selection_indicator(self, bx, by):
        cw = self.cell_w
        ch = self.cell_h
        if self._selected_cell:
            r, c = self._selected_cell
            x = bx + c * cw
            y = by + r * ch
            pygame.draw.rect(self.screen, HIGHLIGHT, (x, y, cw, ch), 3)

    def _draw_hover_indicator(self, bx, by, game_state):
        if game_state.is_game_over:
            return
        cw = self.cell_w
        ch = self.cell_h
        if self._hovered_cell:
            r, c = self._hovered_cell
            if game_state.board.is_valid_position(r, c):
                x = bx + c * cw
                y = by + r * ch
                pygame.draw.rect(self.screen, (255, 255, 200), (x, y, cw, ch), 2)

    def _draw_pieces(self, board, viewer=None):
        cw = self.cell_w
        ch = self.cell_h
        board_start_x = self.board_offset_x + MARGIN
        board_start_y = self.board_offset_y + MARGIN + TITLE_BAR_HEIGHT

        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                piece = board.get_piece(r, c)
                if piece is not None:
                    self._draw_piece(board_start_x, board_start_y, r, c, piece, viewer)

    def _draw_piece(self, bx, by, r, c, piece, viewer=None):
        cw = self.cell_w
        ch = self.cell_h
        x = bx + c * cw + cw // 2
        y = by + r * ch + ch // 2
        radius = min(cw, ch) // 2 - 4

        if piece.owner == Player.RED:
            color = RED_COLOR
            border_color = (180, 30, 30)
        else:
            color = BLUE_COLOR
            border_color = (30, 60, 160)

        hidden = viewer is not None and piece.owner != viewer and not piece.visible

        if radius > 0:
            pygame.draw.circle(self.screen, color, (x, y), radius)
            pygame.draw.circle(self.screen, border_color, (x, y), radius, 2)

        if hidden:
            text = self.small_font.render("?", True, WHITE)
        else:
            name = piece.name
            if len(name) == 2:
                piece_font = self.small_font
            else:
                piece_font = self.tiny_font
            text = piece_font.render(name, True, WHITE)
        text_rect = text.get_rect(center=(x, y))
        self.screen.blit(text, text_rect)

    def _draw_status_bar(self):
        status_y = self.screen_h - STATUS_BAR_HEIGHT + 5
        pygame.draw.line(self.screen, LINE_COLOR, (0, status_y), (self.screen_w, status_y), 1)

    def draw_game_info(self, game_state, network_info=None, my_player=None, opponent_player=None, versus_mode=False):
        y_offset = self.screen_h - STATUS_BAR_HEIGHT + 10
        single_machine = not versus_mode

        if game_state.phase == "setup":
            if versus_mode and my_player is not None:
                if my_player == Player.RED:
                    text = "红方布阵中..."
                else:
                    text = "蓝方布阵中..."
            elif versus_mode:
                text = "等待分配阵营..."
            else:
                text = "双方布阵中..."
        elif game_state.is_game_over:
            if game_state.winner != Player.EMPTY:
                if single_machine:
                    if game_state.winner == Player.RED:
                        text = "红方胜利!"
                    else:
                        text = "蓝方胜利!"
                elif game_state.winner == my_player:
                    text = "你胜利了!"
                else:
                    text = "对手胜利!"
            else:
                text = "平局!"
            text_surface = self.font.render(text, True, HIGHLIGHT)
            self.screen.blit(text_surface, (MARGIN, y_offset))
        else:
            if single_machine:
                if game_state.current_player == Player.RED:
                    text = "当前回合: 红方"
                else:
                    text = "当前回合: 蓝方"
            elif my_player is not None and game_state.current_player == my_player:
                text = "当前回合: 你"
            else:
                text = "当前回合: 对手"
            text_surface = self.font.render(text, True, TEXT_COLOR)
            self.screen.blit(text_surface, (MARGIN, y_offset))

        if network_info:
            net_text = self.small_font.render(network_info, True, TEXT_COLOR)
            self.screen.blit(net_text, (self.screen_w // 2 - net_text.get_width() // 2, y_offset))

    def draw_setup_panel(self, game_state, current_player, selected_piece_type=None, selected_piece_player=None, show_both=True):
        ch = self.cell_h
        panel_y = self.board_offset_y + MARGIN + TITLE_BAR_HEIGHT
        panel_w = SIDE_PANEL_WIDTH - 10
        panel_h = BOARD_ROWS * ch

        if show_both:
            self._draw_one_setup_panel(
                self._left_panel_x, panel_y, panel_w, panel_h,
                game_state, Player.RED, current_player, selected_piece_type, selected_piece_player
            )
            self._draw_one_setup_panel(
                self._right_panel_x, panel_y, panel_w, panel_h,
                game_state, Player.BLUE, current_player, selected_piece_type, selected_piece_player
            )
        else:
            if current_player == Player.RED:
                panel_x = self._left_panel_x
            else:
                panel_x = self._right_panel_x
            self._draw_one_setup_panel(
                panel_x, panel_y, panel_w, panel_h,
                game_state, current_player, current_player, selected_piece_type, selected_piece_player
            )

    def _draw_one_setup_panel(self, px, py, pw, ph, game_state, player, current_player, selected_piece_type, selected_piece_player):
        pygame.draw.rect(self.screen, (240, 235, 220), (px, py, pw, ph))
        pygame.draw.rect(self.screen, LINE_COLOR, (px, py, pw, ph), 2)

        title_font = get_font(16, bold=True)
        if player == Player.RED:
            title_text = title_font.render("红方棋子", True, RED_COLOR)
        else:
            title_text = title_font.render("蓝方棋子", True, BLUE_COLOR)
        tr = title_text.get_rect(center=(px + pw // 2, py + 15))
        self.screen.blit(title_text, tr)

        placed, remaining = game_state.get_setup_piece_counts(player)

        y = py + 35
        font = self.tiny_font

        piece_order = [
            PieceType.COMMANDER, PieceType.ARMY, PieceType.DIVISION, PieceType.BRIGADE,
            PieceType.REGIMENT, PieceType.BATTALION, PieceType.COMPANY, PieceType.PLATOON,
            PieceType.ENGINEER, PieceType.BOMB, PieceType.MINE, PieceType.FLAG
        ]

        is_current = (player == current_player)
        is_selected = (selected_piece_type is not None and selected_piece_player == player)

        for pt in piece_order:
            total = remaining.get(pt, 0)
            name = PIECE_NAMES[pt]
            if total == 0:
                color = (180, 180, 180)
            else:
                color = TEXT_COLOR

            if selected_piece_type == pt and total > 0 and is_selected:
                bg_rect = pygame.Rect(px + 5, y - 1, pw - 10, 18)
                pygame.draw.rect(self.screen, SELECTED_COLOR, bg_rect, border_radius=3)

            text = font.render(f"{name} x{total}", True, color)
            self.screen.blit(text, (px + 10, y))
            y += 20

        y += 10
        total_placed = sum(placed.values())
        info_text = font.render(f"已放置: {total_placed}/25", True, TEXT_COLOR)
        self.screen.blit(info_text, (px + 10, y))

        if total_placed == TOTAL_PIECES_PER_SIDE:
            y += 25
            done_text = get_font(14).render("布阵完成!", True, (0, 150, 0))
            self.screen.blit(done_text, (px + 10, y))

    def draw_battle_results(self, battle_results, board):
        if not battle_results:
            return

        msg_font = get_font(14)
        line_h = 18
        fade_frames = 60

        start_y = TITLE_BAR_HEIGHT + 5

        for i, item in enumerate(battle_results):
            result = item["result"]
            timer = item["timer"]
            from_r, from_c, to_r, to_c, atk_type, def_type, atk_owner, def_owner, outcome = result

            atk_name = PIECE_NAMES[atk_type]
            def_name = PIECE_NAMES[def_type]

            if outcome == "attacker":
                atk_text = f"[{self._owner_label(atk_owner)}]{atk_name}"
                mid_text = " 击败 "
                def_text = f"[{self._owner_label(def_owner)}]{def_name}"
                segments = [
                    (atk_text, self._owner_color(atk_owner)),
                    (mid_text, (0, 0, 0)),
                    (def_text, self._owner_color(def_owner)),
                ]
            elif outcome == "defender":
                atk_text = f"[{self._owner_label(atk_owner)}]{atk_name}"
                mid1 = " 被 "
                def_text = f"[{self._owner_label(def_owner)}]{def_name}"
                mid2 = " 击败"
                segments = [
                    (atk_text, self._owner_color(atk_owner)),
                    (mid1, (0, 0, 0)),
                    (def_text, self._owner_color(def_owner)),
                    (mid2, (0, 0, 0)),
                ]
            else:
                atk_text = f"[{self._owner_label(atk_owner)}]{atk_name}"
                mid1 = " 与 "
                def_text = f"[{self._owner_label(def_owner)}]{def_name}"
                mid2 = " 同归于尽"
                segments = [
                    (atk_text, self._owner_color(atk_owner)),
                    (mid1, (0, 0, 0)),
                    (def_text, self._owner_color(def_owner)),
                    (mid2, (0, 0, 0)),
                ]

            if timer > fade_frames:
                alpha = 255
            else:
                alpha = max(0, int(timer * 255 / fade_frames))

            surfaces = []
            total_w = 0
            for text, color in segments:
                s = msg_font.render(text, True, color)
                surfaces.append(s)
                total_w += s.get_width()

            combined = pygame.Surface((total_w, line_h), pygame.SRCALPHA)
            cx = 0
            for s in surfaces:
                combined.blit(s, (cx, 0))
                cx += s.get_width()
            combined.set_alpha(alpha)

            x = self.screen_w - total_w - 10
            y = start_y + i * line_h
            self.screen.blit(combined, (x, y))

    def _owner_label(self, owner):
        return "红方" if owner == Player.RED else "蓝方"

    def _owner_color(self, owner):
        return RED_COLOR if owner == Player.RED else BLUE_COLOR

    def _wrap_text(self, text, font, max_width):
        words = list(text)
        lines = []
        current = ""
        for ch in words:
            test = current + ch
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
        return lines

    def draw_hover_preview(self, board, mouse_pos, current_player):
        pass

    def _screen_to_board(self, pos):
        cw = self.cell_w
        ch = self.cell_h
        board_start_x = self.board_offset_x + MARGIN
        board_start_y = self.board_offset_y + MARGIN + TITLE_BAR_HEIGHT
        x, y = pos
        col = (x - board_start_x) // cw
        row = (y - board_start_y) // ch
        if 0 <= row < BOARD_ROWS and 0 <= col < BOARD_COLS:
            return row, col
        return None

    def get_board_pos(self, pos):
        return self._screen_to_board(pos)

    def get_setup_panel_piece_type(self, pos):
        panel_y = self.board_offset_y + MARGIN + TITLE_BAR_HEIGHT
        panel_w = SIDE_PANEL_WIDTH - 10
        x, y = pos

        piece_order = [
            PieceType.COMMANDER, PieceType.ARMY, PieceType.DIVISION, PieceType.BRIGADE,
            PieceType.REGIMENT, PieceType.BATTALION, PieceType.COMPANY, PieceType.PLATOON,
            PieceType.ENGINEER, PieceType.BOMB, PieceType.MINE, PieceType.FLAG
        ]

        panels_to_check = [(self._left_panel_x, Player.RED), (self._right_panel_x, Player.BLUE)]
        for panel_x, player in panels_to_check:
            if panel_x <= x <= panel_x + panel_w:
                item_y = panel_y + 35
                for pt in piece_order:
                    if item_y - 1 <= y <= item_y + 18:
                        return pt, player
                    item_y += 20
        return None, None
