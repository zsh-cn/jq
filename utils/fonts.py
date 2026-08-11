import pygame
import os
import sys


_font_cache = {}


def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_font_paths():
    base_path = get_base_path()
    paths = []
    bundled_font = os.path.join(base_path, "assets", "fonts", "simhei.ttf")
    if os.path.isfile(bundled_font):
        paths.append(bundled_font)
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        paths.extend([
            os.path.join(windir, "Fonts", "simhei.ttf"),
            os.path.join(windir, "Fonts", "msyh.ttc"),
            os.path.join(windir, "Fonts", "simsun.ttc"),
            os.path.join(windir, "Fonts", "msyhbd.ttc"),
        ])
    elif sys.platform == "darwin":
        paths.extend([
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/Library/Fonts/Songti.ttc",
        ])
    else:
        paths.extend([
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        ])
    return paths


def load_font(size, bold=False):
    cache_key = (size, bold)
    if cache_key in _font_cache:
        return _font_cache[cache_key]
    font = None
    font_paths = get_font_paths()
    for font_path in font_paths:
        if os.path.isfile(font_path):
            try:
                font = pygame.font.Font(font_path, size)
                _font_cache[cache_key] = font
                return font
            except Exception:
                continue
    try:
        font = pygame.font.SysFont(None, size, bold=bold)
    except Exception:
        font = pygame.font.Font(None, size)
    _font_cache[cache_key] = font
    return font


def get_font(size, bold=False):
    return load_font(size, bold=bold)
