"""Tests for ServoManager class."""

import pytest
from unittest.mock import Mock, PropertyMock

from spirob.control.servo_manager import ServoManager
from spirob.control.safety import SafetyMonitor
from spirob.control.load_compensation import LoadCompensator


class TestServoManager:
    """Tests for ServoManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_adapter = Mock()
        self.mock_adapter.is_connected = True
        self.mock_safety = Mock(spec=SafetyMonitor)
        type(self.mock_safety).estop_triggered = PropertyMock(return_value=False)
        self.mock_compensator = Mock(spec=LoadCompensator)

    def test_initialization_with_injected_dependencies(self):
        """Test manager accepts injected dependencies."""
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1, 'v': 2, 'w': 3},
            safety_monitor=self.mock_safety,
            load_compensator=self.mock_compensator
        )
        assert manager._safety is self.mock_safety
        assert manager._compensator is self.mock_compensator

    def test_default_dependencies_created(self):
        """Test default dependencies created when not injected."""
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1}
        )
        assert isinstance(manager._safety, SafetyMonitor)
        assert isinstance(manager._compensator, LoadCompensator)

    def test_servo_creation(self):
        """Test servos created for each tendon in id_map."""
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1, 'v': 2, 'w': 3}
        )
        assert len(manager._servos) == 3
        assert 'u' in manager._servos
        assert 'v' in manager._servos
        assert 'w' in manager._servos

    def test_get_servo_returns_correct_servo(self):
        """Test get_servo returns servo by name."""
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1, 'v': 2}
        )
        servo_u = manager.get_servo('u')
        assert servo_u is not None
        assert servo_u.id == 1

    def test_get_servo_returns_none_for_unknown(self):
        """Test get_servo returns None for unknown tendon."""
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1}
        )
        assert manager.get_servo('x') is None

    def test_get_all_servos_returns_copy(self):
        """Test get_all_servos returns dictionary of servos."""
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1, 'v': 2}
        )
        servos = manager.get_all_servos()
        assert 'u' in servos
        assert 'v' in servos
        assert len(servos) == 2

    def test_set_target_blocked_during_estop(self):
        """Test set_target_angle blocked when e-stop active."""
        type(self.mock_safety).estop_triggered = PropertyMock(return_value=True)
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1},
            safety_monitor=self.mock_safety
        )
        result = manager.set_target_angle('u', 45.0)
        assert result is False

    def test_set_all_targets_blocked_during_estop(self):
        """Test set_all_targets blocked when e-stop active."""
        type(self.mock_safety).estop_triggered = PropertyMock(return_value=True)
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1, 'v': 2},
            safety_monitor=self.mock_safety
        )
        result = manager.set_all_targets({'u': 45.0, 'v': 90.0})
        assert result is False

    def test_emergency_stop_triggers_safety(self):
        """Test emergency_stop calls safety monitor."""
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1},
            safety_monitor=self.mock_safety
        )
        manager.emergency_stop()
        self.mock_safety.trigger_emergency_stop.assert_called_once()

    def test_reset_estop_calls_safety(self):
        """Test reset_estop calls safety monitor."""
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1},
            safety_monitor=self.mock_safety
        )
        manager.reset_estop()
        self.mock_safety.reset_estop.assert_called_once()

    def test_initial_state(self):
        """Test initial manager state."""
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1}
        )
        assert not manager.is_initialized
        assert not manager.is_telemetry_running

    def test_properties(self):
        """Test manager properties."""
        manager = ServoManager(
            bus_adapter=self.mock_adapter,
            id_map={'u': 1},
            safety_monitor=self.mock_safety,
            load_compensator=self.mock_compensator
        )
        assert manager.safety is self.mock_safety
        assert manager.compensator is self.mock_compensator


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
