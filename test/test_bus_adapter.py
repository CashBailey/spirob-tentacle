"""Tests for BusAdapter class."""

import pytest
from unittest.mock import Mock, MagicMock

from spirob.bus.bus_adapter import BusAdapter, TELEMETRY_BLOCK_SIZE
from spirob.utils.exceptions import PortError, ServoTimeoutError


class TestBusAdapter:
    """Tests for BusAdapter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_port = Mock()
        self.mock_port.is_open.return_value = True

    def test_is_connected_delegates_to_port(self):
        """Test is_connected property delegates to port."""
        adapter = BusAdapter(self.mock_port)
        assert adapter.is_connected is True
        self.mock_port.is_open.return_value = False
        assert adapter.is_connected is False

    def test_ping_returns_true_on_valid_response(self):
        """Test ping returns True for valid response."""
        # Valid ping response: ID=1, Length=2, Error=0, Checksum
        self.mock_port.transact.return_value = bytes([0xFF, 0xFF, 0x01, 0x02, 0x00, 0xFC])
        adapter = BusAdapter(self.mock_port)
        assert adapter.ping(1) is True

    def test_ping_returns_false_on_short_response(self):
        """Test ping returns False for short response."""
        self.mock_port.transact.return_value = bytes([0xFF, 0xFF])
        adapter = BusAdapter(self.mock_port)
        assert adapter.ping(1) is False

    def test_ping_returns_false_on_id_mismatch(self):
        """Test ping returns False when response ID doesn't match."""
        # Response with ID=2 instead of 1
        self.mock_port.transact.return_value = bytes([0xFF, 0xFF, 0x02, 0x02, 0x00, 0xFB])
        adapter = BusAdapter(self.mock_port)
        assert adapter.ping(1) is False

    def test_ping_returns_false_on_port_error(self):
        """Test ping returns False when port raises PortError."""
        self.mock_port.transact.side_effect = PortError("Port closed")
        adapter = BusAdapter(self.mock_port)
        assert adapter.ping(1) is False

    def test_ping_returns_false_on_timeout(self):
        """Test ping returns False when timeout occurs."""
        self.mock_port.transact.side_effect = ServoTimeoutError("Timeout")
        adapter = BusAdapter(self.mock_port)
        assert adapter.ping(1) is False

    def test_read_register_validates_negative_address(self):
        """Test read_register rejects negative addresses."""
        adapter = BusAdapter(self.mock_port)
        assert adapter.read_register(1, -1, 1) is None

    def test_read_register_validates_address_too_large(self):
        """Test read_register rejects addresses > 0xFF."""
        adapter = BusAdapter(self.mock_port)
        assert adapter.read_register(1, 0x100, 1) is None

    def test_read_register_validates_zero_length(self):
        """Test read_register rejects zero length."""
        adapter = BusAdapter(self.mock_port)
        assert adapter.read_register(1, 0x38, 0) is None

    def test_read_register_validates_excessive_length(self):
        """Test read_register rejects excessive lengths."""
        adapter = BusAdapter(self.mock_port)
        assert adapter.read_register(1, 0x38, 200) is None

    def test_write_register_validates_negative_address(self):
        """Test write_register rejects negative addresses."""
        adapter = BusAdapter(self.mock_port)
        assert adapter.write_register(1, -1, b'\x00') is False

    def test_write_register_validates_address_too_large(self):
        """Test write_register rejects addresses > 0xFF."""
        adapter = BusAdapter(self.mock_port)
        assert adapter.write_register(1, 0x100, b'\x00') is False

    def test_write_register_rejects_empty_data(self):
        """Test write_register rejects empty data."""
        adapter = BusAdapter(self.mock_port)
        assert adapter.write_register(1, 0x38, b'') is False

    def test_telemetry_block_size_constant(self):
        """Test TELEMETRY_BLOCK_SIZE is correctly defined."""
        # position(2) + speed(2) + load(2) + voltage(1) + temp(1) = 8
        assert TELEMETRY_BLOCK_SIZE == 8

    def test_scan_returns_found_ids(self):
        """Test scan returns list of responding servo IDs."""
        # Mock ping to succeed for ID 1 and 3, fail for ID 2
        def mock_transact(packet, size, timeout):
            servo_id = packet[2]  # ID is at position 2
            if servo_id in [1, 3]:
                checksum = (~(servo_id + 2 + 0) & 0xFF)
                return bytes([0xFF, 0xFF, servo_id, 0x02, 0x00, checksum])
            return bytes()

        self.mock_port.transact.side_effect = mock_transact
        adapter = BusAdapter(self.mock_port)
        found = adapter.scan(range(1, 4))
        assert 1 in found
        assert 2 not in found
        assert 3 in found


class TestBusAdapterConvenienceMethods:
    """Tests for BusAdapter convenience methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_port = Mock()
        self.mock_port.is_open.return_value = True

    def test_read_byte_calls_read_register(self):
        """Test read_byte calls read_register with length=1."""
        adapter = BusAdapter(self.mock_port)
        # Mock successful response
        self.mock_port.transact.return_value = bytes([0xFF, 0xFF, 0x01, 0x03, 0x00, 0x42, 0xB9])
        result = adapter.read_byte(1, 0x38)
        assert result == 0x42

    def test_read_word_calls_read_register(self):
        """Test read_word calls read_register with length=2."""
        adapter = BusAdapter(self.mock_port)
        # Mock successful response with 2-byte data (little-endian 0x0800 = 2048)
        self.mock_port.transact.return_value = bytes([0xFF, 0xFF, 0x01, 0x04, 0x00, 0x00, 0x08, 0xF2])
        result = adapter.read_word(1, 0x38)
        assert result == 2048


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
