"""Spool geometry calculations for tendon wrap compensation.

The SpiRob tentacle uses spools to wind/unwind tendons. As layers of tendon
accumulate on the spool, the effective radius changes, affecting the
force/displacement relationship.
"""

import math
from dataclasses import dataclass


@dataclass
class SpoolConfig:
    """Configuration for a tendon spool.

    Attributes:
        core_radius_mm: Radius of the empty spool core
        tendon_diameter_mm: Diameter of the tendon
        wrap_width_mm: Width of the spool (how many tendons can fit side by side)
        usable_layers: Maximum number of tendon layers that can be wound
    """
    core_radius_mm: float = 5.0   # 10mm diameter spool
    tendon_diameter_mm: float = 1.0
    wrap_width_mm: float = 15.0
    usable_layers: int = 5


class SpoolGeometry:
    """Calculate effective spool radius and tendon displacement.

    The effective radius increases as tendon layers accumulate:
        r_eff = r_core + layer_count * tendon_diameter

    This affects the torque required to pull the tendon and the
    displacement per spool rotation.
    """

    def __init__(self, config: SpoolConfig):
        """Initialize with spool configuration.

        Args:
            config: SpoolConfig with physical dimensions
        """
        self._config = config
        self._wraps_per_layer = self._calculate_wraps_per_layer()

    @property
    def config(self) -> SpoolConfig:
        """Get the spool configuration."""
        return self._config

    @property
    def core_radius_mm(self) -> float:
        """Get core radius in mm."""
        return self._config.core_radius_mm

    @property
    def max_radius_mm(self) -> float:
        """Get maximum radius (fully wound) in mm."""
        return self._config.core_radius_mm + (
            self._config.usable_layers * self._config.tendon_diameter_mm
        )

    def _calculate_wraps_per_layer(self) -> float:
        """Calculate how many wraps fit in one layer."""
        if self._config.tendon_diameter_mm <= 0:
            return 1.0
        return self._config.wrap_width_mm / self._config.tendon_diameter_mm

    def wraps_to_layer(self, wrap_count: float) -> int:
        """Convert total wrap count to current layer number.

        Layer 0 is the first layer on the bare core.

        Args:
            wrap_count: Total number of wraps on the spool

        Returns:
            Current layer number (0-based)
        """
        if wrap_count <= 0:
            return 0
        layer = int(wrap_count / self._wraps_per_layer)
        return min(layer, self._config.usable_layers - 1)

    def angle_to_wraps(self, angle_deg: float) -> float:
        """Convert spool angle to number of wraps.

        Args:
            angle_deg: Spool rotation angle in degrees

        Returns:
            Number of wraps (can be fractional)
        """
        return angle_deg / 360.0

    def wraps_to_angle(self, wraps: float) -> float:
        """Convert wraps to spool angle.

        Args:
            wraps: Number of wraps

        Returns:
            Spool angle in degrees
        """
        return wraps * 360.0

    def calculate_effective_radius(self, wrap_count: float) -> float:
        """Calculate effective spool radius at given wrap count.

        Args:
            wrap_count: Total number of wraps on spool

        Returns:
            Effective radius in mm
        """
        layer = self.wraps_to_layer(wrap_count)
        # Effective radius is core + accumulated layers + half of current wrap
        r_eff = self._config.core_radius_mm + (
            layer * self._config.tendon_diameter_mm
        )
        # Add half tendon diameter for the current wrap position
        r_eff += self._config.tendon_diameter_mm / 2.0
        return r_eff

    def calculate_effective_radius_at_angle(self, angle_deg: float) -> float:
        """Calculate effective radius at given spool angle.

        Args:
            angle_deg: Spool angle in degrees from zero

        Returns:
            Effective radius in mm
        """
        wraps = self.angle_to_wraps(abs(angle_deg))
        return self.calculate_effective_radius(wraps)

    def angle_to_length_mm(self, angle_deg: float) -> float:
        """Calculate tendon displacement for a given angle change.

        This accounts for the varying effective radius across the motion.
        For small angles, uses the average radius approximation.

        Args:
            angle_deg: Spool rotation in degrees

        Returns:
            Tendon length change in mm (positive = tendon pulled in)
        """
        # For accurate calculation, integrate over the motion
        # For simplicity, use average radius
        start_wraps = 0
        end_wraps = self.angle_to_wraps(abs(angle_deg))

        r_start = self.calculate_effective_radius(start_wraps)
        r_end = self.calculate_effective_radius(end_wraps)
        r_avg = (r_start + r_end) / 2.0

        # Arc length = angle (rad) * radius
        angle_rad = math.radians(abs(angle_deg))
        length = angle_rad * r_avg

        return length if angle_deg >= 0 else -length

    def length_to_angle_approx(self, length_mm: float) -> float:
        """Approximate angle needed for a given length change.

        Uses average radius for approximation.

        Args:
            length_mm: Desired tendon displacement in mm

        Returns:
            Approximate spool angle in degrees
        """
        # Start with core radius as approximation
        r_avg = self._config.core_radius_mm + self._config.tendon_diameter_mm
        angle_rad = abs(length_mm) / r_avg
        angle_deg = math.degrees(angle_rad)

        return angle_deg if length_mm >= 0 else -angle_deg

    def get_torque_scaling_factor(self, wrap_count: float) -> float:
        """Get torque scaling factor relative to core radius.

        As effective radius increases, more torque is needed for the same
        tendon tension. This returns the ratio r_eff / r_core.

        Args:
            wrap_count: Current wrap count

        Returns:
            Torque scaling factor (1.0 at core, increases with wraps)
        """
        r_eff = self.calculate_effective_radius(wrap_count)
        return r_eff / self._config.core_radius_mm

    def get_torque_scaling_at_angle(self, angle_deg: float) -> float:
        """Get torque scaling factor at given angle.

        Args:
            angle_deg: Current spool angle

        Returns:
            Torque scaling factor
        """
        wraps = self.angle_to_wraps(abs(angle_deg))
        return self.get_torque_scaling_factor(wraps)
