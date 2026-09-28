"""Tests for conversion utilities."""

import math
import pytest

from spirob.utils.conversions import (
    steps_to_degrees, degrees_to_steps,
    degrees_to_radians, radians_to_degrees,
    steps_to_radians, radians_to_steps,
    normalize_angle,
    voltage_raw_to_volts, current_raw_to_ma,
    torque_percent_to_raw, torque_raw_to_percent,
    speed_dps_to_raw, speed_raw_to_dps
)


class TestAngleConversions:
    """Tests for angle conversion functions."""

    def test_steps_to_degrees_zero(self):
        """Test steps_to_degrees at zero."""
        assert steps_to_degrees(0) == 0.0

    def test_steps_to_degrees_center(self):
        """Test steps_to_degrees at center position."""
        result = steps_to_degrees(2048)
        assert abs(result - 180.0) < 0.1

    def test_steps_to_degrees_full_rotation(self):
        """Test steps_to_degrees at full rotation."""
        result = steps_to_degrees(4096)
        assert abs(result - 360.0) < 0.1

    def test_degrees_to_steps_zero(self):
        """Test degrees_to_steps at zero."""
        assert degrees_to_steps(0) == 0

    def test_degrees_to_steps_clamps_negative(self):
        """Test degrees_to_steps clamps negative values to 0."""
        assert degrees_to_steps(-10) == 0

    def test_degrees_to_steps_clamps_excessive(self):
        """Test degrees_to_steps clamps values > 360 to 4095."""
        assert degrees_to_steps(400) == 4095

    def test_degrees_to_steps_half_rotation(self):
        """Test degrees_to_steps at 180 degrees."""
        result = degrees_to_steps(180)
        assert abs(result - 2048) <= 1  # Allow rounding

    def test_roundtrip_degrees_steps(self):
        """Test roundtrip conversion degrees -> steps -> degrees."""
        for deg in [0, 45, 90, 135, 180, 225, 270, 315, 359]:
            steps = degrees_to_steps(deg)
            back = steps_to_degrees(steps)
            assert abs(back - deg) < 0.1

    def test_degrees_to_radians_zero(self):
        """Test degrees_to_radians at zero."""
        assert degrees_to_radians(0) == 0.0

    def test_degrees_to_radians_90(self):
        """Test degrees_to_radians at 90 degrees."""
        result = degrees_to_radians(90)
        assert abs(result - math.pi / 2) < 0.0001

    def test_degrees_to_radians_180(self):
        """Test degrees_to_radians at 180 degrees."""
        result = degrees_to_radians(180)
        assert abs(result - math.pi) < 0.0001

    def test_radians_to_degrees_zero(self):
        """Test radians_to_degrees at zero."""
        assert radians_to_degrees(0) == 0.0

    def test_radians_to_degrees_pi(self):
        """Test radians_to_degrees at pi."""
        result = radians_to_degrees(math.pi)
        assert abs(result - 180) < 0.0001

    def test_radians_to_degrees_2pi(self):
        """Test radians_to_degrees at 2*pi."""
        result = radians_to_degrees(2 * math.pi)
        assert abs(result - 360) < 0.0001

    def test_steps_to_radians(self):
        """Test steps_to_radians conversion."""
        result = steps_to_radians(2048)  # 180 degrees
        assert abs(result - math.pi) < 0.01

    def test_radians_to_steps(self):
        """Test radians_to_steps conversion."""
        result = radians_to_steps(math.pi)  # 180 degrees
        assert abs(result - 2048) <= 1


class TestNormalizeAngle:
    """Tests for normalize_angle function."""

    def test_normalize_positive_in_range(self):
        """Test normalize_angle with positive value in range."""
        assert abs(normalize_angle(90) - 90) < 0.001

    def test_normalize_zero(self):
        """Test normalize_angle at zero."""
        assert normalize_angle(0) == 0.0

    def test_normalize_360_wraps_to_zero(self):
        """Test normalize_angle wraps 360 to 0."""
        assert abs(normalize_angle(360) - 0) < 0.001

    def test_normalize_negative(self):
        """Test normalize_angle with negative value."""
        result = normalize_angle(-90)
        assert abs(result - 270) < 0.001

    def test_normalize_large_positive(self):
        """Test normalize_angle with value > 360."""
        result = normalize_angle(450)
        assert abs(result - 90) < 0.001

    def test_normalize_large_negative(self):
        """Test normalize_angle with large negative value."""
        result = normalize_angle(-450)
        assert abs(result - 270) < 0.001


class TestUnitConversions:
    """Tests for unit conversion functions."""

    def test_voltage_raw_to_volts_zero(self):
        """Test voltage_raw_to_volts at zero."""
        assert voltage_raw_to_volts(0) == 0.0

    def test_voltage_raw_to_volts_typical(self):
        """Test voltage_raw_to_volts at typical value."""
        assert voltage_raw_to_volts(120) == 12.0

    def test_current_raw_to_ma_zero(self):
        """Test current_raw_to_ma at zero."""
        assert current_raw_to_ma(0) == 0.0

    def test_current_raw_to_ma_typical(self):
        """Test current_raw_to_ma at typical value."""
        assert current_raw_to_ma(100) == 650.0

    def test_torque_percent_to_raw_zero(self):
        """Test torque_percent_to_raw at zero."""
        assert torque_percent_to_raw(0) == 0

    def test_torque_percent_to_raw_50(self):
        """Test torque_percent_to_raw at 50%."""
        assert torque_percent_to_raw(50) == 500

    def test_torque_percent_to_raw_100(self):
        """Test torque_percent_to_raw at 100%."""
        assert torque_percent_to_raw(100) == 1000

    def test_torque_percent_to_raw_clamps_negative(self):
        """Test torque_percent_to_raw clamps negative values."""
        assert torque_percent_to_raw(-10) == 0

    def test_torque_percent_to_raw_clamps_excessive(self):
        """Test torque_percent_to_raw clamps values > 100."""
        assert torque_percent_to_raw(150) == 1000

    def test_torque_raw_to_percent_zero(self):
        """Test torque_raw_to_percent at zero."""
        assert torque_raw_to_percent(0) == 0.0

    def test_torque_raw_to_percent_500(self):
        """Test torque_raw_to_percent at 500."""
        assert torque_raw_to_percent(500) == 50.0

    def test_torque_raw_to_percent_1000(self):
        """Test torque_raw_to_percent at 1000."""
        assert torque_raw_to_percent(1000) == 100.0

    def test_speed_dps_to_raw_zero(self):
        """Test speed_dps_to_raw at zero."""
        assert speed_dps_to_raw(0) == 0

    def test_speed_dps_to_raw_positive(self):
        """Test speed_dps_to_raw with positive value."""
        result = speed_dps_to_raw(360)
        # 360 deg/s = 4096 steps/s
        assert result == 4095  # Clamped to max

    def test_speed_raw_to_dps_zero(self):
        """Test speed_raw_to_dps at zero."""
        assert speed_raw_to_dps(0) == 0.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
