import sys
import os
import traceback
from datetime import datetime


def _get_log_path():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'military_chess_error.log')


def _write_error_log(error_msg):
    try:
        log_path = _get_log_path()
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}\n")
    except Exception:
        pass


def _show_error_dialog(title, message):
    try:
        import pygame
        pygame.init()
        screen = pygame.display.set_mode((500, 200))
        pygame.display.set_caption(title)
        font = pygame.font.SysFont(None, 24)
        small_font = pygame.font.SysFont(None, 18)
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
            screen.fill((240, 240, 240))
            lines = message.split('\n')
            y = 40
            for line in lines:
                text = font.render(line, True, (30, 30, 30))
                screen.blit(text, (20, y))
                y += 30
            hint = small_font.render("请查看 military_chess_error.log 获取详细信息", True, (100, 100, 100))
            screen.blit(hint, (20, y + 10))
            pygame.display.flip()
    except Exception:
        pass


def main():
    try:
        import pygame
        from game import MilitaryChessGame
        from ui.menu import Menu

        pygame.init()
        saved_window_size = None
        menu = None

        while True:
            if menu is None:
                menu = Menu(window_size=saved_window_size)
            result = menu.run()
            if result[0] is None:
                break
            saved_window_size = menu.screen.get_size()
            is_server, player, host, port = result[0], result[1], result[2], result[3]

            game = MilitaryChessGame(is_server=is_server, player=player, host=host, port=port,
                             window_size=saved_window_size)
            return_code = game.run()
            if return_code == "quit":
                break
            saved_window_size = game.screen.get_size()
            menu = None
    except Exception as e:
        error_detail = traceback.format_exc()
        _write_error_log(error_detail)
        try:
            _show_error_dialog("启动错误", f"{type(e).__name__}: {e}")
        except Exception:
            print(f"启动错误: {error_detail}")
        sys.exit(1)


if __name__ == "__main__":
    main()