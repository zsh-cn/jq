import sys
import os


def is_windows():
    return sys.platform == "win32"


def is_admin():
    if not is_windows():
        return True
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def elevate_and_restart(extra_args=None):
    if not is_windows():
        return False
    if is_admin():
        return True

    try:
        import ctypes
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
            params = ""
        else:
            exe_path = sys.executable
            script_path = os.path.abspath(sys.argv[0])
            params = f'"{script_path}"'

        if extra_args:
            params += " " + " ".join(f'"{a}"' for a in extra_args)

        ret = ctypes.windll.shell32.ShellExecuteW(
            0,
            "runas",
            exe_path,
            params,
            os.getcwd(),
            1
        )
        return ret > 32
    except Exception:
        return False