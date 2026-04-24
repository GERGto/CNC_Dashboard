from __future__ import annotations

import math
import os
import threading
import time
from datetime import datetime, timezone


def iso_now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_state_id(state_id):
    key = str(state_id or "").strip().lower()
    aliases = {
        "off": "off",
        "black": "off",
        "on": "on",
        "white": "on",
        "idle": "idle",
        "warning": "warning",
        "maintenance": "warning",
        "orange": "warning",
        "running": "running",
        "run": "running",
        "green": "running",
        "estop": "eStop",
        "e-stop": "eStop",
        "error": "eStop",
        "red": "eStop",
    }
    return aliases.get(key, "idle")


def _clamp_uint8(value, default_value):
    try:
        return max(0, min(255, int(value)))
    except (ValueError, TypeError):
        return int(default_value)


def _clamp_percent(value, default_value, minimum=0, maximum=100):
    try:
        return max(int(minimum), min(int(maximum), int(value)))
    except (ValueError, TypeError):
        return max(int(minimum), min(int(maximum), int(default_value)))


def _lerp_channel(start_value, end_value, progress):
    factor = max(0.0, min(1.0, float(progress)))
    return int(round(start_value + ((end_value - start_value) * factor)))


def _scale_color(color, factor):
    scale = max(0.0, min(1.0, float(factor)))
    red_value, green_value, blue_value = color
    return (
        int(round(red_value * scale)),
        int(round(green_value * scale)),
        int(round(blue_value * scale)),
    )


def _blend_color(start_color, end_color, factor):
    blend = max(0.0, min(1.0, float(factor)))
    return (
        _lerp_channel(start_color[0], end_color[0], blend),
        _lerp_channel(start_color[1], end_color[1], blend),
        _lerp_channel(start_color[2], end_color[2], blend),
    )


class NeoPixelStatusStripController:
    CONTROLLER_ID = "ws2812b-status-strip"
    DISPLAY_NAME = "WS2812B Status-LED-Streifen"
    DIMMABLE_STATES = frozenset({"idle", "warning", "running"})
    DYNAMIC_BRIGHTNESS_MIN_PERCENT = 10
    STATIC_STATE_COLORS = {
        "off": (0, 0, 0),
        "on": (255, 255, 255),
        "warning": (255, 96, 0),
        "running": (0, 255, 0),
        "eStop": (255, 0, 0),
    }
    STARTUP_BLUE = (0, 96, 255)
    IDLE_WHITE_MIN = 28
    IDLE_WHITE_MAX = 127
    IDLE_PHASE_STEP_PER_FRAME = 0.012
    IDLE_PIXEL_PHASE_OFFSET = 0.12
    ESTOP_RED_BASE = 96
    ESTOP_RED_PEAK = 255
    ESTOP_PULSE_PERIOD_SEC = 1.35
    ESTOP_PULSE_WIDTH_SEC = 0.18
    ESTOP_FIRST_PULSE_CENTER_SEC = 0.16
    ESTOP_SECOND_PULSE_CENTER_SEC = 0.42
    WARNING_PULSE_PERIOD_SEC = 2.6
    WARNING_PULSE_MIN_FACTOR = 0.28
    WARNING_PULSE_MAX_FACTOR = 0.92
    RUNNING_BASE_GREEN = (0, 56, 0)
    RUNNING_HOTSPOT_GREEN = (0, 255, 0)
    RUNNING_TAIL_PIXELS = 44.0
    RUNNING_SMOOTHING_TIME_SEC = 0.28
    ANIMATION_FPS = 60.0
    BOOT_EXPAND_DURATION_SEC = 1.8
    SYSTEM_CHECK_FADE_DURATION_SEC = 1.2
    STATE_BLEND_DURATION_SEC = 1.6
    SHUTDOWN_COLLAPSE_DURATION_SEC = 0.45
    STATIC_REFRESH_SEC = 0.25
    STARTUP_RENDER_STATE = "startupExpand"
    SYSTEM_CHECK_RENDER_STATE = "systemCheck"
    STATE_BLEND_RENDER_STATE = "stateBlend"
    RUNNING_RENDER_STATE = "runningLoadHotspot"
    WARNING_RENDER_STATE = "warningPulse"
    ESTOP_RENDER_STATE = "eStopPulse"
    SHUTDOWN_RENDER_STATE = "shutdownCollapse"
    SHUTDOWN_OFF_RENDER_STATE = "shutdownOff"

    def __init__(
        self,
        pixel_count=59,
        gpio_pin=18,
        frequency_hz=800000,
        dma_channel=10,
        invert=False,
        brightness=64,
        pwm_channel=0,
        strip_type="GRB",
        enabled=True,
        dynamic_brightness_percent=100,
    ):
        self.enabled = bool(enabled)
        self.pixel_count = max(1, int(pixel_count))
        self.gpio_pin = int(gpio_pin)
        self.frequency_hz = max(1, int(frequency_hz))
        self.dma_channel = max(0, int(dma_channel))
        self.invert = bool(invert)
        self.brightness = _clamp_uint8(brightness, 64)
        self.pwm_channel = max(0, int(pwm_channel))
        self.strip_type = str(strip_type or "GRB").strip().upper() or "GRB"
        self._dynamic_brightness_percent = _clamp_percent(
            dynamic_brightness_percent,
            100,
            minimum=self.DYNAMIC_BRIGHTNESS_MIN_PERCENT,
            maximum=100,
        )
        self._lock = threading.Lock()
        self._driver_checked = False
        self._driver = None
        self._driver_error = ""
        self._strip_type_value = None
        self._strip = None
        self._animator_thread = None
        self._wake_event = threading.Event()
        self._boot_started = False
        self._boot_completed = False
        self._boot_phase = "pending"
        self._boot_phase_started_monotonic = None
        self._boot_light_callback = None
        self._boot_light_triggered = False
        self._shutdown_active = False
        self._shutdown_phase = "idle"
        self._shutdown_phase_started_monotonic = None
        self._shutdown_base_frame = None
        self._shutdown_completion_callback = None
        self._shutdown_callback_triggered = False
        self._shutdown_completed_event = threading.Event()
        self._shutdown_completed_event.set()
        self._desired_state = "idle"
        self._render_state = "off"
        self._last_reason = ""
        self._last_source = "backend"
        self._last_color = self.STATIC_STATE_COLORS["off"]
        self._last_pixels = None
        self._center_groups = self._build_center_groups()
        self._idle_phase = 0.0
        self._running_load_percent = 0.0
        self._running_display_position = 0.0
        self._running_last_frame_monotonic = None
        self._last_command_at = None
        self._last_success_at = None
        self._last_error = ""

    def get_snapshot(self):
        with self._lock:
            return self._build_snapshot_locked()

    def set_state(self, state_id, reason="", source="machine-status"):
        normalized_state = _normalize_state_id(state_id)
        normalized_reason = str(reason or "").strip()
        normalized_source = str(source or "machine-status").strip() or "machine-status"
        command_at = iso_now_utc()

        with self._lock:
            self._desired_state = normalized_state
            self._last_reason = normalized_reason
            self._last_source = normalized_source
            self._last_command_at = command_at

            driver = self._load_driver_locked()
            if not self.enabled or driver is None:
                return self._build_snapshot_locked()

            strip = self._ensure_strip_locked()
            if strip is None:
                return self._build_snapshot_locked()

            if not self._boot_started and not self._boot_completed:
                return self._build_snapshot_locked()

            self._ensure_animator_running_locked()
            self._wake_event.set()
            return self._build_snapshot_locked()

    def set_dynamic_brightness(self, brightness_percent):
        normalized_brightness = _clamp_percent(
            brightness_percent,
            100,
            minimum=self.DYNAMIC_BRIGHTNESS_MIN_PERCENT,
            maximum=100,
        )
        command_at = iso_now_utc()

        with self._lock:
            self._dynamic_brightness_percent = normalized_brightness
            self._last_command_at = command_at
            self._last_reason = "brightness-update"
            self._last_source = "settings"

            if not self._boot_started and not self._boot_completed:
                return self._build_snapshot_locked()

            driver = self._load_driver_locked()
            if not self.enabled or driver is None:
                return self._build_snapshot_locked()

            strip = self._ensure_strip_locked()
            if strip is None:
                return self._build_snapshot_locked()

            self._ensure_animator_running_locked()
            self._wake_event.set()
            return self._build_snapshot_locked()

    def set_running_load_percent(self, load_percent):
        try:
            normalized_load = max(0.0, min(100.0, float(load_percent)))
        except (ValueError, TypeError):
            normalized_load = 0.0

        target_position = self._running_load_percent_to_position(normalized_load)

        with self._lock:
            self._running_load_percent = normalized_load
            if self._desired_state != "running" and self._render_state != self.RUNNING_RENDER_STATE:
                self._running_display_position = target_position
                self._running_last_frame_monotonic = None

            driver = self._load_driver_locked()
            if not self.enabled or driver is None:
                return self._build_snapshot_locked()

            strip = self._ensure_strip_locked()
            if strip is None:
                return self._build_snapshot_locked()

            if not self._boot_started and not self._boot_completed:
                return self._build_snapshot_locked()

            if self._desired_state == "running" or self._render_state == self.RUNNING_RENDER_STATE:
                self._ensure_animator_running_locked()
                self._wake_event.set()
            return self._build_snapshot_locked()

    def start_boot_sequence(self, on_full_blue_callback=None):
        callback_to_run = None
        command_at = iso_now_utc()

        with self._lock:
            self._last_command_at = command_at
            self._last_reason = "startup"
            self._last_source = "hardware-startup"
            self._boot_started = True
            self._boot_completed = False
            self._boot_phase = "expand"
            self._boot_phase_started_monotonic = time.monotonic()
            self._boot_light_callback = on_full_blue_callback if callable(on_full_blue_callback) else None
            self._boot_light_triggered = False

            driver = self._load_driver_locked()
            if not self.enabled or driver is None:
                callback_to_run = self._boot_light_callback
                self._boot_completed = True
                self._boot_phase = "skipped"
                return_value = False
            else:
                strip = self._ensure_strip_locked()
                if strip is None:
                    callback_to_run = self._boot_light_callback
                    self._boot_completed = True
                    self._boot_phase = "failed"
                    return_value = False
                else:
                    self._ensure_animator_running_locked()
                    self._wake_event.set()
                    return_value = True

        if callback_to_run is not None:
            try:
                callback_to_run()
            except Exception as exc:  # pragma: no cover - hardware-specific startup edge case
                with self._lock:
                    self._last_error = f"Startup-Callback fuer Statusleiste fehlgeschlagen: {exc}"
        return return_value

    def start_shutdown_sequence(self, on_complete_callback=None):
        callback_to_run = None
        command_at = iso_now_utc()

        with self._lock:
            self._last_command_at = command_at
            self._last_reason = "shutdown"
            self._last_source = "system-shutdown"

            if self._shutdown_active:
                self._wake_event.set()
                return True

            self._shutdown_active = True
            self._shutdown_phase = "collapse"
            self._shutdown_phase_started_monotonic = time.monotonic()
            self._shutdown_base_frame = tuple(self._capture_current_frame_locked())
            self._shutdown_completion_callback = on_complete_callback if callable(on_complete_callback) else None
            self._shutdown_callback_triggered = False
            self._shutdown_completed_event.clear()

            driver = self._load_driver_locked()
            if not self.enabled or driver is None:
                self._shutdown_active = False
                self._shutdown_phase = "skipped"
                self._shutdown_phase_started_monotonic = None
                self._shutdown_base_frame = None
                callback_to_run = self._complete_shutdown_sequence
                return_value = False
            else:
                strip = self._ensure_strip_locked()
                if strip is None:
                    self._shutdown_active = False
                    self._shutdown_phase = "failed"
                    self._shutdown_phase_started_monotonic = None
                    self._shutdown_base_frame = None
                    callback_to_run = self._complete_shutdown_sequence
                    return_value = False
                else:
                    self._ensure_animator_running_locked()
                    self._wake_event.set()
                    return_value = True

        if callback_to_run is not None:
            callback_to_run()
        return return_value

    def wait_for_shutdown_sequence(self, timeout_sec=None):
        return self._shutdown_completed_event.wait(timeout_sec)

    def _build_snapshot_locked(self):
        driver = self._load_driver_locked()
        if not self.enabled:
            available = False
            status = "disabled"
            error = "Status-LED-Streifen ist per STATUS_INDICATOR_ENABLED deaktiviert."
        elif driver is None:
            available = False
            status = "unavailable"
            error = self._driver_error
        elif self._last_error:
            available = False
            status = "error"
            error = self._last_error
        elif self._last_success_at:
            available = True
            status = "ok"
            error = ""
        else:
            available = True
            status = "idle"
            error = ""

        return {
            "controllerId": self.CONTROLLER_ID,
            "displayName": self.DISPLAY_NAME,
            "available": available,
            "status": status,
            "error": error,
            "driver": "rpi_ws281x",
            "gpioPin": self.gpio_pin,
            "pixelCount": self.pixel_count,
            "frequencyHz": self.frequency_hz,
            "dmaChannel": self.dma_channel,
            "pwmChannel": self.pwm_channel,
            "brightness": self.brightness,
            "dynamicBrightnessPercent": self._dynamic_brightness_percent,
            "activeBrightnessPercent": self._get_active_brightness_percent_locked(),
            "stripType": self.strip_type,
            "state": self._render_state,
            "desiredState": self._desired_state,
            "reason": self._last_reason,
            "source": self._last_source,
            "color": {
                "r": self._last_color[0],
                "g": self._last_color[1],
                "b": self._last_color[2],
            },
            "animation": {
                "bootStarted": self._boot_started,
                "bootCompleted": self._boot_completed,
                "bootPhase": self._boot_phase,
                "shutdownActive": self._shutdown_active,
                "shutdownPhase": self._shutdown_phase,
                "frameRateFps": self.ANIMATION_FPS,
                "runningLoadPercent": round(self._running_load_percent, 2),
                "runningDisplayLoadPercent": round(
                    self._running_position_to_percent(self._running_display_position),
                    2,
                ),
                "runningHotspotPixel": round(self._running_display_position, 2),
            },
            "lastCommandAt": self._last_command_at,
            "lastSuccessAt": self._last_success_at,
        }

    def _load_driver_locked(self):
        if self._driver_checked:
            return self._driver

        self._driver_checked = True
        if os.name != "posix":
            self._driver_error = "WS2812B-Ansteuerung ist nur auf Linux auf dem Zielsystem verfuegbar."
            return None

        try:
            import rpi_ws281x as driver  # pragma: no cover - optional dependency on the Pi
        except Exception as exc:  # pragma: no cover - import depends on target environment
            self._driver_error = f"Python-Modul rpi_ws281x ist nicht verfuegbar: {exc}"
            return None

        if not hasattr(driver, "PixelStrip") or not hasattr(driver, "Color"):
            self._driver_error = "rpi_ws281x stellt PixelStrip oder Color nicht bereit."
            return None

        strip_constants = getattr(driver, "ws", None)
        if strip_constants is not None:
            self._strip_type_value = getattr(strip_constants, f"WS2811_STRIP_{self.strip_type}", None)

        self._driver = driver
        self._driver_error = ""
        return self._driver

    def _ensure_strip_locked(self):
        if self._strip is not None:
            return self._strip

        if self._driver is None:
            return None

        try:
            kwargs = {
                "freq_hz": self.frequency_hz,
                "dma": self.dma_channel,
                "invert": self.invert,
                "brightness": self.brightness,
                "channel": self.pwm_channel,
            }
            if self._strip_type_value is not None:
                kwargs["strip_type"] = self._strip_type_value

            self._strip = self._driver.PixelStrip(
                self.pixel_count,
                self.gpio_pin,
                **kwargs,
            )
            self._strip.begin()
            self._last_error = ""
            return self._strip
        except Exception as exc:  # pragma: no cover - hardware-specific runtime edge case
            self._strip = None
            self._last_error = f"NeoPixel-Initialisierung fehlgeschlagen: {exc}"
            return None

    def _ensure_animator_running_locked(self):
        if self._animator_thread is not None and self._animator_thread.is_alive():
            return

        self._animator_thread = threading.Thread(
            target=self._animation_loop,
            name="status-indicator-animator",
            daemon=True,
        )
        self._animator_thread.start()

    def _animation_loop(self):
        while True:
            callback_to_run = None
            wait_timeout_sec = self.STATIC_REFRESH_SEC

            with self._lock:
                if not self.enabled or self._driver is None:
                    wait_timeout_sec = 1.0
                else:
                    strip = self._ensure_strip_locked()
                    if strip is None:
                        wait_timeout_sec = 1.0
                    else:
                        frame, render_state, callback_to_run, wait_timeout_sec = self._compute_next_frame_locked()
                        if frame is not None:
                            self._write_frame_locked(frame, render_state)

            if callback_to_run is not None:
                try:
                    callback_to_run()
                except Exception as exc:  # pragma: no cover - hardware-specific callback edge case
                    with self._lock:
                        self._last_error = f"Statusleisten-Callback fehlgeschlagen: {exc}"

            self._wake_event.wait(max(0.01, float(wait_timeout_sec)))
            self._wake_event.clear()

    def _compute_next_frame_locked(self):
        now = time.monotonic()
        callback_to_run = None

        if self._shutdown_active:
            if self._shutdown_phase == "latchedOff":
                return self._render_static_frame("off"), self.SHUTDOWN_OFF_RENDER_STATE, None, self.STATIC_REFRESH_SEC

            phase_start = self._shutdown_phase_started_monotonic or now
            progress = min(1.0, max(0.0, (now - phase_start) / self.SHUTDOWN_COLLAPSE_DURATION_SEC))
            frame = self._render_shutdown_collapse_frame(progress)
            render_state = self.SHUTDOWN_RENDER_STATE
            if progress >= 1.0 and not self._shutdown_callback_triggered:
                self._shutdown_callback_triggered = True
                self._shutdown_phase = "latchedOff"
                self._shutdown_phase_started_monotonic = None
                self._shutdown_base_frame = None
                callback_to_run = self._complete_shutdown_sequence
                render_state = self.SHUTDOWN_OFF_RENDER_STATE
            return frame, render_state, callback_to_run, 1.0 / self.ANIMATION_FPS

        if self._desired_state == "eStop":
            if self._boot_started and not self._boot_completed:
                self._boot_completed = True
                self._boot_phase = "interrupted"
                self._boot_phase_started_monotonic = None
                self._boot_light_callback = None
            return self._render_estop_double_pulse_frame(now), self.ESTOP_RENDER_STATE, None, 1.0 / self.ANIMATION_FPS

        if self._boot_started and not self._boot_completed:
            if self._boot_phase == "expand":
                phase_start = self._boot_phase_started_monotonic or now
                progress = min(1.0, max(0.0, (now - phase_start) / self.BOOT_EXPAND_DURATION_SEC))
                frame = self._render_boot_expand_frame(progress)
                render_state = self.STARTUP_RENDER_STATE
                if progress >= 1.0 and not self._boot_light_triggered:
                    self._boot_light_triggered = True
                    callback_to_run = self._boot_light_callback
                    self._boot_phase = "systemCheck"
                    self._boot_phase_started_monotonic = now
                return frame, render_state, callback_to_run, 1.0 / self.ANIMATION_FPS

            if self._boot_phase == "systemCheck":
                phase_start = self._boot_phase_started_monotonic or now
                progress = min(1.0, max(0.0, (now - phase_start) / self.SYSTEM_CHECK_FADE_DURATION_SEC))
                frame = self._render_system_check_frame(progress)
                render_state = self.SYSTEM_CHECK_RENDER_STATE
                if progress >= 1.0:
                    if self._desired_state in {"idle", "warning"}:
                        self._boot_phase = "stateBlend"
                        self._boot_phase_started_monotonic = now
                    else:
                        self._boot_completed = True
                        self._boot_phase = "done"
                        self._boot_phase_started_monotonic = None
                return frame, render_state, None, 1.0 / self.ANIMATION_FPS

            if self._boot_phase == "stateBlend":
                if self._desired_state not in {"idle", "warning"}:
                    self._boot_completed = True
                    self._boot_phase = "done"
                    self._boot_phase_started_monotonic = None
                    return self._render_static_frame(self._desired_state), self._desired_state, None, self.STATIC_REFRESH_SEC

                phase_start = self._boot_phase_started_monotonic or now
                progress = min(1.0, max(0.0, (now - phase_start) / self.STATE_BLEND_DURATION_SEC))
                frame = self._render_target_transition_frame(progress, now)
                render_state = self.STATE_BLEND_RENDER_STATE
                if progress >= 1.0:
                    self._boot_completed = True
                    self._boot_phase = "done"
                    self._boot_phase_started_monotonic = None
                return frame, render_state, None, 1.0 / self.ANIMATION_FPS

        if self._desired_state == "idle":
            return self._render_idle_breathing_frame(), "idle", None, 1.0 / self.ANIMATION_FPS

        if self._desired_state == "running":
            return self._render_running_load_frame(now), self.RUNNING_RENDER_STATE, None, 1.0 / self.ANIMATION_FPS

        if self._desired_state == "warning":
            return self._render_warning_pulse_frame(now), self.WARNING_RENDER_STATE, None, 1.0 / self.ANIMATION_FPS

        return self._render_static_frame(self._desired_state), self._desired_state, None, self.STATIC_REFRESH_SEC

    def _render_static_frame(self, state_id):
        color = self.STATIC_STATE_COLORS.get(state_id, self.STATIC_STATE_COLORS["on"])
        color = self._apply_state_brightness(state_id, color)
        return [color for _ in range(self.pixel_count)]

    def _render_idle_breathing_frame(self):
        return self._render_idle_wave_frame(advance_phase=True)

    def _render_target_transition_frame(self, progress, now):
        blend = max(0.0, min(1.0, float(progress)))
        if self._desired_state == "warning":
            target_frame = self._render_warning_pulse_frame(now)
        else:
            target_frame = self._render_idle_wave_frame(advance_phase=True)
        frame = []
        for target_color in target_frame:
            frame.append(
                _blend_color(
                    (self.IDLE_WHITE_MAX, self.IDLE_WHITE_MAX, self.IDLE_WHITE_MAX),
                    target_color,
                    blend,
                )
            )
        return frame

    def _render_idle_wave_frame(self, advance_phase):
        frame = []
        amplitude = self.IDLE_WHITE_MAX - self.IDLE_WHITE_MIN
        for pixel_index in range(self.pixel_count):
            phase = self._idle_phase - (pixel_index * self.IDLE_PIXEL_PHASE_OFFSET)
            wave = (math.sin(phase) + 1.0) * 0.5
            white = int(round(self.IDLE_WHITE_MIN + (amplitude * wave)))
            frame.append(self._apply_state_brightness("idle", (white, white, white)))
        if advance_phase:
            self._idle_phase = (self._idle_phase + self.IDLE_PHASE_STEP_PER_FRAME) % math.tau
        return frame

    def _render_warning_pulse_frame(self, now):
        base_warning = self.STATIC_STATE_COLORS["warning"]
        if self.WARNING_PULSE_PERIOD_SEC <= 0:
            pulse_progress = 1.0
        else:
            cycle_progress = (max(0.0, float(now)) % self.WARNING_PULSE_PERIOD_SEC) / self.WARNING_PULSE_PERIOD_SEC
            pulse_progress = 0.5 - (0.5 * math.cos(math.tau * cycle_progress))

        factor = self.WARNING_PULSE_MIN_FACTOR + (
            (self.WARNING_PULSE_MAX_FACTOR - self.WARNING_PULSE_MIN_FACTOR) * pulse_progress
        )
        color = self._apply_state_brightness("warning", _scale_color(base_warning, factor))
        return [color for _ in range(self.pixel_count)]

    def _render_running_load_frame(self, now):
        target_position = self._running_load_percent_to_position(self._running_load_percent)
        if self._running_last_frame_monotonic is None:
            self._running_display_position = target_position
        else:
            delta_sec = max(0.0, min(0.25, float(now) - float(self._running_last_frame_monotonic)))
            if delta_sec > 0.0 and self.RUNNING_SMOOTHING_TIME_SEC > 0.0:
                blend = 1.0 - math.exp(-delta_sec / self.RUNNING_SMOOTHING_TIME_SEC)
                self._running_display_position += (target_position - self._running_display_position) * blend
            else:
                self._running_display_position = target_position

        self._running_last_frame_monotonic = float(now)
        hotspot_position = max(0.0, min(float(self.pixel_count - 1), self._running_display_position))
        frame = []
        for pixel_index in range(self.pixel_count):
            distance = hotspot_position - float(pixel_index)
            if distance < -0.5:
                highlight_strength = 0.0
            elif distance < 0.0:
                highlight_strength = 1.0 - (abs(distance) / 0.5)
            elif self.RUNNING_TAIL_PIXELS > 0.0 and distance <= self.RUNNING_TAIL_PIXELS:
                tail_progress = distance / self.RUNNING_TAIL_PIXELS
                highlight_strength = math.cos(tail_progress * (math.pi * 0.5)) ** 2
            else:
                highlight_strength = 0.0

            color = _blend_color(
                self.RUNNING_BASE_GREEN,
                self.RUNNING_HOTSPOT_GREEN,
                highlight_strength,
            )
            frame.append(self._apply_state_brightness("running", color))
        return frame

    def _render_estop_double_pulse_frame(self, now):
        cycle_time = 0.0
        if self.ESTOP_PULSE_PERIOD_SEC > 0:
            cycle_time = max(0.0, float(now)) % self.ESTOP_PULSE_PERIOD_SEC

        first_pulse = self._render_estop_pulse_strength(cycle_time, self.ESTOP_FIRST_PULSE_CENTER_SEC)
        second_pulse = self._render_estop_pulse_strength(cycle_time, self.ESTOP_SECOND_PULSE_CENTER_SEC)
        pulse_strength = max(0.0, min(1.0, first_pulse + second_pulse))
        red_value = _lerp_channel(self.ESTOP_RED_BASE, self.ESTOP_RED_PEAK, pulse_strength)
        return [(red_value, 0, 0) for _ in range(self.pixel_count)]

    def _render_estop_pulse_strength(self, cycle_time, center_time):
        half_width = self.ESTOP_PULSE_WIDTH_SEC * 0.5
        if half_width <= 0.0:
            return 0.0

        distance = abs(float(cycle_time) - float(center_time))
        if distance >= half_width:
            return 0.0

        normalized = distance / half_width
        return 0.5 * (1.0 + math.cos(math.pi * normalized))

    def _render_shutdown_collapse_frame(self, progress):
        base_frame = self._shutdown_base_frame or tuple(self._capture_current_frame_locked())
        frame = [(0, 0, 0) for _ in range(self.pixel_count)]
        scaled_groups = max(0.0, 1.0 - min(1.0, max(0.0, progress))) * len(self._center_groups)
        full_group_count = min(len(self._center_groups), int(scaled_groups))
        partial_progress = min(1.0, max(0.0, scaled_groups - full_group_count))

        for group_index in range(full_group_count):
            for pixel_index in self._center_groups[group_index]:
                frame[pixel_index] = base_frame[pixel_index]

        if full_group_count < len(self._center_groups) and partial_progress > 0.0:
            for pixel_index in self._center_groups[full_group_count]:
                frame[pixel_index] = _scale_color(base_frame[pixel_index], partial_progress)

        return frame

    def _render_boot_expand_frame(self, progress):
        frame = [(0, 0, 0) for _ in range(self.pixel_count)]
        scaled = max(0.0, min(1.0, progress)) * len(self._center_groups)
        full_group_count = min(len(self._center_groups), int(scaled))
        partial_progress = min(1.0, max(0.0, scaled - full_group_count))

        for group_index in range(full_group_count):
            for pixel_index in self._center_groups[group_index]:
                frame[pixel_index] = self.STARTUP_BLUE

        if full_group_count < len(self._center_groups):
            partial_blue = _lerp_channel(0, self.STARTUP_BLUE[2], partial_progress)
            partial_green = _lerp_channel(0, self.STARTUP_BLUE[1], partial_progress)
            for pixel_index in self._center_groups[full_group_count]:
                frame[pixel_index] = (0, partial_green, partial_blue)

        return frame

    def _render_system_check_frame(self, progress):
        target_white = self.IDLE_WHITE_MAX
        fade_color = (
            _lerp_channel(self.STARTUP_BLUE[0], target_white, progress),
            _lerp_channel(self.STARTUP_BLUE[1], target_white, progress),
            _lerp_channel(self.STARTUP_BLUE[2], target_white, progress),
        )
        return [fade_color for _ in range(self.pixel_count)]

    def _write_frame_locked(self, frame, render_state):
        if self._strip is None or self._driver is None:
            return

        immutable_frame = tuple(frame)
        if self._last_pixels == immutable_frame and self._render_state == render_state and not self._last_error:
            return

        try:
            for pixel_index, color in enumerate(immutable_frame):
                self._strip.setPixelColor(pixel_index, self._driver.Color(*color))
            self._strip.show()
        except Exception as exc:  # pragma: no cover - hardware-specific runtime edge case
            self._last_error = f"NeoPixel-Update fehlgeschlagen: {exc}"
            return

        red_sum = 0
        green_sum = 0
        blue_sum = 0
        for red_value, green_value, blue_value in immutable_frame:
            red_sum += red_value
            green_sum += green_value
            blue_sum += blue_value

        pixel_count = max(1, len(immutable_frame))
        self._last_pixels = immutable_frame
        self._render_state = str(render_state or "off")
        self._last_color = (
            int(round(red_sum / pixel_count)),
            int(round(green_sum / pixel_count)),
            int(round(blue_sum / pixel_count)),
        )
        self._last_success_at = iso_now_utc()
        self._last_error = ""

    def _capture_current_frame_locked(self):
        if self._last_pixels is not None:
            return [tuple(color) for color in self._last_pixels]

        if self._desired_state == "idle":
            return self._render_idle_wave_frame(advance_phase=False)

        if self._desired_state == "running":
            return self._render_running_load_frame(time.monotonic())

        if self._desired_state == "warning":
            return self._render_warning_pulse_frame(time.monotonic())

        return self._render_static_frame(self._desired_state)

    def _complete_shutdown_sequence(self):
        callback = None
        with self._lock:
            callback = self._shutdown_completion_callback
            self._shutdown_completion_callback = None

        try:
            if callback is not None:
                callback()
        except Exception as exc:  # pragma: no cover - hardware-specific shutdown edge case
            with self._lock:
                self._last_error = f"Shutdown-Callback fuer Statusleiste fehlgeschlagen: {exc}"
        finally:
            self._shutdown_completed_event.set()

    def _get_active_brightness_percent_locked(self):
        if self._desired_state in self.DIMMABLE_STATES:
            return self._dynamic_brightness_percent
        return 100

    def _apply_state_brightness(self, state_id, color):
        if state_id not in self.DIMMABLE_STATES:
            return color
        return _scale_color(color, self._dynamic_brightness_percent / 100.0)

    def _running_load_percent_to_position(self, load_percent):
        if self.pixel_count <= 1:
            return 0.0
        normalized_load = max(0.0, min(100.0, float(load_percent)))
        return (normalized_load / 100.0) * float(self.pixel_count - 1)

    def _running_position_to_percent(self, position):
        if self.pixel_count <= 1:
            return 0.0
        normalized_position = max(0.0, min(float(self.pixel_count - 1), float(position)))
        return (normalized_position / float(self.pixel_count - 1)) * 100.0

    def _build_center_groups(self):
        groups = []
        left_index = (self.pixel_count - 1) // 2
        right_index = self.pixel_count // 2

        while left_index >= 0 or right_index < self.pixel_count:
            group = []
            if left_index == right_index:
                if 0 <= left_index < self.pixel_count:
                    group.append(left_index)
            else:
                if 0 <= left_index < self.pixel_count:
                    group.append(left_index)
                if 0 <= right_index < self.pixel_count:
                    group.append(right_index)
            if group:
                groups.append(tuple(group))
            left_index -= 1
            right_index += 1
        return tuple(groups)
