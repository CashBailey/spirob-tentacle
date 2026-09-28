"""Tests for LoadCompensator class."""

import time
import pytest
from unittest.mock import Mock

from spirob.control.load_compensation import (
    LoadCompensator, CompensationParams, TendonState
)


class TestLoadCompensator:
    """Tests for LoadCompensator class."""

    def test_default_params(self):
        """Test default compensation parameters."""
        comp = LoadCompensator()
        assert comp.params.base_speed_dps == 180.0
        assert comp.params.base_torque_percent == 50.0
        assert comp.params.stuck_threshold_deg == 1.0
        assert comp.params.stuck_timeout_sec == 0.5

    def test_custom_params(self):
        """Test custom compensation parameters."""
        params = CompensationParams(
            base_speed_dps=90.0,
            base_torque_percent=60.0
        )
        comp = LoadCompensator(params=params)
        assert comp.params.base_speed_dps == 90.0
        assert comp.params.base_torque_percent == 60.0

    def test_assertive_mode_default_off(self):
        """Test assertive mode is off by default."""
        comp = LoadCompensator()
        assert not comp.assertive_mode

    def test_assertive_mode_toggle_on(self):
        """Test assertive mode can be enabled."""
        comp = LoadCompensator()
        comp.set_assertive_mode(True)
        assert comp.assertive_mode

    def test_assertive_mode_toggle_off(self):
        """Test assertive mode can be disabled."""
        comp = LoadCompensator()
        comp.set_assertive_mode(True)
        comp.set_assertive_mode(False)
        assert not comp.assertive_mode

    def test_effective_radius_without_geometry(self):
        """Test effective radius returns default without geometry configured."""
        comp = LoadCompensator()
        radius = comp.get_effective_radius('u', 0)
        assert radius == LoadCompensator.DEFAULT_CORE_RADIUS_MM

    def test_torque_scale_without_geometry(self):
        """Test torque scale returns 1.0 without geometry configured."""
        comp = LoadCompensator()
        scale = comp.get_torque_scale('u', 0)
        assert scale == 1.0

    def test_not_stuck_initially(self):
        """Test tendon is not stuck initially."""
        comp = LoadCompensator()
        assert not comp.detect_stuck('u')

    def test_not_stuck_when_making_progress(self):
        """Test tendon is not stuck when making progress."""
        comp = LoadCompensator()
        comp.update_position('u', 0, 100)
        comp.update_position('u', 10, 100)  # Moved 10 degrees
        assert not comp.detect_stuck('u')

    def test_reset_tendon_clears_state(self):
        """Test reset_tendon clears compensation state."""
        comp = LoadCompensator()
        comp.update_position('u', 0, 100)
        comp.reset_tendon('u')
        state = comp._get_state('u')
        assert state.last_position_deg == 0.0
        assert state.current_torque_boost == 0.0

    def test_reset_all_clears_all_states(self):
        """Test reset_all clears all tendon states."""
        comp = LoadCompensator()
        comp.update_position('u', 0, 100)
        comp.update_position('v', 0, 100)
        comp.update_position('w', 0, 100)
        comp.reset_all()
        assert len(comp._states) == 0

    def test_get_compensated_params_returns_tuple(self):
        """Test get_compensated_params returns speed and torque tuple."""
        comp = LoadCompensator()
        speed, torque = comp.get_compensated_params('u', 0, 0)
        assert isinstance(speed, float)
        assert isinstance(torque, float)

    def test_get_compensated_params_base_values(self):
        """Test get_compensated_params returns base values when not stuck."""
        params = CompensationParams(
            base_speed_dps=100.0,
            base_torque_percent=40.0
        )
        comp = LoadCompensator(params=params)
        speed, torque = comp.get_compensated_params('u', 0, 0)
        assert speed == 100.0
        assert torque == 40.0

    def test_assertive_mode_increases_speed(self):
        """Test assertive mode increases speed."""
        comp = LoadCompensator()
        speed_normal, _ = comp.get_compensated_params('u', 0, 0)
        comp.set_assertive_mode(True)
        speed_assertive, _ = comp.get_compensated_params('u', 0, 0)
        assert speed_assertive > speed_normal

    def test_assertive_mode_increases_torque(self):
        """Test assertive mode increases torque."""
        comp = LoadCompensator()
        _, torque_normal = comp.get_compensated_params('u', 0, 0)
        comp.set_assertive_mode(True)
        _, torque_assertive = comp.get_compensated_params('u', 0, 0)
        assert torque_assertive > torque_normal

    def test_should_pretension_for_large_reel_in(self):
        """Test should_pretension returns True for large reel-in moves."""
        comp = LoadCompensator()
        comp.update_position('u', 0, 0)
        # Reel-in move of -50 degrees (more negative than threshold)
        assert comp.should_pretension('u', -50)

    def test_should_not_pretension_for_small_move(self):
        """Test should_pretension returns False for small moves."""
        comp = LoadCompensator()
        comp.update_position('u', 0, 0)
        # Small move
        assert not comp.should_pretension('u', -10)

    def test_should_not_pretension_for_reel_out(self):
        """Test should_pretension returns False for reel-out moves."""
        comp = LoadCompensator()
        comp.update_position('u', 0, 0)
        # Reel-out (positive) move
        assert not comp.should_pretension('u', 50)


class TestCompensationParams:
    """Tests for CompensationParams dataclass."""

    def test_default_values(self):
        """Test default parameter values."""
        params = CompensationParams()
        assert params.base_speed_dps == 180.0
        assert params.base_torque_percent == 50.0
        assert params.stuck_threshold_deg == 1.0
        assert params.stuck_timeout_sec == 0.5
        assert params.adaptation_step_percent == 10.0
        assert params.max_torque_percent == 90.0
        assert params.max_speed_dps == 360.0

    def test_custom_values(self):
        """Test custom parameter values."""
        params = CompensationParams(
            base_speed_dps=200.0,
            max_torque_percent=80.0
        )
        assert params.base_speed_dps == 200.0
        assert params.max_torque_percent == 80.0


class TestTendonState:
    """Tests for TendonState dataclass."""

    def test_default_values(self):
        """Test default state values."""
        state = TendonState()
        assert state.last_position_deg == 0.0
        assert state.last_target_deg == 0.0
        assert state.last_progress_time == 0.0
        assert state.current_torque_boost == 0.0
        assert state.current_speed_boost == 0.0
        assert state.is_stuck is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
