"""Servo manager for coordinating U, V, W tendon servos.

The ServoManager is the central coordination point for all three servos.
It handles:
- Initialization and discovery
- Background telemetry polling
- Coordinated motion commands
- Safety integration
- Load compensation
"""

import time
import logging
import threading
from typing import Dict, Optional, Callable, List

from spirob.bus import BusAdapter, Servo, ServoState
from spirob.control.safety import SafetyMonitor, SoftLimits
from spirob.control.load_compensation import LoadCompensator, CompensationParams
from spirob.control.spool_geometry import SpoolGeometry, SpoolConfig
from spirob.utils.conversions import degrees_to_steps, speed_dps_to_raw

logger = logging.getLogger(__name__)


class ServoManager:
    """Coordinates U, V, W servo control with telemetry polling.

    Runs a background thread for continuous state updates while providing
    a thread-safe interface for commands and state queries.
    """

    # Default telemetry rate
    DEFAULT_TELEMETRY_HZ = 50.0

    def __init__(self, bus_adapter: BusAdapter,
                 id_map: Dict[str, int],
                 telemetry_rate_hz: float = DEFAULT_TELEMETRY_HZ,
                 safety_monitor: Optional[SafetyMonitor] = None,
                 load_compensator: Optional[LoadCompensator] = None):
        """Initialize servo manager.

        Args:
            bus_adapter: BusAdapter for communication
            id_map: Mapping of tendon names to servo IDs (e.g., {'u': 1, 'v': 2, 'w': 3})
            telemetry_rate_hz: Rate for background state polling
            safety_monitor: Optional SafetyMonitor instance (injectable for testing)
            load_compensator: Optional LoadCompensator instance (injectable for testing)
        """
        self._adapter = bus_adapter
        self._id_map = id_map
        self._telemetry_rate = telemetry_rate_hz

        # Create servo instances
        self._servos: Dict[str, Servo] = {}
        for name, servo_id in id_map.items():
            self._servos[name] = Servo(servo_id, bus_adapter, label=name)

        # Threading for telemetry
        self._telemetry_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._state_lock = threading.RLock()

        # Safety and compensation (injectable for testing)
        self._safety = safety_monitor or SafetyMonitor(on_emergency_stop=self._on_emergency_stop)
        self._compensator = load_compensator or LoadCompensator()

        # Callbacks for state changes
        self._on_state_update: Optional[Callable[[Dict[str, ServoState]], None]] = None
        self._on_fault: Optional[Callable[[str, List[str]], None]] = None

        # Consecutive fault counters — require multiple bad readings before e-stop
        # (protects against single corrupted serial reads)
        self._temp_fault_count: Dict[str, int] = {n: 0 for n in id_map}
        self._voltage_fault_count: Dict[str, int] = {n: 0 for n in id_map}

        # Cached torque values — only write when changed (avoids redundant serial traffic)
        self._last_torque: Dict[str, int] = {}

        # Status
        self._initialized = False
        self._telemetry_running = False

    @property
    def is_initialized(self) -> bool:
        """Check if manager has been initialized."""
        return self._initialized

    @property
    def is_telemetry_running(self) -> bool:
        """Check if telemetry thread is running."""
        return self._telemetry_running

    @property
    def safety(self) -> SafetyMonitor:
        """Get safety monitor instance."""
        return self._safety

    @property
    def compensator(self) -> LoadCompensator:
        """Get load compensator instance."""
        return self._compensator

    def get_servo(self, tendon: str) -> Optional[Servo]:
        """Get servo instance by tendon name.

        Args:
            tendon: Tendon name ('u', 'v', 'w')

        Returns:
            Servo instance or None if not found
        """
        return self._servos.get(tendon)

    def get_all_servos(self) -> Dict[str, Servo]:
        """Get all servo instances."""
        return dict(self._servos)

    # === Callbacks ===

    def set_state_update_callback(
            self, callback: Callable[[Dict[str, ServoState]], None]) -> None:
        """Set callback for state updates.

        Called after each telemetry cycle with all servo states.
        """
        self._on_state_update = callback

    def set_fault_callback(
            self, callback: Callable[[str, List[str]], None]) -> None:
        """Set callback for fault detection.

        Called when a servo reports error flags.
        Args passed: (tendon_name, list_of_fault_names)
        """
        self._on_fault = callback

    # === Initialization ===

    def initialize(self) -> bool:
        """Initialize servos: ping, verify IDs, read initial state.

        Returns:
            True if all servos respond successfully
        """
        logger.info("Initializing servo manager...")

        if not self._adapter.is_connected:
            logger.error("Bus adapter not connected")
            return False

        all_ok = True
        for name, servo in self._servos.items():
            logger.info(f"Pinging servo '{name}' (ID={servo.id})...")

            if not servo.ping():
                logger.error(f"Servo '{name}' (ID={servo.id}) not responding")
                all_ok = False
                continue

            # Configure multi-turn (MODE=3, angle limits=0)
            if not self._adapter.configure_multi_turn(servo.id):
                logger.warning(f"Failed to configure multi-turn for '{name}'")

            # Read initial state
            if servo.update_state():
                state = servo.state
                logger.info(
                    f"Servo '{name}': pos={state.position_deg:.1f}deg, "
                    f"V={state.voltage:.1f}V, T={state.temperature}C"
                )
            else:
                logger.warning(f"Could not read initial state for '{name}'")

            # Initialize heartbeat tracking
            self._safety.update_heartbeat(name)

        if all_ok:
            self._initialized = True
            logger.info("Servo manager initialized successfully")
        else:
            logger.warning("Servo manager initialized with errors")

        return all_ok

    def scan_bus(self) -> List[int]:
        """Scan bus for all connected servos.

        Returns:
            List of found servo IDs
        """
        return self._adapter.scan()

    # === Telemetry Thread ===

    def start_telemetry(self) -> None:
        """Start background telemetry polling thread."""
        if self._telemetry_running:
            logger.warning("Telemetry already running")
            return

        self._stop_event.clear()
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_loop,
            name="spirob_telemetry",
            daemon=True
        )
        self._telemetry_thread.start()
        self._telemetry_running = True
        logger.info(f"Telemetry started at {self._telemetry_rate} Hz")

    def stop_telemetry(self) -> None:
        """Stop telemetry thread."""
        if not self._telemetry_running:
            return

        logger.info("Stopping telemetry...")
        self._stop_event.set()

        if self._telemetry_thread:
            self._telemetry_thread.join(timeout=2.0)
            self._telemetry_thread = None

        self._telemetry_running = False
        logger.info("Telemetry stopped")

    # Consecutive readings required before temperature/voltage triggers e-stop.
    # At 50Hz, 5 readings = 100ms — fast enough for real faults, immune to
    # single corrupted serial reads.
    FAULT_CONFIRM_COUNT = 5

    def _process_servo_telemetry(self, name: str, servo) -> ServoState:
        """Process telemetry for a single servo.

        Updates heartbeat, checks for faults, and validates temperature/voltage.
        Uses consecutive-reading confirmation to avoid false e-stops from
        corrupted serial data.

        Must be called with _state_lock held.

        Args:
            name: Tendon name
            servo: Servo instance

        Returns:
            Current ServoState (updated if communication succeeded)
        """
        if not servo.update_state():
            return servo.state

        self._safety.update_heartbeat(name)

        # Check for faults
        if servo.state.has_error:
            faults = servo.state.get_error_names()
            if self._on_fault:
                self._on_fault(name, faults)
            self._safety.check_and_handle_faults(name, servo.state.error_flags)

        # Check temperature with consecutive-reading confirmation
        # (bypasses safety.check_temperature() which triggers instant e-stop)
        temp = servo.state.temperature
        if temp >= self._safety.TEMP_CRITICAL_THRESHOLD:
            self._temp_fault_count[name] = self._temp_fault_count.get(name, 0) + 1
            if self._temp_fault_count[name] >= self.FAULT_CONFIRM_COUNT:
                self._safety.trigger_emergency_stop(
                    f"Confirmed high temperature on {name}: {temp}C "
                    f"({self._temp_fault_count[name]} consecutive readings)"
                )
            elif self._temp_fault_count[name] == 1:
                logger.warning(
                    f"Possible high temp on {name}: {temp}C "
                    f"(confirming, {self.FAULT_CONFIRM_COUNT - 1} more needed)"
                )
        elif temp >= self._safety.TEMP_WARN_THRESHOLD:
            self._temp_fault_count[name] = 0
            logger.warning(f"Warm temperature on {name}: {temp}C")
        else:
            self._temp_fault_count[name] = 0

        # Check voltage with consecutive-reading confirmation
        voltage = servo.state.voltage
        voltage_bad = (voltage < self._safety.VOLTAGE_MIN or
                       voltage > self._safety.VOLTAGE_MAX)
        if voltage_bad:
            self._voltage_fault_count[name] = self._voltage_fault_count.get(name, 0) + 1
            if self._voltage_fault_count[name] >= self.FAULT_CONFIRM_COUNT:
                self._safety.trigger_emergency_stop(
                    f"Confirmed voltage fault on {name}: {voltage:.1f}V "
                    f"({self._voltage_fault_count[name]} consecutive readings)"
                )
            elif self._voltage_fault_count[name] == 1:
                logger.warning(
                    f"Possible voltage fault on {name}: {voltage:.1f}V "
                    f"(confirming, {self.FAULT_CONFIRM_COUNT - 1} more needed)"
                )
        else:
            self._voltage_fault_count[name] = 0

        return servo.state

    def _telemetry_loop(self) -> None:
        """Background loop that polls all servos at configured rate.

        Lock is held per-servo (not across all reads) so movement
        commands from the GUI thread can interleave between servo polls.
        """
        period = 1.0 / self._telemetry_rate

        while not self._stop_event.is_set():
            loop_start = time.time()

            # Poll each servo with a short per-servo lock hold
            states = {}
            for name, servo in self._servos.items():
                with self._state_lock:
                    states[name] = self._process_servo_telemetry(name, servo)

            # Check heartbeats (lightweight, no serial I/O)
            with self._state_lock:
                timed_out = self._safety.check_all_heartbeats()
                for name in timed_out:
                    logger.warning(f"Heartbeat timeout for '{name}'")
                    self._safety.trigger_emergency_stop(
                        f"Lost communication with '{name}'"
                    )

            # Call state update callback
            if self._on_state_update and states:
                try:
                    self._on_state_update(states)
                except Exception as e:
                    logger.error(f"State update callback error: {e}")

            # Sleep for remainder of period
            elapsed = time.time() - loop_start
            sleep_time = max(0, period - elapsed)
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)

    # === State Access ===

    def get_all_states(self) -> Dict[str, ServoState]:
        """Get current state of all servos (thread-safe).

        Returns:
            Dictionary mapping tendon names to ServoState
        """
        with self._state_lock:
            return {name: servo.state for name, servo in self._servos.items()}

    def get_state(self, tendon: str) -> Optional[ServoState]:
        """Get state for a single tendon.

        Args:
            tendon: Tendon name

        Returns:
            ServoState or None if tendon not found
        """
        servo = self._servos.get(tendon)
        if servo:
            with self._state_lock:
                return servo.state
        return None

    # === Motion Commands ===

    def set_target_angle(self, tendon: str, angle_deg: float,
                         speed_dps: float = 0,
                         use_compensation: bool = True) -> bool:
        """Set target angle for a tendon with safety checks.

        Args:
            tendon: Tendon name
            angle_deg: Target angle in degrees
            speed_dps: Speed in degrees/second (0 = max)
            use_compensation: Apply load compensation if True

        Returns:
            True if command sent successfully
        """
        if self._safety.estop_triggered:
            logger.warning("E-stop active, ignoring command")
            return False

        servo = self._servos.get(tendon)
        if not servo:
            logger.error(f"Unknown tendon: {tendon}")
            return False

        # Apply soft limits
        angle_deg = self._safety.check_position_limit(tendon, angle_deg)

        # Apply load compensation
        if use_compensation:
            current_deg = servo.get_position_deg()
            comp_speed, comp_torque = self._compensator.get_compensated_params(
                tendon, current_deg, angle_deg
            )
            if speed_dps == 0:
                speed_dps = comp_speed
            # Only write torque limit when it changes (saves a serial transaction)
            torque_raw = max(0, min(1000, int(comp_torque * 10)))
            if self._last_torque.get(tendon) != torque_raw:
                servo.set_torque_limit(comp_torque)
                self._last_torque[tendon] = torque_raw

        # Apply speed limit
        speed_dps = self._safety.check_speed_limit(tendon, speed_dps)

        # Convert to raw values
        speed_raw = speed_dps_to_raw(speed_dps) if speed_dps > 0 else 0

        # Send command
        return servo.set_target_deg(angle_deg, speed=speed_raw)

    def set_all_targets(self, targets: Dict[str, float],
                        speed_dps: float = 0) -> bool:
        """Set target angles for multiple tendons.

        Args:
            targets: Dictionary of tendon name to target angle
            speed_dps: Speed for all moves

        Returns:
            True if all commands sent successfully
        """
        if self._safety.estop_triggered:
            logger.warning("E-stop active, ignoring commands")
            return False

        all_ok = True
        for tendon, angle in targets.items():
            if not self.set_target_angle(tendon, angle, speed_dps):
                all_ok = False

        return all_ok

    # === Torque Control ===

    def set_torque_enable(self, tendon: str, enable: bool) -> bool:
        """Enable/disable torque for a single tendon.

        Args:
            tendon: Tendon name
            enable: True to enable, False to disable

        Returns:
            True if command succeeded
        """
        servo = self._servos.get(tendon)
        if not servo:
            return False

        if enable:
            return servo.enable_torque()
        else:
            return servo.disable_torque()

    def set_all_torque_enable(self, enable: bool) -> bool:
        """Enable/disable torque on all servos.

        Args:
            enable: True to enable, False to disable

        Returns:
            True if all commands succeeded
        """
        all_ok = True
        for name, servo in self._servos.items():
            if enable:
                if not servo.enable_torque():
                    all_ok = False
            else:
                if not servo.disable_torque():
                    all_ok = False

        action = "enabled" if enable else "disabled"
        logger.info(f"Torque {action} for all servos")
        return all_ok

    # === Zeroing ===

    def zero_tendon(self, tendon: str) -> bool:
        """Set current position as zero for a tendon.

        Args:
            tendon: Tendon name

        Returns:
            True if zeroing succeeded
        """
        servo = self._servos.get(tendon)
        if not servo:
            return False

        # Update state first
        servo.update_state()
        servo.set_zero_here()
        logger.info(f"Zeroed tendon '{tendon}' at position {servo.state.position}")
        return True

    def zero_all(self) -> bool:
        """Set current positions as zero for all tendons."""
        all_ok = True
        for name in self._servos:
            if not self.zero_tendon(name):
                all_ok = False
        return all_ok

    # === Safety ===

    def _on_emergency_stop(self, reason: str) -> None:
        """Internal emergency stop handler.

        Best-effort attempt to disable torque on all servos.
        Continues even if some servos fail, to maximize safety.
        """
        logger.critical(f"EMERGENCY STOP: {reason}")
        failed_servos = []
        # Disable all torque immediately - best effort
        for name, servo in self._servos.items():
            try:
                servo.disable_torque()
            except Exception as e:
                failed_servos.append(name)
                logger.error(f"Failed to disable torque on {name}: {e}")

        if failed_servos:
            logger.critical(
                f"E-STOP INCOMPLETE: Could not disable torque on: {failed_servos}"
            )

    def emergency_stop(self) -> None:
        """Trigger emergency stop manually."""
        self._safety.trigger_emergency_stop("Manual E-stop")

    def reset_estop(self) -> None:
        """Reset emergency stop (after clearing fault)."""
        self._safety.reset_estop()

    # === Configuration ===

    def configure_limits(self, tendon: str, limits: SoftLimits) -> None:
        """Configure soft limits for a tendon.

        Args:
            tendon: Tendon name
            limits: SoftLimits instance
        """
        self._safety.set_limits(tendon, limits)

    def configure_spool(self, tendon: str, config: SpoolConfig) -> None:
        """Configure spool geometry for a tendon.

        Args:
            tendon: Tendon name
            config: SpoolConfig instance
        """
        geometry = SpoolGeometry(config)
        self._compensator.set_geometry(tendon, geometry)

    def configure_compensation(self, params: CompensationParams) -> None:
        """Configure load compensation parameters.

        Args:
            params: CompensationParams instance
        """
        self._compensator = LoadCompensator(params)

    # === Cleanup ===

    def shutdown(self) -> None:
        """Shutdown manager: stop telemetry, disable torque."""
        logger.info("Shutting down servo manager...")
        self.stop_telemetry()
        self.set_all_torque_enable(False)
        self._initialized = False
        logger.info("Servo manager shutdown complete")
