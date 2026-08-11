import pygame
import sys
from config import *
from utils.fonts import get_font


class Dialog:
    def __init__(self, surface, message, title="提示", buttons=None, dialog_width=400):
        self.surface = surface
        self.message = message
        self.title = title
        self.buttons = buttons or [("确定", True)]
        self.dialog_width = dialog_width
        self.font_title = get_font(24, bold=True)
        self.font_message = get_font(20)
        self.font_button = get_font(20)
        self.result = None
        self.hovered_index = -1
        self._screen_snapshot = None
        self._calculate_layout()

    def _calculate_layout(self):
        message_lines = self.message.split('\n')
        line_height = 30
        content_height = len(message_lines) * line_height
        top_padding = 40
        bottom_padding = 70
        title_height = 40
        dialog_h = top_padding + title_height + content_height + bottom_padding
        dialog_h = max(dialog_h, 180)
        surf_w, surf_h = self.surface.get_size()
        self.rect = pygame.Rect(
            (surf_w - self.dialog_width) // 2,
            max(10, (surf_h - dialog_h) // 2),
            self.dialog_width,
            dialog_h
        )
        self.button_rects = []
        btn_w = 100
        btn_h = 40
        spacing = 20
        total_w = len(self.buttons) * btn_w + (len(self.buttons) - 1) * spacing
        start_x = self.rect.centerx - total_w // 2
        for i, (text, value) in enumerate(self.buttons):
            x = start_x + i * (btn_w + spacing)
            y = self.rect.bottom - 60
            self.button_rects.append((pygame.Rect(x, y, btn_w, btn_h), text, value))
        self._message_lines = message_lines

    def show(self):
        self._calculate_layout()
        self._screen_snapshot = self.surface.copy()
        self._draw_dialog()
        pygame.display.flip()
        self._wait_for_input()
        return self.result

    def _draw_dialog(self):
        current_size = self.surface.get_size()
        if self._screen_snapshot and self._screen_snapshot.get_size() == current_size:
            self.surface.blit(self._screen_snapshot, (0, 0))
        else:
            self._screen_snapshot = self.surface.copy()

        overlay = pygame.Surface(current_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        self.surface.blit(overlay, (0, 0))

        pygame.draw.rect(self.surface, (240, 240, 240), self.rect, border_radius=10)
        pygame.draw.rect(self.surface, BLACK, self.rect, 2, border_radius=10)

        title_surface = self.font_title.render(self.title, True, TEXT_COLOR)
        title_rect = title_surface.get_rect(center=(self.rect.centerx, self.rect.top + 35))
        self.surface.blit(title_surface, title_rect)

        y_offset = self.rect.top + 75
        for line in self._message_lines:
            msg_surface = self.font_message.render(line, True, TEXT_COLOR)
            msg_rect = msg_surface.get_rect(center=(self.rect.centerx, y_offset))
            self.surface.blit(msg_surface, msg_rect)
            y_offset += 30

        for i, (rect, text, value) in enumerate(self.button_rects):
            color = BUTTON_HOVER if i == self.hovered_index else BUTTON_COLOR
            pygame.draw.rect(self.surface, color, rect, border_radius=5)
            pygame.draw.rect(self.surface, BLACK, rect, 2, border_radius=5)
            btn_text = self.font_button.render(text, True, BUTTON_TEXT)
            btn_rect = btn_text.get_rect(center=rect.center)
            self.surface.blit(btn_text, btn_rect)

    def _wait_for_input(self):
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == pygame.VIDEORESIZE:
                    self._calculate_layout()
                    self._draw_dialog()
                    pygame.display.flip()
                elif event.type == pygame.MOUSEMOTION:
                    pos = event.pos
                    new_hover = -1
                    for i, (rect, _, _) in enumerate(self.button_rects):
                        if rect.collidepoint(pos):
                            new_hover = i
                            break
                    if new_hover != self.hovered_index:
                        self.hovered_index = new_hover
                        self._draw_dialog()
                        pygame.display.flip()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    pos = event.pos
                    for i, (rect, text, value) in enumerate(self.button_rects):
                        if rect.collidepoint(pos):
                            self.result = value
                            waiting = False
                            break
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        self.result = self.button_rects[0][2]
                        waiting = False
                        break
                    elif event.key == pygame.K_ESCAPE:
                        if len(self.button_rects) >= 2:
                            self.result = self.button_rects[-1][2]
                        else:
                            self.result = False
                        waiting = False
                        break
            if waiting:
                pygame.time.wait(30)
