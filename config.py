import pygame

BOARD_COLS = 5
BOARD_ROWS = 13
BASE_CELL_WIDTH = 80
BASE_CELL_HEIGHT = 55
MARGIN = 50
TITLE_BAR_HEIGHT = 40
SIDE_PANEL_WIDTH = 200
STATUS_BAR_HEIGHT = 60

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BACKGROUND = (200, 180, 140)
BOARD_BG = (220, 200, 150)
LINE_COLOR = (60, 40, 20)
HIGHLIGHT = (255, 0, 0)
TEXT_COLOR = (30, 30, 30)
BUTTON_COLOR = (70, 130, 180)
BUTTON_HOVER = (100, 160, 210)
BUTTON_TEXT = (255, 255, 255)
RED_COLOR = (220, 60, 60)
BLUE_COLOR = (60, 100, 200)
CAMP_COLOR = (180, 220, 180)
HQ_COLOR = (255, 220, 180)
MOUNTAIN_COLOR = (200, 180, 160)
RAILWAY_COLOR = (160, 160, 160)
SELECTED_COLOR = (255, 255, 100)
VALID_MOVE_COLOR = (100, 255, 100, 80)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000

FPS = 60

USE_RESIZABLE = True


def calc_window_size():
    try:
        pygame.display.init()
        screen_info = pygame.display.Info()
        sw = screen_info.current_w
        sh = screen_info.current_h
        taskbar_h = 40
        usable_h = sh - taskbar_h - 40

        board_w = BOARD_COLS * BASE_CELL_WIDTH + 2 * MARGIN
        total_w = 2 * SIDE_PANEL_WIDTH + board_w
        board_h = BOARD_ROWS * BASE_CELL_HEIGHT + 2 * MARGIN
        total_h = board_h + TITLE_BAR_HEIGHT + STATUS_BAR_HEIGHT + 10

        scale_w = (sw - 40) / total_w if total_w > 0 else 1
        scale_h = usable_h / total_h if total_h > 0 else 1
        scale = min(1, scale_w, scale_h)

        if scale < 1:
            cell_w = max(40, int(BASE_CELL_WIDTH * scale))
            cell_h = max(28, int(BASE_CELL_HEIGHT * scale))
        else:
            cell_w = BASE_CELL_WIDTH
            cell_h = BASE_CELL_HEIGHT

        window_w = 2 * SIDE_PANEL_WIDTH + BOARD_COLS * cell_w + 2 * MARGIN
        window_h = BOARD_ROWS * cell_h + 2 * MARGIN + TITLE_BAR_HEIGHT + STATUS_BAR_HEIGHT + 10

        max_w = sw - 40
        max_h = usable_h
        window_w = min(window_w, max_w)
        window_h = min(window_h, max_h)

        pygame.display.quit()
        return window_w, window_h, cell_w, cell_h
    except Exception:
        return 900, 850, BASE_CELL_WIDTH, BASE_CELL_HEIGHT


_win_result = calc_window_size()
WINDOW_WIDTH = _win_result[0]
WINDOW_HEIGHT = _win_result[1]
CELL_WIDTH = _win_result[2]
CELL_HEIGHT = _win_result[3]
