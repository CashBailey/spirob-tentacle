"""Load compensation for varying tendon wrap conditions.

Implements adaptive speed/torque adjustment based on:
- Current effective radius (wrap layers)
- Progress toward target (stuck detection)
- Thermal and power constraints
"""

import time
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from spirob.control.spool_geometry import SpoolGeometry

logger = logging.getLogger(__name__)


@dataclass
class CompensationParams:
    """Parameters for load compensation algorithm.

    Attributes:
        base_speed_dps: Default speed in degrees/second
        base_torque_percent: Default torque limit as percentage
        stuck_threshold_deg: Position error threshold for stuck detection
        stuck_timeout_sec: Time without progress before declaring stuck
        adaptation_step_percent: How much to increase torque/speed when stuck
        max_torque_percent: Maximum torque limit (cap)
        max_speed_dps: Maximum speed (cap)
    """
    base_speed_dps: float = 180.0
    base_torque_percent: float = 50.0
    stuck_threshold_deg: float = 1.0
    stuck_timeout_sec: float = 0.5
    adaptation_step_percent: float = 10.0
    max_torque_percent: float = 90.0
    max_speed_dps: float = 360.0


@dataclass
class TendonState:
    """Internal state for tracking a tendon's compensation."""
    last_position_deg: float = 0.0
    last_target_deg: float = 0.0
    last_progress_time: float = 0.0
    current_torque_boost: float = 0.0
    current_speed_boost: float = 0.0
    is_stuck: bool = False


class LoadCompensator:
    """Adaptive load compensation based on wrap layers and progress.

    The compensator adjusts commanded speed and torque based on:
    1. Effective radius - higher radius needs more torque
    2. Progress monitoring - if servo is stuck, increase torque/speed
    3. Pre-tension - brief pulse before major movements

    This aligns with the LC-1 through LC-5 requirements in the design spec.
    """

    # Compensation thresholds
    DEFAULT_CORE_RADIUS_MM = 10.0
    BOOST_REDUCTION_STEP = 5
    SIGNIFICANT_REEL_IN_THRESHOLD_DEG = -30.0
    ASSERTIVE_MODE_SPEED_MULT = 1.5
    ASSERTIVE_MODE_TORQUE_MULT = 1.25

    def __init__(self, params: CompensationParams = None) -> None:
        """Initialize load compensator.

        Args:
            params: Compensation parameters (uses defaults if not provided)
        """
        self._params = params or CompensationParams()
        self._geometries: Dict[str, SpoolGeometry] = {}
        self._states: Dict[str, TendonState] = {}
        self._assertive_mode = False

    @property
    def params(self) -> CompensationParams:
        """Get compensation parameters."""
        return self._params

    @property
    def assertive_mode(self) -> bool:
        """Check if assertive mode is enabled."""
        return self._assertive_mode

    def set_assertive_mode(self, enabled: bool) -> None:
        """Enable/disable assertive mode.

        Assertive mode uses higher speed and torque limits for
        moves that fight heavy wrap.

        Args:
            enabled: True to enable assertive mode
        """
        self._assertive_mode = enabled
        if enabled:
            logger.info("Assertive mode ENABLED")
        else:
            logger.info("Assertive mode disabled")

    def set_geometry(self, tendon: str, geometry: SpoolGeometry) -> None:
        """Set spool geometry for a tendon.

        Args:
            tendon: Tendon identifier (e.g., 'u', 'v', 'w')
            geometry: SpoolGeometry instance for this tendon
        """
        self._geometries[tendon] = geometry
        if tendon not in self._states:
            self._states[tendon] = TendonState()

    def _get_state(self, tendon: str) -> TendonState:
        """Get or create state for a tendon."""
        if tendon not in self._states:
            self._states[tendon] = TendonState()
        return self._states[tendon]

    # === LC-1: Effective Radius Estimation ===

    def get_effective_radius(self, tendon: str, angle_deg: float) -> float:
        """Get effective spool radius at current angle.

        Args:
            tendon: Tendon identifier
            angle_deg: Current spool angle

        Returns:
            Effective radius in mm, or core radius if no geometry set
        """
        if tendon not in self._geometries:
            return self.DEFAULT_CORE_RADIUS_MM

        return self._geometries[tendon].calculate_effective_radius_at_angle(angle_deg)

    def get_torque_scale(self, tendon: str, angle_deg: float) -> float:
        """Get torque scaling factor based on effective radius.

        Higher effective radius requires more torque for same tendon tension.

        Args:
            tendon: Tendon identifier
            angle_deg: Current spool angle

        Returns:
            Torque scaling factor (1.0 at core radius)
        """
        if tendon not in self._geometries:
            return 1.0

        return self._geometries[tendon].get_torque_scaling_at_angle(angle_deg)

    # === LC-2: Progress-based Adaptation ===

    def update_position(self, tendon: str, current_deg: float,
                        target_deg: float) -> None:
        """Update position tracking for stuck detection.

        Call this periodically with current and target positions.

        Args:
            tendon: Tendon identifier
            current_deg: Current position in degrees
            target_deg: Target position in degrees
        """
        state = self._get_state(tendon)
        now = time.time()

        # Calculate error
        error = abs(target_deg - current_deg)

        # Check if making progress
        position_change = abs(current_deg - state.last_position_deg)

        if position_change > self._params.stuck_threshold_deg:
            # Making progress, reset stuck detection
            state.last_progress_time = now
            state.is_stuck = False
            # Gradually reduce boost when moving
            state.current_torque_boost = max(0, state.current_torque_boost - self.BOOST_REDUCTION_STEP)
            state.current_speed_boost = max(0, state.current_speed_boost - self.BOOST_REDUCTION_STEP)
        elif error > self._params.stuck_threshold_deg:
            # Not at target and not making progress
            time_stuck = now - state.last_progress_time
            if time_stuck > self._params.stuck_timeout_sec:
                state.is_stuck = True

        state.last_position_deg = current_deg
        state.last_target_deg = target_deg

    def detect_stuck(self, tendon: str) -> bool:
        """Check if a tendon is currently stuck.

        Args:
            tendon: Tendon identifier

        Returns:
            True if servo appears stuck
        """
        return self._get_state(tendon).is_stuck

    def adapt_for_stuck(self, tendon: str) -> Tuple[float, float]:
        """Get adapted speed/torque when stuck.

        Increases speed and torque by adaptation step up to max limits.

        Args:
            tendon: Tendon identifier

        Returns:
            Tuple of (adapted_speed_dps, adapted_torque_percent)
        """
        state = self._get_state(tendon)
        p = self._params

        if state.is_stuck:
            # Increase boost
            state.current_torque_boost = min(
                state.current_torque_boost + p.adaptation_step_percent,
                p.max_torque_percent - p.base_torque_percent
            )
            state.current_speed_boost = min(
                state.current_speed_boost + p.adaptation_step_percent,
                p.max_speed_dps - p.base_speed_dps
            )
            logger.debug(
                f"Adapting {tendon} for stuck: "
                f"torque_boost={state.current_torque_boost:.0f}%, "
                f"speed_boost={state.current_speed_boost:.0f}"
            )

        speed = p.base_speed_dps + state.current_speed_boost
        torque = p.base_torque_percent + state.current_torque_boost

        return speed, torque

    # === LC-3: Pre-tension (Placeholder) ===

    def should_pretension(self, tendon: str, target_deg: float) -> bool:
        """Check if pre-tension should be applied before move.

        Pre-tension helps remove slack before reel-in moves.

        Args:
            tendon: Tendon identifier
            target_deg: Target position

        Returns:
            True if pre-tension recommended
        """
        state = self._get_state(tendon)
        # Suggest pre-tension for significant reel-in moves
        move_amount = target_deg - state.last_position_deg
        return move_amount < self.SIGNIFICANT_REEL_IN_THRESHOLD_DEG

    # === Main Interface ===

    def get_compensated_params(self, tendon: str, current_deg: float,
                               target_deg: float) -> Tuple[float, float]:
        """Get speed and torque with all compensation applied.

        This is the main entry point for getting compensated parameters.

        Args:
            tendon: Tendon identifier
            current_deg: Current position in degrees
            target_deg: Target position in degrees

        Returns:
            Tuple of (speed_dps, torque_percent) with compensation applied
        """
        # Update position tracking
        self.update_position(tendon, current_deg, target_deg)

        p = self._params
        state = self._get_state(tendon)

        # Start with base values
        speed = p.base_speed_dps
        torque = p.base_torque_percent

        # Apply assertive mode boost
        if self._assertive_mode:
            speed = min(speed * self.ASSERTIVE_MODE_SPEED_MULT, p.max_speed_dps)
            torque = min(torque * self.ASSERTIVE_MODE_TORQUE_MULT, p.max_torque_percent)

        # Apply effective radius compensation (LC-1)
        torque_scale = self.get_torque_scale(tendon, current_deg)
        torque = min(torque * torque_scale, p.max_torque_percent)

        # Apply stuck adaptation (LC-2)
        if state.is_stuck:
            adapted_speed, adapted_torque = self.adapt_for_stuck(tendon)
            speed = max(speed, adapted_speed)
            torque = max(torque, adapted_torque)

        # Apply current boost
        speed = min(speed + state.current_speed_boost, p.max_speed_dps)
        torque = min(torque + state.current_torque_boost, p.max_torque_percent)

        return speed, torque

    def reset_tendon(self, tendon: str) -> None:
        """Reset compensation state for a tendon.

        Args:
            tendon: Tendon identifier
        """
        self._states[tendon] = TendonState()
        logger.debug(f"Reset compensation state for {tendon}")

    def reset_all(self) -> None:
        """Reset compensation state for all tendons."""
        self._states.clear()
        logger.debug("Reset all compensation states")
