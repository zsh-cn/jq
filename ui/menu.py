import pygame
import socket
import sys
from config import *
from utils.fonts import get_font
from utils.admin import is_admin, elevate_and_restart


class InputBox:
    def __init__(self, rect, placeholder, font, max_length=50):
        self.rect = rect
        self.placeholder = placeholder
        self.font = font
        self.text = ""
        self.active = False
        self.max_length = max_length
        self.cursor_pos = 0
        self.select_start = None
        self.select_end = None

    def activate(self):
        self.active = True
        self.cursor_pos = len(self.text)
        self.select_start = None
        self.select_end = None

    def deactivate(self):
        self.active = False
        self.select_start = None
        self.select_end = None

    def _get_selection(self):
        if self.select_start is not None and self.select_end is not None:
            return min(self.select_start, self.select_end), max(self.select_start, self.select_end)
        return None

    def handle_event(self, event):
        if not self.active:
            return None
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.deactivate()
                return self.text
            elif event.key == pygame.K_ESCAPE:
                self.deactivate()
                return None
            elif event.key == pygame.K_BACKSPACE:
                sel = self._get_selection()
                if sel:
                    s, e = sel
                    self.text = self.text[:s] + self.text[e:]
                    self.cursor_pos = s
                    self.select_start = None
                    self.select_end = None
                elif self.cursor_pos > 0:
                    self.text = self.text[:self.cursor_pos - 1] + self.text[self.cursor_pos:]
                    self.cursor_pos -= 1
            elif event.key == pygame.K_DELETE:
                sel = self._get_selection()
                if sel:
                    s, e = sel
                    self.text = self.text[:s] + self.text[e:]
                    self.cursor_pos = s
                    self.select_start = None
                    self.select_end = None
                elif self.cursor_pos < len(self.text):
                    self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos + 1:]
            elif event.key == pygame.K_LEFT:
                if self.select_start is not None and self.select_end is not None:
                    self.cursor_pos = min(self.select_start, self.select_end)
                    self.select_start = None
                    self.select_end = None
                elif self.cursor_pos > 0:
                    self.cursor_pos -= 1
            elif event.key == pygame.K_RIGHT:
                if self.select_start is not None and self.select_end is not None:
                    self.cursor_pos = max(self.select_start, self.select_end)
                    self.select_start = None
                    self.select_end = None
                elif self.cursor_pos < len(self.text):
                    self.cursor_pos += 1
            elif event.key == pygame.K_HOME:
                self.cursor_pos = 0
                self.select_start = None
                self.select_end = None
            elif event.key == pygame.K_END:
                self.cursor_pos = len(self.text)
                self.select_start = None
                self.select_end = None
            else:
                if event.unicode and event.unicode.isprintable():
                    sel = self._get_selection()
                    if sel:
                        s, e = sel
                        new_text = self.text[:s] + event.unicode + self.text[e:]
                        if len(new_text) <= self.max_length:
                            self.text = new_text
                            self.cursor_pos = s + len(event.unicode)
                    else:
                        if len(self.text) < self.max_length:
                            self.text = self.text[:self.cursor_pos] + event.unicode + self.text[self.cursor_pos:]
                            self.cursor_pos += len(event.unicode)
                    self.select_start = None
                    self.select_end = None
        return None

    def draw(self, surface):
        color = (100, 150, 255) if self.active else WHITE
        pygame.draw.rect(surface, color, self.rect, border_radius=5)
        pygame.draw.rect(surface, BLACK, self.rect, 2, border_radius=5)
        display_text = self.text if self.text else self.placeholder
        text_color = TEXT_COLOR if self.text else (150, 150, 150)
        text_surface = self.font.render(display_text, True, text_color)
        base_y = self.rect.y + (self.rect.height - self.font.get_height()) // 2
        surface.blit(text_surface, (self.rect.x + 10, base_y))
        if self.active:
            sel = self._get_selection()
            if sel:
                s, e = sel
                before = self.text[:s]
                selected = self.text[s:e]
                x_start = self.rect.x + 10 + self.font.size(before)[0]
                x_end = x_start + self.font.size(selected)[0]
                sel_rect = pygame.Rect(x_start, base_y, x_end - x_start, self.font.get_height())
                bg = pygame.Surface((sel_rect.width, sel_rect.height), pygame.SRCALPHA)
                bg.fill((100, 150, 255, 100))
                surface.blit(bg, sel_rect.topleft)
            cursor_x = self.rect.x + 10 + self.font.size(self.text[:self.cursor_pos])[0]
            cursor_y = base_y
            if sel is None or cursor_x != self.rect.x + 10 + self.font.size(self.text[:sel[0]])[0]:
                pygame.draw.line(surface, TEXT_COLOR,
                                 (cursor_x, cursor_y),
                                 (cursor_x, cursor_y + self.font.get_height()), 2)

    def get_text(self):
        return self.text

    def set_text(self, text):
        self.text = text
        self.cursor_pos = len(text)
        self.select_start = None
        self.select_end = None


class Button:
    def __init__(self, rect, text, font, callback=None):
        self.rect = rect
        self.text = text
        self.font = font
        self.callback = callback
        self.hovered = False
        self.visible = True

    def draw(self, surface):
        if not self.visible:
            return
        color = BUTTON_HOVER if self.hovered else BUTTON_COLOR
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, BLACK, self.rect, 2, border_radius=8)
        text_surface = self.font.render(self.text, True, BUTTON_TEXT)
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)

    def handle_event(self, event):
        if not self.visible:
            return
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos) and self.callback:
                self.callback()


class Menu:
    def __init__(self, window_size=None):
        pygame.init()
        if window_size:
            self.screen = pygame.display.set_mode(window_size, pygame.RESIZABLE)
        else:
            self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("军棋 - 联机对战")
        self.clock = pygame.time.Clock()
        self.font_title = get_font(42, bold=True)
        self.font_button = get_font(26)
        self.font_input = get_font(24)
        self.font_small = get_font(16)
        self.state = "main"
        self.buttons = []
        self.input_boxes = []
        self.is_server = None
        self.player = None
        self.host = None
        self.port = None
        self.running = False
        self._local_ip = None
        self._ip_error_timer = 0
        self._create_main_buttons()

    def _get_screen_size(self):
        return self.screen.get_size()

    def _create_main_buttons(self):
        screen_w, screen_h = self._get_screen_size()
        center_x = screen_w // 2
        btn_h = 50
        btn_spacing = 15
        total_btns_h = 4 * btn_h + 3 * btn_spacing
        title_h = 50
        title_spacing = 20
        total_content_h = title_h + title_spacing + total_btns_h
        start_y = max(10, (screen_h - total_content_h) // 2)

        self.buttons = [
            Button(
                pygame.Rect(center_x - 130, start_y + title_h + title_spacing, 260, btn_h),
                "创建房间",
                self.font_button,
                lambda: self._show_create_screen()
            ),
            Button(
                pygame.Rect(center_x - 130, start_y + title_h + title_spacing + btn_h + btn_spacing, 260, btn_h),
                "联机模式",
                self.font_button,
                lambda: self._show_lobby_screen()
            ),
            Button(
                pygame.Rect(center_x - 130, start_y + title_h + title_spacing + 2 * (btn_h + btn_spacing), 260, btn_h),
                "AI模式",
                self.font_button,
                lambda: self._start_ai_game()
            ),
            Button(
                pygame.Rect(center_x - 130, start_y + title_h + title_spacing + 3 * (btn_h + btn_spacing), 260, btn_h),
                "单机模式",
                self.font_button,
                lambda: self._start_game(is_server=False, player=0)
            ),
        ]
        self._title_y = start_y
        self.input_boxes = []

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

    def _show_create_screen(self):
        screen_w, screen_h = self._get_screen_size()
        self.state = "create"
        center_x = screen_w // 2
        self.input_boxes = []
        btn_h = 50
        btn_spacing = 15
        ip_section_h = 80
        hint_h = 30
        total_h = ip_section_h + hint_h + 2 * btn_h + btn_spacing
        start_y = (screen_h - total_h) // 2 + 30
        self.buttons = [
            Button(
                pygame.Rect(center_x - 130, start_y + ip_section_h + hint_h, 260, btn_h),
                "创建房间",
                self.font_button,
                lambda: self._start_game(is_server=True, player=1)
            ),
            Button(
                pygame.Rect(center_x - 130, start_y + ip_section_h + hint_h + btn_h + btn_spacing, 260, btn_h),
                "返回",
                self.font_button,
                lambda: self._show_main()
            ),
        ]
        self._content_start_y = start_y
        self._title_y = max(10, start_y - 60)

    def _show_lobby_screen(self, preserved_text=None):
        screen_w, screen_h = self._get_screen_size()
        self.state = "lobby"
        center_x = screen_w // 2
        local_ip = self._get_local_ip()
        ip_hint = local_ip[:local_ip.rfind(".") + 1] if "." in local_ip else "192.168.1."
        ip_section_h = 60
        input_section_h = 70
        btn_h = 50
        btn_spacing = 15
        total_h = ip_section_h + input_section_h + 2 * btn_h + btn_spacing
        start_y = (screen_h - total_h) // 2 + 30
        ip_rect = pygame.Rect(center_x - 100, start_y + ip_section_h, 200, 40)
        self.ip_box = InputBox(ip_rect, ip_hint, self.font_input, 15)
        if preserved_text is not None:
            self.ip_box.set_text(preserved_text)
        else:
            self.ip_box.set_text("")
        self.input_boxes = [self.ip_box]
        self.buttons = [
            Button(
                pygame.Rect(center_x - 130, start_y + ip_section_h + input_section_h, 260, btn_h),
                "连接",
                self.font_button,
                lambda: self._join_by_ip()
            ),
            Button(
                pygame.Rect(center_x - 130, start_y + ip_section_h + input_section_h + btn_h + btn_spacing, 260, btn_h),
                "返回",
                self.font_button,
                lambda: self._show_main()
            ),
        ]
        self._content_start_y = start_y
        self._title_y = max(10, start_y - 60)

    def _join_by_ip(self):
        self.is_server = False
        self.player = 2
        self.host = self.ip_box.get_text().strip()
        self.port = DEFAULT_PORT
        if self.host:
            if not self._validate_ip(self.host):
                self._ip_error_timer = 120
                return
            self.running = False

    def _validate_ip(self, ip):
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        for part in parts:
            if not part.isdigit():
                return False
            num = int(part)
            if num < 0 or num > 255:
                return False
        return True

    def _show_main(self):
        self.state = "main"
        self._create_main_buttons()

    def _start_game(self, is_server, player):
        if is_server and not is_admin():
            if elevate_and_restart():
                pygame.quit()
                sys.exit(0)
            return

        self.is_server = is_server
        self.player = player
        if is_server:
            self.host = "0.0.0.0"
            self.port = DEFAULT_PORT
        else:
            self.host = "127.0.0.1"
            self.port = DEFAULT_PORT
        self.running = False

    def _start_ai_game(self):
        self.is_server = False
        self.player = 3
        self.host = "127.0.0.1"
        self.port = DEFAULT_PORT
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            self._process_events()
            self._draw()
            self.clock.tick(FPS)
        return (getattr(self, 'is_server', None),
                getattr(self, 'player', None),
                getattr(self, 'host', None),
                getattr(self, 'port', None))

    def _process_events(self):
        active_box = None
        for box in self.input_boxes:
            if box.active:
                active_box = box
                break

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            if event.type == pygame.KEYDOWN:
                if active_box:
                    active_box.handle_event(event)
                    if not active_box.active:
                        active_box = None
                    continue
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                if self.state == "main":
                    self._create_main_buttons()
                elif self.state == "create":
                    self._show_create_screen()
                elif self.state == "lobby":
                    preserved = self.ip_box.get_text() if hasattr(self, 'ip_box') and self.ip_box else ""
                    self._show_lobby_screen(preserved_text=preserved)

            if event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.MOUSEMOTION:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    clicked_box = None
                    for box in self.input_boxes:
                        if box.rect.collidepoint(event.pos):
                            clicked_box = box
                            break
                    if clicked_box:
                        if active_box and active_box != clicked_box:
                            active_box.deactivate()
                        clicked_box.activate()
                        active_box = clicked_box
                        continue
                    if active_box:
                        active_box.deactivate()
                        active_box = None
                for button in self.buttons:
                    if event.type == pygame.MOUSEMOTION:
                        button.hovered = button.rect.collidepoint(event.pos)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if button.rect.collidepoint(event.pos) and button.callback:
                            button.callback()

    def _draw(self):
        screen_w, screen_h = self._get_screen_size()
        self.screen.fill(BACKGROUND)
        title_text = "军棋 联机对战"
        title = self.font_title.render(title_text, True, TEXT_COLOR)
        title_rect = title.get_rect(center=(screen_w // 2, self._title_y + title.get_height() // 2))
        self.screen.blit(title, title_rect)

        if self.state == "create":
            self._draw_create_screen()
        elif self.state == "lobby":
            self._draw_lobby_screen()

        for box in self.input_boxes:
            box.draw(self.screen)

        for button in self.buttons:
            button.draw(self.screen)

        pygame.display.flip()

    def _draw_create_screen(self):
        screen_w, screen_h = self._get_screen_size()
        center_x = screen_w // 2
        local_ip = self._get_local_ip()
        ip_font = get_font(24)
        start_y = self._content_start_y
        ip_label = ip_font.render("本机IP:", True, TEXT_COLOR)
        self.screen.blit(ip_label, (center_x - 195, start_y))
        ip_value = ip_font.render(local_ip, True, HIGHLIGHT)
        self.screen.blit(ip_value, (center_x - 60, start_y))

        hint_font = get_font(16)
        hint = hint_font.render("请将此IP分享给对方，让对方在联机模式中连接", True, (100, 100, 100))
        self.screen.blit(hint, (center_x - hint.get_width() // 2, start_y + 40))

    def _draw_lobby_screen(self):
        screen_w, screen_h = self._get_screen_size()
        center_x = screen_w // 2
        label_font = self.font_input
        start_y = self._content_start_y
        ip_label = label_font.render("主机IP:", True, TEXT_COLOR)
        self.screen.blit(ip_label, (center_x - 195, start_y))
        if self._ip_error_timer > 0:
            error_font = get_font(16)
            error_text = error_font.render("IP地址格式无效，请输入正确的IP", True, HIGHLIGHT)
            self.screen.blit(error_text, (center_x - error_text.get_width() // 2, start_y + 45))
            self._ip_error_timer -= 1