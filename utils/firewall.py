import sys
import os
import subprocess


def _get_exe_path():
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        return os.path.abspath(sys.argv[0])


def add_firewall_rule(rule_name):
    if sys.platform != "win32":
        return True

    exe_path = _get_exe_path()

    check_cmd = (
        f'netsh advfirewall firewall show rule name="{rule_name}"'
    )
    try:
        result = subprocess.run(
            check_cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0 and rule_name in result.stdout:
            return True
    except Exception:
        pass

    add_cmd = (
        f'netsh advfirewall firewall add rule '
        f'name="{rule_name}" '
        f'dir=in action=allow '
        f'profile=any '
        f'program="{exe_path}"'
    )
    try:
        result = subprocess.run(
            add_cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def remove_firewall_rule(rule_name):
    if sys.platform != "win32":
        return True

    cmd = f'netsh advfirewall firewall delete rule name="{rule_name}"'
    try:
        result = subprocess.run(
            cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False