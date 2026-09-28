"""Gamepad/controller input handler for SpiRob GUI.

Supports Xbox, PS5, and generic controllers via pygame/SDL2.
Runs in a separate thread and emits Qt signals for input events.
"""

import copy
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

# Optional dependency - pygame provides controller support
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    pygame = None
    PYGAME_AVAILABLE = False

logger = logging.getLogger(__name__)

# Polling interval constant
POLL_INTERVAL_SEC = 0.02  # 50Hz
POLL_ERROR_BACKOFF_SEC = 0.1


@dataclass
class ControllerState:
    """Current state of the controller."""
    connected: bool = False
    name: str = ""

    # Analog sticks (-1.0 to 1.0)
    left_x: float = 0.0   # V tendon
    left_y: float = 0.0   # U tendon (inverted, up = positive)
    right_x: float = 0.0  # Unused
    right_y: float = 0.0  # W tendon (inverted, up = positive)

    # Triggers (0.0 to 1.0)
    left_trigger: float = 0.0
    right_trigger: float = 0.0

    # Buttons (pressed state)
    btn_a: bool = False      # Toggle torque
    btn_b: bool = False      # Reset E-stop
    btn_x: bool = False      # Unused
    btn_y: bool = False      # E-stop
    btn_lb: bool = False     # Slow mode
    btn_rb: bool = False     # Fast mode
    btn_back: bool = False   # Zero all
    btn_start: bool = False  # Toggle torque


class ControllerHandler(QObject):
    """Handles gamepad input and emits signals for GUI control.

    Uses pygame for cross-platform controller support.
    """

    # Signals
    state_changed = pyqtSignal(ControllerState)
    connected = pyqtSignal(str)  # Controller name
    disconnected = pyqtSignal()

    # Button press events (for one-shot actions)
    estop_pressed = pyqtSignal()
    torque_toggle_pressed = pyqtSignal()
    reset_estop_pressed = pyqtSignal()
    zero_all_pressed = pyqtSignal()

    # Movement signals (tendon, delta_deg)
    movement = pyqtSignal(str, float)

    # Deadzone for analog sticks
    DEADZONE = 0.15

    # Speed settings (degrees per second)
    SPEED_SLOW = 30.0
    SPEED_NORMAL = 90.0
    SPEED_FAST = 180.0
    SPEED_MAX = 360.0

    def __init__(self):
        super().__init__()

        # Thread safety lock for shared state
        self._state_lock = threading.Lock()

        self._state = ControllerState()
        self._joystick = None
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._pygame_initialized = False

        # Axis mapping (Xbox default, remapped on DualSense connect)
        self._axis_lx = 0
        self._axis_ly = 1
        self._axis_rx = 2
        self._axis_ry = 3
        self._axis_lt = 4
        self._axis_rt = 5

        # Button state tracking for edge detection
        self._prev_btn_y = False
        self._prev_btn_a = False
        self._prev_btn_b = False
        self._prev_btn_back = False
        self._prev_btn_start = False

        # Movement update timer
        self._last_update = time.time()

    @property
    def state(self) -> ControllerState:
        """Get current controller state (thread-safe copy)."""
        with self._state_lock:
            return copy.copy(self._state)

    @property
    def is_connected(self) -> bool:
        """Check if a controller is connected (thread-safe)."""
        with self._state_lock:
            return self._state.connected

    def start(self) -> bool:
        """Start the controller handler."""
        if self._running:
            return True

        if not PYGAME_AVAILABLE:
            logger.warning("pygame not installed - controller support disabled")
            return False

        try:
            pygame.init()
            pygame.joystick.init()
            self._pygame_initialized = True
        except pygame.error as e:
            logger.error(f"Failed to initialize pygame: {e}")
            return False

        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name='controller_poll',
            daemon=True
        )
        self._poll_thread.start()
        return True

    def stop(self) -> None:
        """Stop the controller handler."""
        self._running = False

        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)

        if self._pygame_initialized and PYGAME_AVAILABLE:
            try:
                pygame.joystick.quit()
                pygame.quit()
            except pygame.error as e:
                logger.debug(f"Error during pygame cleanup: {e}")

        with self._state_lock:
            self._state.connected = False
        self.disconnected.emit()

    def _poll_loop(self) -> None:
        """Main polling loop for controller input."""
        while self._running:
            try:
                # Process pygame events
                pygame.event.pump()

                # Check for controller connection changes
                joystick_count = pygame.joystick.get_count()

                if joystick_count == 0 and self._joystick is not None:
                    # Controller disconnected
                    self._joystick = None
                    with self._state_lock:
                        self._state.connected = False
                        self._state.name = ""
                    self.disconnected.emit()

                elif joystick_count > 0 and self._joystick is None:
                    # Controller connected
                    self._joystick = pygame.joystick.Joystick(0)
                    self._joystick.init()
                    controller_name = self._joystick.get_name()

                    # DualSense has different axis layout than Xbox
                    if "dualsense" in controller_name.lower():
                        self._axis_ry = 5   # Right Y is axis 5
                        self._axis_lt = 3   # L2 trigger is axis 3
                        self._axis_rt = 4   # R2 trigger is axis 4
                        logger.info(f"DualSense detected, using PS5 axis mapping")
                    else:
                        self._axis_ry = 3
                        self._axis_lt = 4
                        self._axis_rt = 5

                    with self._state_lock:
                        self._state.connected = True
                        self._state.name = controller_name
                    self.connected.emit(controller_name)

                # Read controller state
                if self._joystick is not None:
                    self._read_controller_state()
                    self._process_buttons()
                    self._process_movement()
                    # Emit a copy of state for thread safety
                    with self._state_lock:
                        state_copy = copy.copy(self._state)
                    self.state_changed.emit(state_copy)

                time.sleep(POLL_INTERVAL_SEC)

            except pygame.error as e:
                logger.warning(f"Controller poll error: {e}")
                time.sleep(POLL_ERROR_BACKOFF_SEC)

    def _apply_deadzone(self, value: float) -> float:
        """Apply deadzone to analog input."""
        if abs(value) < self.DEADZONE:
            return 0.0
        # Scale value to remove deadzone gap
        sign = 1 if value > 0 else -1
        return sign * (abs(value) - self.DEADZONE) / (1.0 - self.DEADZONE)

    def _read_controller_state(self) -> None:
        """Read current state from the controller."""
        if self._joystick is None:
            return

        # Get number of axes and buttons
        num_axes = self._joystick.get_numaxes()
        num_buttons = self._joystick.get_numbuttons()

        with self._state_lock:
            # Read analog sticks (using mapped axis indices)
            if num_axes >= 2:
                self._state.left_x = self._apply_deadzone(self._joystick.get_axis(self._axis_lx))
                self._state.left_y = self._apply_deadzone(-self._joystick.get_axis(self._axis_ly))  # Invert Y

            if num_axes > self._axis_ry:
                self._state.right_x = self._apply_deadzone(self._joystick.get_axis(self._axis_rx))
                self._state.right_y = self._apply_deadzone(-self._joystick.get_axis(self._axis_ry))  # Invert Y

            # Read triggers (axes vary by controller)
            if num_axes > max(self._axis_lt, self._axis_rt):
                # Triggers go from -1 (released) to 1 (pressed)
                self._state.left_trigger = (self._joystick.get_axis(self._axis_lt) + 1) / 2
                self._state.right_trigger = (self._joystick.get_axis(self._axis_rt) + 1) / 2

            # Read buttons (standard Xbox/PS mapping)
            if num_buttons >= 1:
                self._state.btn_a = self._joystick.get_button(0)  # A/Cross
            if num_buttons >= 2:
                self._state.btn_b = self._joystick.get_button(1)  # B/Circle
            if num_buttons >= 3:
                self._state.btn_x = self._joystick.get_button(2)  # X/Square
            if num_buttons >= 4:
                self._state.btn_y = self._joystick.get_button(3)  # Y/Triangle
            if num_buttons >= 5:
                self._state.btn_lb = self._joystick.get_button(4)  # LB/L1
            if num_buttons >= 6:
                self._state.btn_rb = self._joystick.get_button(5)  # RB/R1
            if num_buttons >= 7:
                self._state.btn_back = self._joystick.get_button(6)  # Back/Share
            if num_buttons >= 8:
                self._state.btn_start = self._joystick.get_button(7)  # Start/Options

    def _process_buttons(self) -> None:
        """Process button presses and emit one-shot signals."""
        # Copy button state under lock for thread safety
        with self._state_lock:
            btn_y = self._state.btn_y
            btn_a = self._state.btn_a
            btn_b = self._state.btn_b
            btn_back = self._state.btn_back
            btn_start = self._state.btn_start

        # Y button -> E-stop (rising edge)
        if btn_y and not self._prev_btn_y:
            self.estop_pressed.emit()
        self._prev_btn_y = btn_y

        # A button -> Toggle torque (rising edge)
        if btn_a and not self._prev_btn_a:
            self.torque_toggle_pressed.emit()
        self._prev_btn_a = btn_a

        # B button -> Reset E-stop (rising edge)
        if btn_b and not self._prev_btn_b:
            self.reset_estop_pressed.emit()
        self._prev_btn_b = btn_b

        # Back button -> Zero all (rising edge)
        if btn_back and not self._prev_btn_back:
            self.zero_all_pressed.emit()
        self._prev_btn_back = btn_back

        # Start button -> Toggle torque (rising edge, alternative)
        if btn_start and not self._prev_btn_start:
            self.torque_toggle_pressed.emit()
        self._prev_btn_start = btn_start

    def _process_movement(self) -> None:
        """Process analog stick input and emit movement signals."""
        now = time.time()
        dt = now - self._last_update
        self._last_update = now

        # Copy state under lock for thread safety
        with self._state_lock:
            btn_lb = self._state.btn_lb
            btn_rb = self._state.btn_rb
            left_y = self._state.left_y
            left_x = self._state.left_x
            right_y = self._state.right_y

        # Determine speed based on button modifiers
        if btn_lb and btn_rb:
            speed = self.SPEED_MAX
        elif btn_rb:
            speed = self.SPEED_FAST
        elif btn_lb:
            speed = self.SPEED_SLOW
        else:
            speed = self.SPEED_NORMAL

        # Calculate movement deltas (degrees)
        # Left stick Y -> U tendon
        if abs(left_y) > 0:
            delta_u = left_y * speed * dt
            self.movement.emit('u', delta_u)

        # Left stick X -> V tendon
        if abs(left_x) > 0:
            delta_v = left_x * speed * dt
            self.movement.emit('v', delta_v)

        # Right stick Y -> W tendon
        if abs(right_y) > 0:
            delta_w = right_y * speed * dt
            self.movement.emit('w', delta_w)

    def get_speed_multiplier(self) -> float:
        """Get current speed multiplier based on button state (thread-safe)."""
        with self._state_lock:
            btn_lb = self._state.btn_lb
            btn_rb = self._state.btn_rb

        if btn_lb and btn_rb:
            return self.SPEED_MAX / self.SPEED_NORMAL
        elif btn_rb:
            return self.SPEED_FAST / self.SPEED_NORMAL
        elif btn_lb:
            return self.SPEED_SLOW / self.SPEED_NORMAL
        return 1.0

    def get_speed_mode_name(self) -> str:
        """Get name of current speed mode (thread-safe)."""
        with self._state_lock:
            btn_lb = self._state.btn_lb
            btn_rb = self._state.btn_rb

        if btn_lb and btn_rb:
            return "MAX"
        elif btn_rb:
            return "FAST"
        elif btn_lb:
            return "SLOW"
        return "NORMAL"
