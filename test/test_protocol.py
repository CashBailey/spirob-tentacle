"""Unit tests for spirob protocol layer."""

import pytest

from spirob.protocol.constants import Instruction, ErrorFlag, HEADER
from spirob.protocol.packet import PacketBuilder, PacketParser
from spirob.protocol.registers import Register


class TestPacketBuilder:
    """Tests for PacketBuilder class."""

    def test_checksum_calculation(self):
        """Test checksum calculation."""
        # Simple ping packet: ID=1, Length=2, Instruction=PING(0x01)
        # Checksum = ~(1 + 2 + 0x01) & 0xFF = ~4 & 0xFF = 0xFB
        checksum = PacketBuilder.calculate_checksum(
            servo_id=1,
            length=2,
            instruction=Instruction.PING,
            params=b''
        )
        assert checksum == 0xFB

    def test_build_ping(self):
        """Test building a ping packet."""
        packet = PacketBuilder.build_ping(servo_id=1)
        # Expected: [0xFF, 0xFF, 0x01, 0x02, 0x01, 0xFB]
        assert packet == bytes([0xFF, 0xFF, 0x01, 0x02, 0x01, 0xFB])

    def test_build_read(self):
        """Test building a read packet."""
        packet = PacketBuilder.build_read(servo_id=1, address=0x38, length=2)
        # Params: [0x38, 0x02]
        # Length = 4 (2 params + 1 instruction + 1 checksum)
        # Checksum = ~(1 + 4 + 0x02 + 0x38 + 0x02) & 0xFF
        assert packet[0:2] == HEADER
        assert packet[2] == 1  # ID
        assert packet[3] == 4  # Length
        assert packet[4] == Instruction.READ

    def test_build_write(self):
        """Test building a write packet."""
        packet = PacketBuilder.build_write(
            servo_id=1,
            address=Register.TARGET_POSITION,
            data=bytes([0x00, 0x08])  # Position 2048
        )
        assert packet[0:2] == HEADER
        assert packet[2] == 1  # ID
        assert packet[4] == Instruction.WRITE

    def test_build_sync_write(self):
        """Test building a sync write packet."""
        packet = PacketBuilder.build_sync_write(
            servo_ids=[1, 2, 3],
            address=Register.TARGET_POSITION,
            data_list=[
                bytes([0x00, 0x08]),
                bytes([0x00, 0x08]),
                bytes([0x00, 0x08]),
            ]
        )
        assert packet[0:2] == HEADER
        assert packet[2] == 0xFE  # Broadcast ID


class TestPacketParser:
    """Tests for PacketParser class."""

    def test_validate_checksum(self):
        """Test checksum validation."""
        # Valid ping response: ID=1, Length=2, Error=0, Checksum
        valid_packet = bytes([0xFF, 0xFF, 0x01, 0x02, 0x00, 0xFC])
        assert PacketParser.validate_checksum(valid_packet) is True

    def test_find_packet_start(self):
        """Test finding packet start in data."""
        data = bytes([0x00, 0x00, 0xFF, 0xFF, 0x01, 0x02, 0x00, 0xFC])
        start = PacketParser.find_packet_start(data)
        assert start == 2

    def test_parse_response(self):
        """Test parsing a response packet."""
        # Ping response: ID=1, Error=0
        packet = bytes([0xFF, 0xFF, 0x01, 0x02, 0x00, 0xFC])
        servo_id, error_flags, data = PacketParser.parse_response(packet)
        assert servo_id == 1
        assert error_flags == 0
        assert data == b''

    def test_unpack_word(self):
        """Test unpacking little-endian word."""
        data = bytes([0x00, 0x08])  # 2048 in little-endian
        value = PacketParser.unpack_word(data)
        assert value == 2048

    def test_unpack_word_signed(self):
        """Test unpacking signed word."""
        data = bytes([0xFF, 0xFF])  # -1 in little-endian signed
        value = PacketParser.unpack_word(data, signed=True)
        assert value == -1


class TestErrorFlags:
    """Tests for error flag handling."""

    def test_error_flag_values(self):
        """Test error flag bit values."""
        assert ErrorFlag.VOLTAGE == 0x01
        assert ErrorFlag.ANGLE_LIMIT == 0x02
        assert ErrorFlag.OVERHEAT == 0x04
        assert ErrorFlag.OVERLOAD == 0x20

    def test_multiple_errors(self):
        """Test combining multiple error flags."""
        combined = ErrorFlag.VOLTAGE | ErrorFlag.OVERHEAT
        assert combined & ErrorFlag.VOLTAGE
        assert combined & ErrorFlag.OVERHEAT
        assert not (combined & ErrorFlag.OVERLOAD)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
