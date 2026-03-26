from __future__ import annotations

import os
import shutil
import subprocess


def dedupe_strings(values):
    unique = []
    seen = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def is_posix_root():
    return os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0


def resolve_executable(executable):
    value = str(executable or "").strip()
    if not value:
        return ""
    if os.path.isabs(value):
        return value if os.path.exists(value) else ""

    resolved = shutil.which(value)
    if resolved:
        return resolved

    if os.name == "posix":
        for directory in ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"):
            candidate = os.path.join(directory, value)
            if os.path.exists(candidate):
                return candidate
    return ""


def resolve_command(command):
    if not isinstance(command, (list, tuple)) or not command:
        return []
    executable = resolve_executable(command[0])
    if not executable:
        return []
    return [executable, *[str(part) for part in command[1:]]]


def read_text_file(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (FileNotFoundError, OSError):
        return ""


def run_command(command, timeout=5, allow_sudo=False, input_text=None, prefer_sudo=False, sudo_only=False, env=None):
    resolved = resolve_command(command)
    if not resolved:
        return None

    attempts = [resolved]
    if allow_sudo and os.name == "posix" and not is_posix_root():
        sudo_executable = resolve_executable("sudo")
        if sudo_executable:
            sudo_command = [sudo_executable, "-n", *resolved]
            if sudo_only:
                attempts = [sudo_command]
            else:
                attempts = [sudo_command, *attempts] if prefer_sudo else [*attempts, sudo_command]

    last_result = None
    for candidate in attempts:
        try:
            run_env = None
            if env:
                run_env = os.environ.copy()
                run_env.update({str(key): str(value) for key, value in env.items() if value is not None})
            result = subprocess.run(
                candidate,
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                env=run_env,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        last_result = result
        if result.returncode == 0:
            return result
    return last_result


def format_command_failure(result, fallback_message):
    if result is None:
        return fallback_message
    stderr = str(result.stderr or "").strip()
    stdout = str(result.stdout or "").strip()
    detail = stderr or stdout or f"exit code {result.returncode}"
    return f"{fallback_message}: {detail}"
