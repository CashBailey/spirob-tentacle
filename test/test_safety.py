"""Tests for SafetyMonitor class."""

import time
import pytest

from spirob.control.safety import SafetyMonitor, SoftLimits


class TestSafetyMonitor:
    """Tests for SafetyMonitor class."""

    def test_estop_trigger(self):
        """Test emergency stop triggers callback and sets flag."""
        triggered = []
        monitor = SafetyMonitor(on_emergency_stop=lambda r: triggered.append(r))
        monitor.trigger_emergency_stop("Test reason")
        assert monitor.estop_triggered
        assert "Test reason" in triggered

    def test_estop_only_triggers_once(self):
        """Test e-stop callback only called once."""
        count = [0]
        monitor = SafetyMonitor(
            on_emergency_stop=lambda r: count.__setitem__(0, count[0] + 1)
        )
        monitor.trigger_emergency_stop("First")
        monitor.trigger_emergency_stop("Second")
        assert count[0] == 1

    def test_estop_reset(self):
        """Test e-stop can be reset."""
        monitor = SafetyMonitor()
        monitor.trigger_emergency_stop("Test")
        assert monitor.estop_triggered
        monitor.reset_estop()
        assert not monitor.estop_triggered

    def test_estop_disabled_does_not_trigger(self):
        """Test e-stop does not trigger when safety is disabled."""
        triggered = []
        monitor = SafetyMonitor(on_emergency_stop=lambda r: triggered.append(r))
        monitor.disable()
        monitor.trigger_emergency_stop("Test")
        assert not monitor.estop_triggered
        assert len(triggered) == 0

    def test_soft_limits_clamping(self):
        """Test position clamping to soft limits."""
        monitor = SafetyMonitor()
        monitor.set_limits('u', SoftLimits(min_angle_deg=-100, max_angle_deg=100))
        assert monitor.check_position_limit('u', 50) == 50
        assert monitor.check_position_limit('u', 150) == 100
        assert monitor.check_position_limit('u', -150) == -100

    def test_soft_limits_no_limit_set(self):
        """Test position returns unchanged when no limits set."""
        monitor = SafetyMonitor()
        assert monitor.check_position_limit('u', 500) == 500

    def test_temperature_warning(self):
        """Test temperature warning threshold does not trigger e-stop."""
        monitor = SafetyMonitor()
        # Below warn threshold - OK
        assert monitor.check_temperature('u', 50) is True
        assert not monitor.estop_triggered
        # Above warn threshold but below critical - OK (logged warning)
        assert monitor.check_temperature('u', 65) is True
        assert not monitor.estop_triggered

    def test_temperature_critical_triggers_estop(self):
        """Test critical temperature triggers e-stop."""
        monitor = SafetyMonitor()
        assert monitor.check_temperature('u', 75) is False
        assert monitor.estop_triggered

    def test_voltage_low_triggers_estop(self):
        """Test voltage below minimum triggers e-stop."""
        monitor = SafetyMonitor()
        assert monitor.check_voltage('u', 5.0) is False  # Below 6V min
        assert monitor.estop_triggered

    def test_voltage_high_triggers_estop(self):
        """Test voltage above maximum triggers e-stop."""
        monitor = SafetyMonitor()
        assert monitor.check_voltage('u', 15.0) is False  # Above 14V max
        assert monitor.estop_triggered

    def test_voltage_in_range_ok(self):
        """Test voltage in valid range does not trigger e-stop."""
        monitor = SafetyMonitor()
        assert monitor.check_voltage('u', 12.0) is True
        assert not monitor.estop_triggered

    def test_heartbeat_timeout(self):
        """Test heartbeat timeout detection."""
        monitor = SafetyMonitor()
        monitor.set_heartbeat_timeout(10)  # 10ms timeout
        monitor.update_heartbeat('u')
        time.sleep(0.02)  # 20ms
        timed_out = monitor.check_all_heartbeats()
        assert 'u' in timed_out

    def test_heartbeat_not_timed_out(self):
        """Test heartbeat not timed out when recently updated."""
        monitor = SafetyMonitor()
        monitor.set_heartbeat_timeout(1000)  # 1 second timeout
        monitor.update_heartbeat('u')
        timed_out = monitor.check_all_heartbeats()
        assert 'u' not in timed_out


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
