"""Single servo abstraction with state tracking."""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

from spirob.protocol.constants import (
    POSITION_MIN, POSITION_MAX, POSITION_CENTER, ErrorFlag, get_error_flag_names
)
from spirob.protocol.registers import Register
from spirob.utils.conversions import (
    steps_to_degrees, degrees_to_steps, steps_to_radians,
    voltage_raw_to_volts, current_raw_to_ma, speed_raw_to_dps
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from spirob.bus.bus_adapter import BusAdapter


class ServoMode(Enum):
    """Servo operating modes."""
    POSITION = 0      # Position control (servo mode)
    VELOCITY = 1      # Velocity/speed control
    PWM = 2           # PWM control
    STEP = 3          # Step mode


@dataclass
class ServoState:
    """Current state of a servo."""

    # Position (raw steps, signed multi-turn)
    position: int = POSITION_CENTER

    # Speed (steps/sec, signed)
    speed: int = 0

    # Load (signed, represents torque direction)
    load: int = 0

    # Voltage (raw value in 0.1V units)
    voltage_raw: int = 0

    # Temperature (Celsius)
    temperature: int = 0

    # Current draw (raw value in 6.5mA units)
    current_raw: int = 0

    # Error/status flags
    error_flags: int = 0

    # Moving indicator
    is_moving: bool = False

    # Timestamp of last update
    timestamp: float = field(default_factory=time.time)

    # Connection status
    is_connected: bool = True

    # Consecutive communication failures
    comm_failures: int = 0

    @property
    def position_deg(self) -> float:
        """Position in degrees (signed, multi-turn)."""
        return steps_to_degrees(self.position)

    @property
    def position_rad(self) -> float:
        """Position in radians."""
        return steps_to_radians(self.position)

    @property
    def speed_dps(self) -> float:
        """Speed in degrees per second."""
        return speed_raw_to_dps(abs(self.speed))

    @property
    def voltage(self) -> float:
        """Voltage in volts."""
        return voltage_raw_to_volts(self.voltage_raw)

    @property
    def current_ma(self) -> float:
        """Current in milliamps."""
        return current_raw_to_ma(self.current_raw)

    @property
    def has_error(self) -> bool:
        """Check if any error flags are set."""
        return self.error_flags != 0

    @property
    def is_overheating(self) -> bool:
        """Check if overheat flag is set."""
        return bool(self.error_flags & ErrorFlag.OVERHEAT)

    @property
    def is_overloaded(self) -> bool:
        """Check if overload flag is set."""
        return bool(self.error_flags & ErrorFlag.OVERLOAD)

    @property
    def has_voltage_error(self) -> bool:
        """Check if voltage error flag is set."""
        return bool(self.error_flags & ErrorFlag.VOLTAGE)

    def get_error_names(self) -> list[str]:
        """Get list of active error flag names."""
        return get_error_flag_names(self.error_flags)


class Servo:
    """Single servo abstraction with state tracking and control.

    Provides a high-level interface to a servo with automatic state
    tracking and offset management for zeroing.
    """

    # Maximum consecutive failures before marking disconnected
    MAX_FAILURES = 5

    # Multi-turn unwrapping constants (4096 steps per revolution)
    STEPS_PER_REV = 4096
    HALF_REV = 2048  # Standard wrap detection threshold
    QUARTER_REV = 1024  # Speed-validated wrap threshold

    # Sanity limits for telemetry - reject obviously corrupted reads
    # Max temperature jump per read cycle (real thermal change is ~0.1C/cycle at 50Hz)
    MAX_TEMP_JUMP_C = 30
    # Absolute max plausible temperature for ST3215
    MAX_PLAUSIBLE_TEMP_C = 120
    # Max plausible voltage (raw 0.1V units) - 25V would be way beyond 12V system
    MAX_PLAUSIBLE_VOLTAGE_RAW = 250

    def __init__(self, servo_id: int, adapter: 'BusAdapter',
                 label: str = None):
        """Initialize servo instance.

        Args:
            servo_id: The servo's bus ID (1-253)
            adapter: BusAdapter instance for communication
            label: Optional human-readable label (e.g., 'u', 'v', 'w')
        """
        self._id = servo_id
        self._adapter = adapter
        self._label = label or str(servo_id)
        self._state = ServoState()
        self._offset: int = 0  # Zero offset in steps
        self._torque_enabled: bool = False
        self._turn_count: int = 0  # Multi-turn revolution counter
        self._prev_raw_pos: Optional[int] = None  # Previous raw position for wrap detection

    @property
    def id(self) -> int:
        """Get servo bus ID."""
        return self._id

    @property
    def label(self) -> str:
        """Get servo label."""
        return self._label

    @property
    def state(self) -> ServoState:
        """Get current servo state (read-only copy)."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if servo is responsive."""
        return self._state.is_connected

    @property
    def torque_enabled(self) -> bool:
        """Check if torque is enabled."""
        return self._torque_enabled

    def update_state(self) -> bool:
        """Fetch and update state from servo.

        Includes sanity filtering to reject corrupted serial data.
        Temperature and voltage values that jump implausibly between
        reads are replaced with the previous known-good value.

        Returns:
            True if state was successfully updated
        """
        telemetry = self._adapter.read_telemetry(self._id)

        if telemetry is None:
            self._state.comm_failures += 1
            if self._state.comm_failures >= self.MAX_FAILURES:
                self._state.is_connected = False
            return False

        # Reset failure counter on successful read
        self._state.comm_failures = 0
        self._state.is_connected = True

        # Unwrap position for multi-turn tracking
        # PRESENT_POSITION only reports single-turn (0-4095) even in multi-turn mode.
        # Detect wraps at 0↔4095 boundary and maintain a turn counter.
        #
        # Two-tier detection:
        # 1. Standard: jumps > HALF_REV are obvious wraps
        # 2. Speed-validated: jumps > QUARTER_REV where delta direction disagrees
        #    with speed register — catches wraps missed during long poll gaps
        #    (e.g. WSL2 USB latency spikes causing 700ms gaps at high speed)
        raw_pos = telemetry['position']
        speed = telemetry['speed']
        if self._prev_raw_pos is not None:
            delta = raw_pos - self._prev_raw_pos
            if delta > self.HALF_REV:
                self._turn_count -= 1
            elif delta < -self.HALF_REV:
                self._turn_count += 1
            elif abs(delta) > self.QUARTER_REV and abs(speed) > 50:
                # Large delta but under HALF_REV — check speed for validation
                if delta < 0 and speed > 0:
                    # Position dropped but servo moving positive → wrapped 4095→0
                    self._turn_count += 1
                elif delta > 0 and speed < 0:
                    # Position jumped but servo moving negative → wrapped 0→4095
                    self._turn_count -= 1
        self._prev_raw_pos = raw_pos
        self._state.position = raw_pos + (self._turn_count * self.STEPS_PER_REV)

        self._state.speed = speed
        self._state.load = telemetry['load']

        # Sanity-check temperature before accepting
        new_temp = telemetry['temperature']
        prev_temp = self._state.temperature
        if new_temp > self.MAX_PLAUSIBLE_TEMP_C:
            logger.warning(
                f"Servo {self._label}: rejected implausible temp {new_temp}C "
                f"(max {self.MAX_PLAUSIBLE_TEMP_C}C), keeping {prev_temp}C"
            )
        elif prev_temp > 0 and abs(new_temp - prev_temp) > self.MAX_TEMP_JUMP_C:
            logger.warning(
                f"Servo {self._label}: rejected temp spike {prev_temp}C->{new_temp}C "
                f"(>{self.MAX_TEMP_JUMP_C}C jump), keeping {prev_temp}C"
            )
        else:
            self._state.temperature = new_temp

        # Sanity-check voltage before accepting
        new_voltage = telemetry['voltage']
        if new_voltage > self.MAX_PLAUSIBLE_VOLTAGE_RAW:
            logger.warning(
                f"Servo {self._label}: rejected implausible voltage raw={new_voltage} "
                f"(>{self.MAX_PLAUSIBLE_VOLTAGE_RAW}), keeping {self._state.voltage_raw}"
            )
        else:
            self._state.voltage_raw = new_voltage

        self._state.timestamp = time.time()

        # Infer moving from speed (avoids extra serial transaction)
        self._state.is_moving = self._state.speed != 0

        return True

    def ping(self) -> bool:
        """Ping servo to check if present."""
        result = self._adapter.ping(self._id)
        self._state.is_connected = result
        return result

    # === Position Control ===

    def get_position_steps(self) -> int:
        """Get current position in raw steps (signed, multi-turn)."""
        return self._state.position

    def get_position_deg(self, with_offset: bool = True) -> float:
        """Get current position in degrees.

        Args:
            with_offset: If True, apply zero offset

        Returns:
            Position in degrees
        """
        pos = self._state.position
        if with_offset:
            pos = pos - self._offset
        return steps_to_degrees(pos)

    def get_position_rad(self, with_offset: bool = True) -> float:
        """Get current position in radians.

        Args:
            with_offset: If True, apply zero offset
        """
        pos = self._state.position
        if with_offset:
            pos = pos - self._offset
        return steps_to_radians(pos)

    def set_target_steps(self, position: int, time_ms: int = 0,
                         speed: int = 0) -> bool:
        """Set target position in raw steps.

        Args:
            position: Target position (signed, multi-turn)
            time_ms: Move duration in ms (0 = use speed)
            speed: Move speed (0 = max, ignored if time_ms > 0)

        Returns:
            True if command succeeded
        """
        return self._adapter.write_position(self._id, position, time_ms, speed)

    def set_target_deg(self, degrees: float, time_ms: int = 0,
                       speed: int = 0, with_offset: bool = True) -> bool:
        """Set target position in degrees.

        Args:
            degrees: Target position in degrees
            time_ms: Move duration in ms
            speed: Move speed in steps/s
            with_offset: If True, apply zero offset

        Returns:
            True if command succeeded
        """
        steps = degrees_to_steps(degrees)
        if with_offset:
            steps = steps + self._offset
        # Clamp to valid range
        steps = max(POSITION_MIN, min(POSITION_MAX, steps))
        return self._adapter.write_position(self._id, steps, time_ms, speed)

    # === Zero/Offset ===

    def set_zero_here(self) -> None:
        """Set current position as the zero reference.

        Resets the turn counter and stores an offset so get_position_deg()
        returns 0 at this position. Stored locally, not written to servo EEPROM.
        """
        self._turn_count = 0
        self._prev_raw_pos = None
        self._offset = self._state.position

    def get_offset(self) -> int:
        """Get current zero offset in steps."""
        return self._offset

    def set_offset(self, offset: int) -> None:
        """Set zero offset in steps."""
        self._offset = offset

    def clear_offset(self) -> None:
        """Clear zero offset (reset to no offset)."""
        self._offset = 0

    # === Torque Control ===

    def enable_torque(self) -> bool:
        """Enable torque output."""
        result = self._adapter.set_torque_enable(self._id, True)
        if result:
            self._torque_enabled = True
        return result

    def disable_torque(self) -> bool:
        """Disable torque output."""
        result = self._adapter.set_torque_enable(self._id, False)
        if result:
            self._torque_enabled = False
        return result

    def set_torque_limit(self, limit_percent: float) -> bool:
        """Set torque limit as percentage (0-100).

        Args:
            limit_percent: Torque limit as percentage

        Returns:
            True if command succeeded
        """
        limit = max(0, min(1000, int(limit_percent * 10)))
        return self._adapter.set_torque_limit(self._id, limit)

    # === Mode Control ===

    def set_mode(self, mode: ServoMode) -> bool:
        """Set operating mode.

        Args:
            mode: Desired operating mode

        Returns:
            True if command succeeded
        """
        return self._adapter.set_mode(self._id, mode.value)

    # === Status ===

    def get_status_string(self) -> str:
        """Get human-readable status string."""
        s = self._state
        status = f"Servo {self._label} (ID={self._id}): "

        if not s.is_connected:
            return status + "DISCONNECTED"

        status += f"pos={s.position_deg:.1f}deg "
        status += f"spd={s.speed_dps:.1f}dps "
        status += f"V={s.voltage:.1f}V "
        status += f"T={s.temperature}C "

        if s.is_moving:
            status += "[MOVING] "
        if self._torque_enabled:
            status += "[TORQUE] "
        if s.has_error:
            status += f"[ERR: {','.join(s.get_error_names())}]"

        return status

    def __repr__(self) -> str:
        return f"Servo(id={self._id}, label='{self._label}')"
