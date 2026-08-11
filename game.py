import pygame
import time
import socket
import random
import threading
import sys
from config import *
from core.game_state import GameState
from core.board import Piece
from core.player import Player, PieceType, PIECE_NAMES
from core.ai import MilitaryChessAI
from ui.renderer import Renderer
from ui.menu import Menu, Button
from ui.dialog import Dialog
from network.client import GomokuClient
from network.server import GomokuServer
from utils.fonts import get_font
from utils.firewall import add_firewall_rule


class MilitaryChessGame:
    def __init__(self, is_server=False, player=0, host="127.0.0.1", port=9000, window_size=None):
        pygame.init()
        if window_size:
            self.screen = pygame.display.set_mode(window_size, pygame.RESIZABLE)
        else:
            self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("军棋 - 联机对战")
        self.clock = pygame.time.Clock()
        self.game_state = GameState()
        self.renderer = Renderer(self.screen)
        self.renderer.set_screen_size(*self.screen.get_size())
        self.is_server = is_server
        self.player_type = player
        self.host = host
        self.port = port
        self.client = None
        self.server = None
        self.game_started = False
        self.server_client_id = 0
        self.player_id = 0
        self.my_player = None
        self.opponent_player = None
        self._pending_game_start = None
        self._network_ok = None
        self._connect_done = False
        self._connect_lock = threading.Lock()
        self._disconnected = False
        self._pending_return = None
        self._ai = None
        self._ai_pending = False
        self._ai_setup_done = False
        self._ai_delay = 0
        self._ai_thread = None
        self._ai_result = None
        self._ai_computing = False
        self._ai_anim_phase = 0
        self._ai_generation = 0
        self._local_ip = None
        self._selected_piece_type = None
        self._selected_piece_player = None
        self._selected_cell = None
        self._battle_results = []
        self._opponent_setup_received = False
        self._my_setup_sent = False
        self._reset_pending = False
        self._waiting_for_rematch = False

    def _full_reset(self):
        self.game_state.reset()
        self._selected_piece_type = None
        self._selected_piece_player = None
        self._selected_cell = None
        self._battle_results = []
        self._opponent_setup_received = False
        self._my_setup_sent = False
        self._disconnected = False
        self._waiting_for_rematch = False
        self._ai_pending = False
        self._ai_computing = False
        self._ai_result = None
        self._ai_thread = None
        self._ai_setup_done = False
        self._ai_delay = 0
        self._ai_anim_phase = 0
        self.renderer.set_selected(None)
        self.renderer.set_valid_moves([])

    def _init_network(self):
        if self.player_type == 0:
            self.game_started = True
            self.my_player = Player.RED
            self.opponent_player = Player.BLUE
            return True
        if self.is_server:
            self.server = GomokuServer(self.host, self.port)
            if not self.server.start():
                return False
            add_firewall_rule("军棋联机服务")
            time.sleep(0.1)
            self.client = GomokuClient("127.0.0.1", self.port)
            if self.client.connect():
                return True
            self.server.stop()
            self.server = None
            return False
        else:
            self.client = GomokuClient(self.host, self.port)
            if self.client.connect():
                return True
            return False

    def _init_ai_game(self):
        self._full_reset()
        self._ai = MilitaryChessAI()
        self.game_started = True
        self._init_buttons()

        if random.random() < 0.5:
            self.my_player = Player.RED
            self.opponent_player = Player.BLUE
        else:
            self.my_player = Player.BLUE
            self.opponent_player = Player.RED

        self._ai.auto_setup(self.game_state.board, self.opponent_player)
        for r, c in self.game_state.board.get_piece_positions(self.opponent_player):
            p = self.game_state.board.get_piece(r, c)
            if p is not None:
                p.visible = False
        if self.opponent_player == Player.RED:
            self.game_state.red_setup_done = True
        else:
            self.game_state.blue_setup_done = True
        self._ai_setup_done = True

    def _init_buttons(self):
        self.renderer.buttons = []
        font = get_font(18)
        btn_w, btn_h = 70, 28
        margin_left = 15
        y_top = 6
        screen_w = self.screen.get_width()

        self.exit_button = self.renderer.add_button(
            pygame.Rect(margin_left, y_top, btn_w, btn_h),
            "退出",
            font,
            self._quit_to_menu
        )

        self.reset_button = self.renderer.add_button(
            pygame.Rect(margin_left + btn_w + 8, y_top, btn_w, btn_h),
            "重置",
            font,
            self._restart_game
        )
        self.reset_button.visible = True

        btn_w2, btn_h2 = 120, 40
        y_pos2 = self.screen.get_height() // 2 + 80

        self.restart_button = self.renderer.add_button(
            pygame.Rect(screen_w // 2 - btn_w2 - 15, y_pos2, btn_w2, btn_h2),
            "再来一局",
            font,
            self._restart_game
        )
        self.restart_button.visible = False

        self.menu_button = self.renderer.add_button(
            pygame.Rect(screen_w // 2 + 15, y_pos2, btn_w2, btn_h2),
            "返回菜单",
            font,
            self._quit_to_menu
        )
        self.menu_button.visible = False

        self.confirm_button = self.renderer.add_button(
            pygame.Rect(margin_left + btn_w * 2 + 16, y_top, btn_w, btn_h),
            "确认布阵",
            font,
            self._confirm_setup
        )
        self.confirm_button.visible = True

        self.auto_setup_button = self.renderer.add_button(
            pygame.Rect(margin_left + btn_w * 3 + 24, y_top, btn_w, btn_h),
            "自动布阵",
            font,
            self._auto_setup_self
        )
        self.auto_setup_button.visible = True

    def _restart_game(self):
        if self.client:
            if self.game_state.is_game_over:
                self._full_reset()
                self._waiting_for_rematch = True
                self.client.send_reset()
            else:
                dialog = Dialog(self.screen, "游戏还未结束，确定要重新开始吗？", "提示", [("确定", True), ("取消", False)])
                result = dialog.show()
                if result:
                    self._full_reset()
                    self.client.send_reset()
        elif self.player_type == 3:
            self._init_ai_game()
        else:
            self._full_reset()
            self.my_player = Player.RED
            self.opponent_player = Player.BLUE

    def _randomize_sides_and_start(self):
        self._full_reset()
        cids = sorted(self.server.clients.keys()) if self.server else []
        if len(cids) >= 2:
            if random.random() < 0.5:
                pid_map = {str(cids[0]): 1, str(cids[1]): 2}
            else:
                pid_map = {str(cids[0]): 2, str(cids[1]): 1}
            self.server._broadcast("game_start", {"player_id_map": pid_map})

    def _quit_to_menu(self):
        self._pending_return = "menu"

    def _quit_game(self):
        self._pending_return = "quit"

    def _confirm_setup(self):
        if self.game_state.phase != "setup":
            return
        if self.player_type != 0 and self.my_player is None:
            return

        if self.player_type == 0:
            red_ready = self.game_state.is_setup_complete(Player.RED)
            blue_ready = self.game_state.is_setup_complete(Player.BLUE)
            if red_ready and blue_ready:
                self.game_state.red_setup_done = True
                self.game_state.blue_setup_done = True
                self.game_state.start_game()
            return

        if self.game_state.is_setup_complete(self.my_player):
            if self.my_player == Player.RED:
                self.game_state.red_setup_done = True
            else:
                self.game_state.blue_setup_done = True

            if self.player_type == 3 and self._ai_setup_done:
                self.game_state.start_game()
                if self._is_ai_turn():
                    self._ai_pending = True
                    self._ai_delay = 30
            elif self.client and not self._my_setup_sent:
                self._send_setup_sync()
                self._my_setup_sent = True
                if self._opponent_setup_received:
                    self.game_state.start_game()
                    if self._is_ai_turn():
                        self._ai_pending = True
                        self._ai_delay = 20

    def _send_setup_sync(self):
        if not self.client:
            return
        pieces_data = []
        area_rows = list(self.game_state.board.get_player_area_rows(self.my_player))
        for r in area_rows:
            for c in range(5):
                p = self.game_state.board.get_piece(r, c)
                if p is not None and p.owner == self.my_player:
                    pieces_data.append((r, c, int(p.piece_type), int(p.owner)))
        self.client.send_setup_sync(pieces_data)

    def _auto_setup_self(self):
        if self.game_state.phase != "setup":
            return
        if self._ai is None:
            self._ai = MilitaryChessAI()
        if self.player_type == 0:
            self._clear_player_pieces(Player.RED)
            self._clear_player_pieces(Player.BLUE)
            self._ai.auto_setup(self.game_state.board, Player.RED)
            self._ai.auto_setup(self.game_state.board, Player.BLUE)
        else:
            if self.my_player is None:
                return
            self._clear_player_pieces(self.my_player)
            self._ai.auto_setup(self.game_state.board, self.my_player)
        self._selected_piece_type = None
        self._selected_piece_player = None
        self._selected_cell = None
        self.renderer.set_selected(None)
        self.renderer.set_valid_moves([])

    def _clear_player_pieces(self, player):
        area_rows = list(self.game_state.board.get_player_area_rows(player))
        for r in area_rows:
            for c in range(5):
                p = self.game_state.board.get_piece(r, c)
                if p is not None and p.owner == player:
                    self.game_state.board.remove_piece(r, c)

    def _is_ai_turn(self):
        if self.game_state.phase != "playing":
            return False
        if self.game_state.is_game_over:
            return False
        return self.game_state.current_player == self.opponent_player

    def _is_my_turn(self):
        if self.game_state.phase == "setup":
            return True
        if self.game_state.is_game_over:
            return False
        if self.player_type == 3:
            return self.game_state.current_player == self.my_player
        if not self.client:
            return True
        if self.player_type == 0:
            return True
        return self.game_state.current_player == self.my_player

    def _get_selectable_player(self):
        if self.player_type == 0:
            return self.game_state.current_player
        return self.my_player

    def _ai_make_move(self):
        if self.game_state.phase != "playing":
            return
        if self.game_state.is_game_over:
            return
        if self._ai_computing:
            return
        self._ai_computing = True
        self._ai_result = None
        self._ai_generation += 1
        gen = self._ai_generation
        board_copy = self.game_state.board.copy()
        ai_player = self.opponent_player

        def _worker():
            try:
                move = self._ai.get_best_move(board_copy, ai_player)
                if gen == self._ai_generation:
                    self._ai_result = move
            except Exception:
                if gen == self._ai_generation:
                    self._ai_result = None

        self._ai_thread = threading.Thread(target=_worker, daemon=True)
        self._ai_thread.start()

    def _add_battle_result(self, battle_result):
        self._battle_results.append({"result": battle_result, "timer": 360})

    def _update_battle_results(self):
        self._battle_results = [r for r in self._battle_results if r["timer"] > 0]
        for r in self._battle_results:
            r["timer"] -= 1

    def _finish_ai_move(self):
        if self._ai_result is not None:
            from_r, from_c, to_r, to_c = self._ai_result
            if not self.game_state.is_game_over and self.game_state.phase == "playing":
                self.game_state.make_move(from_r, from_c, to_r, to_c)
                if self.game_state.battle_result:
                    self._add_battle_result(self.game_state.battle_result)
        self._ai_computing = False
        self._ai_result = None
        self._ai_thread = None

    def _do_connect(self):
        try:
            result = self._init_network()
        except Exception:
            result = False
        with self._connect_lock:
            self._network_ok = result
            self._connect_done = True

    def _show_connecting_screen(self):
        display_host = "127.0.0.1" if self.is_server else self.host
        dots = 0
        frame_count = 0
        font = get_font(24)
        screen_w, screen_h = self.screen.get_size()
        cancel_btn = Button(
            pygame.Rect(screen_w // 2 - 60, screen_h // 2 + 60, 120, 40),
            "取消",
            font,
            lambda: None
        )
        cancel_clicked = False
        while True:
            with self._connect_lock:
                done = self._connect_done
            if done:
                return True
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._cleanup()
                    pygame.quit()
                    sys.exit(0)
                if event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.renderer.set_screen_size(event.w, event.h)
                    screen_w, screen_h = self.screen.get_size()
                    cancel_btn.rect = pygame.Rect(screen_w // 2 - 60, screen_h // 2 + 60, 120, 40)
                elif event.type == pygame.MOUSEMOTION:
                    cancel_btn.hovered = cancel_btn.rect.collidepoint(event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if cancel_btn.rect.collidepoint(event.pos):
                        cancel_clicked = True
            if cancel_clicked:
                return False
            self.screen.fill(BACKGROUND)
            font_big = get_font(36)
            text = font_big.render(f"正在连接...{'.' * dots}", True, TEXT_COLOR)
            text_rect = text.get_rect(center=(screen_w // 2, screen_h // 2 - 20))
            self.screen.blit(text, text_rect)
            hint_font = get_font(20)
            hint = hint_font.render(f"{display_host}:{self.port}", True, (100, 100, 100))
            hint_rect = hint.get_rect(center=(screen_w // 2, screen_h // 2 + 20))
            self.screen.blit(hint, hint_rect)
            cancel_btn.draw(self.screen)
            pygame.display.flip()
            self.clock.tick(10)
            frame_count += 1
            if frame_count >= 3:
                dots = (dots + 1) % 4
                frame_count = 0

    def run(self):
        if self.player_type == 3:
            self._init_ai_game()
        elif self.player_type != 0:
            connect_thread = threading.Thread(target=self._do_connect, daemon=True)
            connect_thread.start()
            if not self._show_connecting_screen():
                self._cleanup()
                return "menu"
            if not self._network_ok:
                dialog = Dialog(self.screen, f"无法连接到服务器\n{self.host}:{self.port}",
                                "连接失败", [("返回菜单", True)])
                result = dialog.show()
                self._cleanup()
                if result is None:
                    return "quit"
                return "menu"
            self._init_buttons()
        else:
            self.game_started = True
            self.my_player = Player.RED
            self.opponent_player = Player.BLUE
            self._init_buttons()

        running = True
        while running:
            if self._pending_return == "menu":
                self._cleanup()
                return "menu"
            elif self._pending_return == "quit":
                self._cleanup()
                pygame.quit()
                sys.exit(0)
            if not self._process_events():
                running = False
                break
            self._update()
            self._draw()
            self.clock.tick(FPS)
        self._cleanup()
        return "menu"

    def _process_button_event(self, event, game_pos):
        consumed = False
        for button in self.renderer.buttons:
            if not button.visible:
                continue
            if event.type == pygame.MOUSEMOTION:
                button.hovered = button.rect.collidepoint(game_pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if button.rect.collidepoint(game_pos):
                    if button.callback:
                        button.callback()
                    consumed = True
                    break
        return consumed

    def _process_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._cleanup()
                pygame.quit()
                sys.exit(0)
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self._process_button_event(event, event.pos):
                    self._handle_click(event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                self._handle_right_click(event.pos)
            elif event.type == pygame.MOUSEMOTION:
                self._process_button_event(event, event.pos)
                self.renderer.update_hover(event.pos)
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                self.renderer.set_screen_size(event.w, event.h)
                self._init_buttons()
        return True

    def _handle_click(self, pos):
        if self.game_state.phase == "setup":
            self._handle_setup_click(pos)
        elif self.game_state.phase == "playing":
            self._handle_play_click(pos)

    def _handle_right_click(self, pos):
        if self.game_state.phase == "setup":
            cell = self.renderer.get_board_pos(pos)
            if cell is not None:
                existing = self.game_state.board.get_piece(cell[0], cell[1])
                if existing is not None:
                    if self.player_type != 0 and existing.owner != self.my_player:
                        return
                    self.game_state.setup_remove_piece(cell[0], cell[1], existing.owner)
                    self._selected_cell = None
                    self._selected_piece_type = None
                    self._selected_piece_player = None
        elif self.game_state.phase == "playing":
            self._selected_cell = None
            self.renderer.set_selected(None)
            self.renderer.set_valid_moves([])

    def _handle_setup_click(self, pos):
        if self._ai_pending or self._ai_computing:
            return
        if self.player_type != 0 and self.my_player is None:
            return

        panel_pt, panel_player = self.renderer.get_setup_panel_piece_type(pos)
        if panel_pt is not None:
            if self.player_type != 0 and panel_player != self.my_player:
                return
            placed, remaining = self.game_state.get_setup_piece_counts(panel_player)
            if remaining.get(panel_pt, 0) > 0:
                self._selected_piece_type = panel_pt
                self._selected_piece_player = panel_player
            return

        cell = self.renderer.get_board_pos(pos)
        if cell is not None:
            r, c = cell
            if self._selected_piece_type is not None and self._selected_piece_player is not None:
                if self.player_type != 0 and self._selected_piece_player != self.my_player:
                    return
                existing = self.game_state.board.get_piece(r, c)
                if existing is not None and existing.owner == self._selected_piece_player:
                    self.game_state.setup_remove_piece(r, c, self._selected_piece_player)
                    self._selected_cell = None
                else:
                    if self.game_state.setup_place_piece(r, c, self._selected_piece_type, self._selected_piece_player):
                        placed, remaining = self.game_state.get_setup_piece_counts(self._selected_piece_player)
                        if remaining.get(self._selected_piece_type, 0) <= 0:
                            self._selected_piece_type = None
                            self._selected_piece_player = None
            else:
                existing = self.game_state.board.get_piece(r, c)
                if existing is not None:
                    if self.player_type != 0 and existing.owner != self.my_player:
                        return
                    self.game_state.setup_remove_piece(r, c, existing.owner)
                    self._selected_cell = None

    def _handle_play_click(self, pos):
        if self._ai_pending or self._ai_computing:
            return
        if not self._is_my_turn():
            return

        cell = self.renderer.get_board_pos(pos)
        if cell is None:
            return

        r, c = cell

        if self._selected_cell is None:
            piece = self.game_state.board.get_piece(r, c)
            selectable = self._get_selectable_player()
            if piece is not None and piece.owner == selectable:
                moves = self.game_state.board.get_valid_moves(r, c)
                if moves:
                    self._selected_cell = (r, c)
                    self.renderer.set_selected((r, c))
                    self.renderer.set_valid_moves(moves)
        else:
            sr, sc = self._selected_cell
            if (r, c) == (sr, sc):
                self._selected_cell = None
                self.renderer.set_selected(None)
                self.renderer.set_valid_moves([])
            else:
                if self.game_state.make_move(sr, sc, r, c):
                    self._selected_cell = None
                    self.renderer.set_selected(None)
                    self.renderer.set_valid_moves([])
                    if self.game_state.battle_result:
                        self._add_battle_result(self.game_state.battle_result)
                    if self.client:
                        self.client.send_move(sr, sc, r, c)
                    elif self.player_type == 3 and not self.game_state.is_game_over:
                        self._ai_pending = True
                        self._ai_delay = 20
                else:
                    piece = self.game_state.board.get_piece(r, c)
                    selectable = self._get_selectable_player()
                    if piece is not None and piece.owner == selectable:
                        moves = self.game_state.board.get_valid_moves(r, c)
                        if moves:
                            self._selected_cell = (r, c)
                            self.renderer.set_selected((r, c))
                            self.renderer.set_valid_moves(moves)
                        else:
                            self._selected_cell = None
                            self.renderer.set_selected(None)
                            self.renderer.set_valid_moves([])
                    else:
                        self._selected_cell = None
                        self.renderer.set_selected(None)
                        self.renderer.set_valid_moves([])

    def _handle_key(self, event):
        if event.key == pygame.K_ESCAPE:
            if self.game_state.is_game_over:
                self._quit_to_menu()
            else:
                dialog = Dialog(self.screen, "确定要返回菜单吗？", "提示", [("确定", True), ("取消", False)])
                result = dialog.show()
                if result:
                    self._quit_to_menu()
        elif event.key == pygame.K_r and self.player_type not in (1, 2):
            self._restart_game()
        elif event.key == pygame.K_RETURN and self.game_state.phase == "setup":
            self._confirm_setup()

    def _update(self):
        if self.client:
            self._process_network_messages()
        if self.player_type == 3:
            if self._ai_pending and self.game_state.phase == "playing" and not self.game_state.is_game_over:
                self._ai_delay -= 1
                self._ai_anim_phase = (self._ai_anim_phase + 1) % 60
                if self._ai_delay <= 0:
                    self._ai_make_move()
                    self._ai_pending = False
            if self._ai_computing:
                self._ai_anim_phase = (self._ai_anim_phase + 1) % 60
                if self._ai_thread is not None and not self._ai_thread.is_alive():
                    self._finish_ai_move()
                elif self._ai_thread is None:
                    self._ai_computing = False
        self._update_battle_results()

    def _process_network_messages(self):
        if self._disconnected:
            return
        messages = self.client.get_all_messages()
        for msg in messages:
            msg_type = msg.get("type")
            if msg_type == "disconnect":
                self.game_started = False
                self._disconnected = True
                self._show_disconnect_dialog()
                return
            elif msg_type == "leave":
                self._show_opponent_left_dialog()
                return
            elif msg_type == "welcome":
                self.server_client_id = msg["data"]["client_id"]
                self.client.player_id = self.server_client_id
            elif msg_type == "game_start":
                self._handle_game_start(msg["data"])
            elif msg_type == "move":
                self._handle_network_move(msg["data"])
            elif msg_type == "setup_sync":
                self._handle_setup_sync(msg["data"])
            elif msg_type == "reset":
                self._handle_network_reset()

    def _handle_game_start(self, data):
        self._full_reset()
        pid_map = data.get("player_id_map", {})
        my_pid_str = str(self.server_client_id)
        my_pid = pid_map.get(my_pid_str, 1)
        if my_pid == 1:
            self.my_player = Player.RED
            self.opponent_player = Player.BLUE
        else:
            self.my_player = Player.BLUE
            self.opponent_player = Player.RED
        self.game_started = True

    def _handle_network_move(self, data):
        if self.game_state.phase != "playing":
            return
        if self.game_state.is_game_over:
            return
        self._ai_pending = False
        self._ai_computing = False
        self._ai_result = None
        self._ai_thread = None
        self._ai_anim_phase = 0
        from_r = data.get("from_row")
        from_c = data.get("from_col")
        to_r = data.get("to_row")
        to_c = data.get("to_col")
        if from_r is None or from_c is None or to_r is None or to_c is None:
            return
        if self.game_state.current_player != self.opponent_player:
            return
        if self.game_state.make_move(from_r, from_c, to_r, to_c):
            self._selected_cell = None
            self.renderer.set_selected(None)
            self.renderer.set_valid_moves([])
            if self.game_state.battle_result:
                self._add_battle_result(self.game_state.battle_result)

    def _handle_setup_sync(self, data):
        if self.game_state.phase != "setup":
            return
        if self._opponent_setup_received:
            return
        if self.opponent_player is None:
            return
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                p = self.game_state.board.get_piece(r, c)
                if p is not None and p.owner == self.opponent_player:
                    self.game_state.board.remove_piece(r, c)
        pieces_data = data.get("pieces", [])
        for r, c, pt, owner in pieces_data:
            piece = Piece(PieceType(pt), Player(owner))
            piece.visible = False
            self.game_state.board.place_piece(r, c, piece)
        if self.opponent_player == Player.RED:
            self.game_state.red_setup_done = True
        else:
            self.game_state.blue_setup_done = True
        self._opponent_setup_received = True
        if self._my_setup_sent and self._opponent_setup_received:
            self.game_state.start_game()
            if self.player_type == 3 and self._is_ai_turn():
                self._ai_pending = True
                self._ai_delay = 20

    def _handle_network_reset(self):
        self._full_reset()
        if self.is_server:
            cids = sorted(self.server.clients.keys()) if self.server else []
            if len(cids) >= 2:
                if random.random() < 0.5:
                    pid_map = {str(cids[0]): 1, str(cids[1]): 2}
                else:
                    pid_map = {str(cids[0]): 2, str(cids[1]): 1}
                self.server._broadcast("game_start", {"player_id_map": pid_map})
        self._waiting_for_rematch = False

    def _get_mode_title(self):
        if self.player_type == 0:
            return "单机对战"
        elif self.player_type == 3:
            return "AI 对战"
        elif self.player_type in (1, 2):
            return "联机对战"
        return "军棋"

    def _draw(self):
        screen_w, screen_h = self.screen.get_size()
        viewer = None if self.player_type == 0 else self.my_player
        self.renderer.draw_board(self.game_state, self._get_mode_title(), viewer=viewer)

        show_panel_player = None
        if self.player_type == 0:
            show_panel_player = None
        elif self.my_player is not None:
            show_panel_player = self.my_player

        if self.game_state.phase == "setup":
            if self.player_type == 0:
                self.renderer.draw_setup_panel(self.game_state, self.my_player, self._selected_piece_type, self._selected_piece_player, show_both=True)
            elif self.my_player is not None:
                self.renderer.draw_setup_panel(self.game_state, self.my_player, self._selected_piece_type, self._selected_piece_player, show_both=False)

        network_info = None
        if self.client and self.game_started:
            if self.my_player is not None:
                my_name = "红方" if self.my_player == Player.RED else "蓝方"
                opp_name = "蓝方" if self.my_player == Player.RED else "红方"
                if self.game_state.phase == "setup":
                    if self._waiting_for_rematch:
                        network_info = "等待对方确认重开..."
                    elif self._my_setup_sent and not self._opponent_setup_received:
                        network_info = f"你: {my_name} (已确认)  |  对手: {opp_name} (布阵中...)"
                    elif not self._my_setup_sent and self._opponent_setup_received:
                        network_info = f"你: {my_name} (布阵中...)  |  对手: {opp_name} (已确认)"
                    elif self._my_setup_sent and self._opponent_setup_received:
                        network_info = f"你: {my_name}  |  对手: {opp_name}  |  即将开始"
                    else:
                        network_info = f"你: {my_name} (布阵中...)  |  对手: {opp_name} (布阵中...)"
                else:
                    network_info = f"你: {my_name}  |  对手: {opp_name}"
        elif self.player_type == 3:
            if self.my_player == Player.RED:
                network_info = "你: 红方  |  对手: 蓝方 (AI)"
            else:
                network_info = "你: 蓝方  |  对手: 红方 (AI)"

        self.renderer.draw_game_info(self.game_state, network_info,
                                     self.my_player, self.opponent_player,
                                     versus_mode=(self.player_type != 0))

        self.renderer.draw_battle_results(self._battle_results, self.game_state.board)

        if self.game_state.is_game_over:
            self.exit_button.visible = False
            self.reset_button.visible = False
            self.confirm_button.visible = False
            self.auto_setup_button.visible = False
            self.restart_button.visible = True
            self.menu_button.visible = True
        else:
            self.exit_button.visible = True
            if self.player_type in (1, 2):
                self.reset_button.visible = False
            elif self.player_type in (0, 3):
                self.reset_button.visible = True
            else:
                self.reset_button.visible = (self.game_state.phase == "playing")
            if self.game_state.phase == "setup":
                self.confirm_button.visible = True
                self.auto_setup_button.visible = True
            else:
                self.confirm_button.visible = False
                self.auto_setup_button.visible = False
            self.restart_button.visible = False
            self.menu_button.visible = False

        if self.game_state.is_game_over and self.game_started:
            self._draw_game_over()

        self.renderer.draw_buttons()

        if not self.game_started and self.player_type != 0 and self.player_type != 3 and not self._disconnected:
            self._draw_waiting()
        if self.player_type == 3 and (self._ai_pending or self._ai_computing):
            self._draw_ai_thinking()

        pygame.display.flip()

    def _draw_game_over(self):
        screen_w, screen_h = self.screen.get_size()
        overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        self.screen.blit(overlay, (0, 0))
        if self.game_state.winner != Player.EMPTY:
            if self.player_type == 0:
                if self.game_state.winner == Player.RED:
                    winner_text = "红方 胜利!"
                else:
                    winner_text = "蓝方 胜利!"
            elif self.player_type == 3:
                if self.game_state.winner == self.my_player:
                    winner_text = "你 胜利!"
                else:
                    winner_text = "AI 胜利!"
            else:
                if self.game_state.winner == self.my_player:
                    winner_text = "你 胜利!"
                else:
                    winner_text = "对手 胜利!"
        else:
            winner_text = "平局!"
        font = get_font(48, bold=True)
        text_surface = font.render(winner_text, True, HIGHLIGHT)
        text_rect = text_surface.get_rect(center=(screen_w // 2, screen_h // 2 - 20))
        self.screen.blit(text_surface, text_rect)

    def _draw_waiting(self):
        screen_w, screen_h = self.screen.get_size()
        font = get_font(36)
        text = font.render("等待对方加入...", True, TEXT_COLOR)
        text_rect = text.get_rect(center=(screen_w // 2, screen_h // 2 - 80))
        background_rect = pygame.Rect(text_rect.left - 20, text_rect.top - 10,
                                       text_rect.width + 40, text_rect.height + 20)
        pygame.draw.rect(self.screen, (240, 240, 240), background_rect, border_radius=10)
        pygame.draw.rect(self.screen, BLACK, background_rect, 2, border_radius=10)
        self.screen.blit(text, text_rect)

        local_ip = self._get_local_ip()
        hint_font = get_font(20)
        ip_text = hint_font.render(f"本机IP: {local_ip}", True, HIGHLIGHT)
        ip_rect = ip_text.get_rect(center=(screen_w // 2, screen_h // 2 - 30))
        self.screen.blit(ip_text, ip_rect)

        hint = hint_font.render("请将此IP告诉对方，让对方在联机模式中输入", True, (100, 100, 100))
        hint_rect = hint.get_rect(center=(screen_w // 2, screen_h // 2 + 5))
        self.screen.blit(hint, hint_rect)

    def _get_local_ip(self):
        if self._local_ip is not None:
            return self._local_ip
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            self._local_ip = ip
            return ip
        except OSError:
            self._local_ip = "127.0.0.1"
            return "127.0.0.1"

    def _draw_ai_thinking(self):
        font = get_font(16)
        dots = "." * (self._ai_anim_phase // 15 % 4)
        text = font.render(f"AI思考中{dots}", True, (255, 200, 100))
        x = self.screen.get_width() - 130
        y = 12
        bg_rect = pygame.Rect(x - 6, y - 2, text.get_width() + 12, text.get_height() + 4)
        pygame.draw.rect(self.screen, (50, 50, 50), bg_rect, border_radius=4)
        self.screen.blit(text, (x, y))

    def _cleanup(self):
        if self._ai_thread is not None and self._ai_thread.is_alive():
            self._ai_computing = False
            self._ai_thread.join(timeout=0.5)
        self._ai_computing = False
        self._ai_result = None
        self._ai_thread = None
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass

    def _show_disconnect_dialog(self):
        self._draw()
        dialog = Dialog(self.screen, "与服务器断开连接!", "错误", [("返回菜单", True)])
        result = dialog.show()
        self._pending_return = "menu"

    def _show_opponent_left_dialog(self):
        self._draw()
        if not self.game_state.is_game_over:
            dialog = Dialog(self.screen, "对方已离开，你赢了!", "游戏结束", [("返回菜单", True)])
            result = dialog.show()
            self._pending_return = "menu"
        else:
            dialog = Dialog(self.screen, "对方已离开", "提示", [("返回菜单", True)])
            result = dialog.show()
            self._pending_return = "menu"
