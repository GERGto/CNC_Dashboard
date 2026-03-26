from __future__ import annotations

import math
import os
import shlex
import subprocess
import threading
import time

from .command_utils import format_command_failure, is_posix_root, run_command


def mock_axes_load(t_ms):
    def base(index):
        value = (math.sin(t_ms / 700.0 + index) * 40.0 + 50.0)
        return round(value, 1)

    return {
        "spindle": base(0),
        "x": base(1),
        "y": base(2),
        "z": base(3),
    }


class ShutdownService:
    def __init__(self, config):
        self.config = config

    def build_shutdown_commands(self):
        if self.config.shutdown_command:
            try:
                return [shlex.split(self.config.shutdown_command)]
            except ValueError:
                return []

        if os.name != "posix":
            return []

        prefix = []
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            prefix = ["sudo", "-n"]

        commands = []
        for command in (
            ["/usr/bin/systemctl", "poweroff"],
            ["/usr/sbin/shutdown", "-h", "now"],
            ["/usr/sbin/poweroff"],
        ):
            if os.path.exists(command[0]):
                commands.append(prefix + command)
        return commands

    def blackout_display_for_shutdown(self):
        if os.name != "posix":
            return False

        display_env = {"DISPLAY": self.config.kiosk_display}
        if self.config.kiosk_xauthority:
            display_env["XAUTHORITY"] = self.config.kiosk_xauthority

        xset_result = None
        if self.config.kiosk_display:
            run_command(["xset", "-display", self.config.kiosk_display, "+dpms"], timeout=2, env=display_env)
            xset_result = run_command(
                ["xset", "-display", self.config.kiosk_display, "dpms", "force", "off"],
                timeout=2,
                env=display_env,
            )
            if xset_result and xset_result.returncode == 0:
                return True

        if is_posix_root():
            vcgencmd_result = run_command(["vcgencmd", "display_power", "0"], timeout=2)
            if vcgencmd_result and vcgencmd_result.returncode == 0:
                return True

        detail = format_command_failure(xset_result, "Display blackout command failed")
        print(detail, flush=True)
        return False

    def execute_shutdown_request(self):
        self.blackout_display_for_shutdown()

        if self.config.shutdown_delay_sec > 0:
            time.sleep(self.config.shutdown_delay_sec)

        commands = self.build_shutdown_commands()
        failures = []

        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                failures.append(f"{command}: {exc}")
                continue

            if result.returncode == 0:
                return

            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            detail = stderr or stdout or f"exit code {result.returncode}"
            failures.append(f"{command}: {detail}")

        print("Failed to execute system shutdown request:", " | ".join(failures), flush=True)

    def request_system_shutdown(self):
        if not self.config.enable_real_shutdown:
            return False, "Real shutdown is disabled"

        commands = self.build_shutdown_commands()
        if not commands:
            return False, "No shutdown command is available"

        worker = threading.Thread(target=self.execute_shutdown_request, daemon=True)
        worker.start()
        return True, "Shutdown scheduled"
