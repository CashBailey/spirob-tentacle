"""Safety monitoring for soft-limits, watchdogs, and emergency stop.

Implements the safety requirements from the High-Level Design Specification:
- Per-tendon soft-limits in spool rotation
- Emergency stop on fault detection
- Heartbeat monitoring for lost communication
"""

import threading
import time
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Dict, List

from spirob.protocol.constants import ErrorFlag, get_error_flag_names

logger = logging.getLogger(__name__)


@dataclass
class SoftLimits:
    """Soft limits for a single tendon/servo.

    All angles are in degrees relative to the zero position.
    """
    min_angle_deg: float = -2292.0
    max_angle_deg: float = 2292.0
    max_speed_dps: float = 360.0
    max_torque_percent: float = 80.0


class SafetyMonitor:
    """Monitors safety conditions and triggers emergency stop when needed.

    Responsibilities:
    - Enforce soft limits on commanded positions
    - Monitor heartbeat from each servo
    - Check servo error flags
    - Trigger emergency stop callback on critical faults
    """

    # Default heartbeat timeout (ms) - must be generous enough to tolerate
    # occasional USB hiccups and serial retries (3 servos × 1 read each at 50Hz)
    DEFAULT_HEARTBEAT_TIMEOUT_MS = 2000

    # Error flags that trigger immediate e-stop
    CRITICAL_ERROR_FLAGS = (
        ErrorFlag.OVERHEAT |
        ErrorFlag.OVERLOAD |
        ErrorFlag.VOLTAGE
    )

    # Temperature thresholds (Celsius)
    TEMP_WARN_THRESHOLD = 60
    TEMP_CRITICAL_THRESHOLD = 70

    # Voltage thresholds (Volts)
    VOLTAGE_MIN = 6.0
    VOLTAGE_MAX = 14.0

    def __init__(self, on_emergency_stop: Callable[[str], None] = None):
        """Initialize safety monitor.

        Args:
            on_emergency_stop: Callback when emergency stop is triggered.
                              Receives a reason string.
        """
        self._estop_callback = on_emergency_stop
        self._limits: Dict[str, SoftLimits] = {}
        self._heartbeat_timeout_ms = self.DEFAULT_HEARTBEAT_TIMEOUT_MS
        self._last_heartbeat: Dict[str, float] = {}

        # Thread-safe estop flag with lock for atomic check-and-set
        self._estop_lock = threading.Lock()
        self._estop_triggered = False
        self._enabled = True

    @property
    def is_enabled(self) -> bool:
        """Check if safety monitoring is enabled."""
        return self._enabled

    @property
    def estop_triggered(self) -> bool:
        """Check if emergency stop has been triggered (thread-safe)."""
        with self._estop_lock:
            return self._estop_triggered

    def enable(self) -> None:
        """Enable safety monitoring."""
        self._enabled = True
        logger.info("Safety monitoring enabled")

    def disable(self) -> None:
        """Disable safety monitoring (use with caution!)."""
        self._enabled = False
        logger.warning("Safety monitoring DISABLED")

    def reset_estop(self) -> None:
        """Reset emergency stop state (after fault is cleared)."""
        with self._estop_lock:
            self._estop_triggered = False
        logger.info("Emergency stop reset")

    def set_heartbeat_timeout(self, timeout_ms: int) -> None:
        """Set heartbeat timeout in milliseconds."""
        self._heartbeat_timeout_ms = timeout_ms

    # === Soft Limits ===

    def set_limits(self, tendon: str, limits: SoftLimits) -> None:
        """Set soft limits for a tendon.

        Args:
            tendon: Tendon identifier (e.g., 'u', 'v', 'w')
            limits: SoftLimits instance
        """
        self._limits[tendon] = limits
        logger.debug(f"Set limits for {tendon}: {limits}")

    def get_limits(self, tendon: str) -> Optional[SoftLimits]:
        """Get soft limits for a tendon."""
        return self._limits.get(tendon)

    def check_position_limit(self, tendon: str, target_angle: float) -> float:
        """Check and clamp target position to soft limits.

        Args:
            tendon: Tendon identifier
            target_angle: Desired target angle in degrees

        Returns:
            Clamped angle (may be different from input if limit hit)
        """
        limits = self._limits.get(tendon)
        if limits is None:
            return target_angle

        clamped = max(limits.min_angle_deg,
                      min(limits.max_angle_deg, target_angle))

        if clamped != target_angle:
            logger.warning(
                f"Position limit: {tendon} target {target_angle:.1f}deg "
                f"clamped to {clamped:.1f}deg"
            )

        return clamped

    def check_speed_limit(self, tendon: str, speed_dps: float) -> float:
        """Check and clamp speed to limit.

        Args:
            tendon: Tendon identifier
            speed_dps: Desired speed in degrees/second

        Returns:
            Clamped speed
        """
        limits = self._limits.get(tendon)
        if limits is None:
            return speed_dps

        clamped = min(abs(speed_dps), limits.max_speed_dps)
        return clamped if speed_dps >= 0 else -clamped

    def check_torque_limit(self, tendon: str, torque_percent: float) -> float:
        """Check and clamp torque to limit.

        Args:
            tendon: Tendon identifier
            torque_percent: Desired torque as percentage

        Returns:
            Clamped torque percentage
        """
        limits = self._limits.get(tendon)
        if limits is None:
            return torque_percent

        return min(torque_percent, limits.max_torque_percent)

    # === Heartbeat Monitoring ===

    def update_heartbeat(self, tendon: str) -> None:
        """Update heartbeat timestamp for a tendon.

        Call this when successful communication with the servo occurs.

        Args:
            tendon: Tendon identifier
        """
        self._last_heartbeat[tendon] = time.time()

    def check_heartbeat(self, tendon: str) -> bool:
        """Check if servo heartbeat is within timeout.

        Args:
            tendon: Tendon identifier

        Returns:
            True if heartbeat is OK, False if timed out
        """
        if tendon not in self._last_heartbeat:
            return True  # No heartbeat recorded yet, assume OK

        elapsed_ms = (time.time() - self._last_heartbeat[tendon]) * 1000
        return elapsed_ms < self._heartbeat_timeout_ms

    def check_all_heartbeats(self) -> List[str]:
        """Check heartbeats for all monitored tendons.

        Returns:
            List of tendon names with timed-out heartbeats
        """
        timed_out = []
        for tendon in self._last_heartbeat:
            if not self.check_heartbeat(tendon):
                timed_out.append(tendon)
        return timed_out

    # === Error Flag Checking ===

    def check_servo_faults(self, tendon: str, error_flags: int) -> List[str]:
        """Check servo error flags and return list of active faults.

        Args:
            tendon: Tendon identifier
            error_flags: Error flags from servo status

        Returns:
            List of fault names
        """
        return get_error_flag_names(error_flags)

    def is_critical_fault(self, error_flags: int) -> bool:
        """Check if error flags contain any critical faults.

        Args:
            error_flags: Error flags from servo status

        Returns:
            True if critical fault detected
        """
        return bool(error_flags & self.CRITICAL_ERROR_FLAGS)

    # === Emergency Stop ===

    def trigger_emergency_stop(self, reason: str) -> None:
        """Trigger emergency stop.

        Calls the registered callback and sets the estop flag.
        Uses atomic check-and-set to prevent race conditions.

        Args:
            reason: Description of why e-stop was triggered
        """
        if not self._enabled:
            logger.warning(f"E-stop condition but safety disabled: {reason}")
            return

        # Atomic check-and-set to prevent duplicate triggers
        with self._estop_lock:
            if self._estop_triggered:
                # Already triggered, don't repeat callback
                return
            self._estop_triggered = True

        logger.error(f"EMERGENCY STOP: {reason}")

        if self._estop_callback:
            try:
                self._estop_callback(reason)
            except Exception as e:
                # E-stop callback failure is critical - log with full traceback
                logger.exception(
                    f"CRITICAL: E-stop callback failed during emergency stop: {e}"
                )

    def check_and_handle_faults(self, tendon: str, error_flags: int) -> bool:
        """Check error flags and trigger e-stop if critical.

        Args:
            tendon: Tendon identifier
            error_flags: Error flags from servo

        Returns:
            True if no critical faults, False if e-stop triggered
        """
        if error_flags == 0:
            return True

        faults = self.check_servo_faults(tendon, error_flags)

        if self.is_critical_fault(error_flags):
            self.trigger_emergency_stop(
                f"Critical fault on {tendon}: {', '.join(faults)}"
            )
            return False

        # Non-critical faults - log warning
        if faults:
            logger.warning(f"Servo {tendon} faults: {', '.join(faults)}")

        return True

    # === Thermal/Voltage Guardrails ===

    def check_temperature(self, tendon: str, temp_celsius: int,
                          warn_threshold: Optional[int] = None,
                          critical_threshold: Optional[int] = None) -> bool:
        """Check temperature and warn/estop if high.

        Args:
            tendon: Tendon identifier
            temp_celsius: Current temperature
            warn_threshold: Temperature to log warning (default: TEMP_WARN_THRESHOLD)
            critical_threshold: Temperature to trigger e-stop (default: TEMP_CRITICAL_THRESHOLD)

        Returns:
            True if temperature OK, False if e-stop triggered
        """
        if warn_threshold is None:
            warn_threshold = self.TEMP_WARN_THRESHOLD
        if critical_threshold is None:
            critical_threshold = self.TEMP_CRITICAL_THRESHOLD

        if temp_celsius >= critical_threshold:
            self.trigger_emergency_stop(
                f"Critical temperature on {tendon}: {temp_celsius}C"
            )
            return False

        if temp_celsius >= warn_threshold:
            logger.warning(f"High temperature on {tendon}: {temp_celsius}C")

        return True

    def check_voltage(self, tendon: str, voltage: float,
                      min_voltage: Optional[float] = None,
                      max_voltage: Optional[float] = None) -> bool:
        """Check voltage and warn/estop if out of range.

        Args:
            tendon: Tendon identifier
            voltage: Current voltage in volts
            min_voltage: Minimum acceptable voltage (default: VOLTAGE_MIN)
            max_voltage: Maximum acceptable voltage (default: VOLTAGE_MAX)

        Returns:
            True if voltage OK, False if e-stop triggered
        """
        if min_voltage is None:
            min_voltage = self.VOLTAGE_MIN
        if max_voltage is None:
            max_voltage = self.VOLTAGE_MAX

        if voltage < min_voltage:
            self.trigger_emergency_stop(
                f"Low voltage on {tendon}: {voltage:.1f}V (min: {min_voltage}V)"
            )
            return False

        if voltage > max_voltage:
            self.trigger_emergency_stop(
                f"High voltage on {tendon}: {voltage:.1f}V (max: {max_voltage}V)"
            )
            return False

        return True
