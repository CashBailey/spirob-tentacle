"""Packet building and parsing for Waveshare ST/SC servo protocol.

Packet format:
[0xFF][0xFF][ID][LENGTH][INSTRUCTION][PARAM1...PARAMN][CHECKSUM]

Where:
- LENGTH = number of params + 2 (instruction + checksum)
- CHECKSUM = ~(ID + LENGTH + INSTRUCTION + sum(PARAMS)) & 0xFF
"""

from typing import Optional, Tuple, List
from spirob.protocol.constants import HEADER, Instruction, BROADCAST_ID, MAX_SERVO_ID


# Valid servo ID range: 0-253 for individual servos, 254 (0xFE) for broadcast
MIN_SERVO_ID = 0


class PacketBuilder:
    """Constructs instruction packets for the servo protocol."""

    @staticmethod
    def calculate_checksum(servo_id: int, length: int,
                           instruction: int, params: bytes) -> int:
        """Calculate packet checksum.

        Checksum = ~(ID + Length + Instruction + sum(Params)) & 0xFF
        """
        total = servo_id + length + instruction + sum(params)
        return (~total) & 0xFF

    @staticmethod
    def build_packet(servo_id: int, instruction: int, params: bytes = b'') -> bytes:
        """Build a complete instruction packet.

        Args:
            servo_id: Target servo ID (0-253, or 0xFE for broadcast)
            instruction: Instruction code
            params: Parameter bytes

        Returns:
            Complete packet bytes including header and checksum

        Raises:
            ValueError: If servo_id is outside valid range (0-253 or broadcast 0xFE)
        """
        # Validate servo_id at boundary
        if servo_id < MIN_SERVO_ID or (servo_id > MAX_SERVO_ID and servo_id != BROADCAST_ID):
            raise ValueError(
                f"Invalid servo_id {servo_id}: must be {MIN_SERVO_ID}-{MAX_SERVO_ID} "
                f"or broadcast ({BROADCAST_ID})"
            )

        length = len(params) + 2  # params + instruction + checksum
        checksum = PacketBuilder.calculate_checksum(servo_id, length, instruction, params)

        packet = bytearray(HEADER)
        packet.append(servo_id)
        packet.append(length)
        packet.append(instruction)
        packet.extend(params)
        packet.append(checksum)

        return bytes(packet)

    @staticmethod
    def build_ping(servo_id: int) -> bytes:
        """Build PING packet to check if servo is present."""
        return PacketBuilder.build_packet(servo_id, Instruction.PING)

    @staticmethod
    def build_read(servo_id: int, address: int, length: int) -> bytes:
        """Build READ packet to read register(s).

        Args:
            servo_id: Target servo ID
            address: Starting register address
            length: Number of bytes to read
        """
        params = bytes([address, length])
        return PacketBuilder.build_packet(servo_id, Instruction.READ, params)

    @staticmethod
    def build_write(servo_id: int, address: int, data: bytes) -> bytes:
        """Build WRITE packet to write register(s).

        Args:
            servo_id: Target servo ID
            address: Starting register address
            data: Data bytes to write
        """
        params = bytes([address]) + data
        return PacketBuilder.build_packet(servo_id, Instruction.WRITE, params)

    @staticmethod
    def build_reg_write(servo_id: int, address: int, data: bytes) -> bytes:
        """Build REG_WRITE packet for buffered write.

        The write is buffered until an ACTION command is sent.
        """
        params = bytes([address]) + data
        return PacketBuilder.build_packet(servo_id, Instruction.REG_WRITE, params)

    @staticmethod
    def build_action() -> bytes:
        """Build ACTION packet to execute buffered REG_WRITE commands.

        Sent to broadcast address to trigger all pending writes.
        """
        return PacketBuilder.build_packet(BROADCAST_ID, Instruction.ACTION)

    @staticmethod
    def build_sync_write(servo_ids: List[int], address: int,
                         data_list: List[bytes]) -> bytes:
        """Build SYNC_WRITE packet for synchronized multi-servo write.

        All servos receive their data simultaneously, useful for coordinated motion.

        Args:
            servo_ids: List of target servo IDs
            address: Starting register address (same for all)
            data_list: List of data bytes for each servo (must match servo_ids length)

        Returns:
            Complete SYNC_WRITE packet
        """
        if len(servo_ids) != len(data_list):
            raise ValueError("servo_ids and data_list must have same length")

        if not data_list:
            raise ValueError("data_list cannot be empty")

        data_length = len(data_list[0])
        for d in data_list:
            if len(d) != data_length:
                raise ValueError("All data entries must have same length")

        # SYNC_WRITE format: [address][data_length][ID1][data1...][ID2][data2...]...
        params = bytearray([address, data_length])
        for servo_id, data in zip(servo_ids, data_list):
            params.append(servo_id)
            params.extend(data)

        return PacketBuilder.build_packet(BROADCAST_ID, Instruction.SYNC_WRITE, bytes(params))

    @staticmethod
    def build_reset(servo_id: int) -> bytes:
        """Build RESET packet to restore factory defaults.

        Warning: This will reset ID to 1 and baud to default!
        """
        return PacketBuilder.build_packet(servo_id, Instruction.RESET)

    @staticmethod
    def build_write_position(servo_id: int, position: int,
                             time_ms: int = 0, speed: int = 0) -> bytes:
        """Build WRITE packet for position with time and speed.

        Args:
            servo_id: Target servo ID
            position: Target position (0-4095)
            time_ms: Move duration in milliseconds (0 = use speed)
            speed: Move speed in steps/sec (0 = max speed, ignored if time_ms > 0)
        """
        # Write to TARGET_POSITION (0x2A), which is followed by MOVE_TIME and MOVE_SPEED
        from spirob.protocol.registers import Register

        data = bytearray()
        data.extend(position.to_bytes(2, 'little'))
        data.extend(time_ms.to_bytes(2, 'little'))
        data.extend(speed.to_bytes(2, 'little'))

        return PacketBuilder.build_write(servo_id, Register.TARGET_POSITION, bytes(data))


class PacketParser:
    """Parses response packets from servos."""

    # Minimum valid response packet size: header(2) + id(1) + length(1) + error(1) + checksum(1)
    MIN_RESPONSE_SIZE = 6

    @staticmethod
    def validate_checksum(data: bytes) -> bool:
        """Validate packet checksum.

        Args:
            data: Complete packet bytes including header and checksum

        Returns:
            True if checksum is valid
        """
        if len(data) < PacketParser.MIN_RESPONSE_SIZE:
            return False

        # Skip header, extract ID, length, and calculate expected checksum
        servo_id = data[2]
        length = data[3]

        # Verify length matches actual data
        expected_total_length = 4 + length  # header(2) + id(1) + length(1) + (instruction/error + params + checksum)
        if len(data) < expected_total_length:
            return False

        # Calculate checksum over ID, length, and data (excluding final checksum byte)
        packet_data = data[2:2+length+1]  # ID, length, then 'length' bytes of data
        total = sum(packet_data)
        calculated = (~total) & 0xFF
        received = data[2 + length + 1]

        return calculated == received

    @staticmethod
    def find_packet_start(data: bytes) -> int:
        """Find the start of a valid packet (0xFF 0xFF header).

        Returns:
            Index of first header byte, or -1 if not found
        """
        for i in range(len(data) - 1):
            if data[i] == 0xFF and data[i+1] == 0xFF:
                return i
        return -1

    @staticmethod
    def parse_response(data: bytes) -> Tuple[Optional[int], Optional[int], Optional[bytes]]:
        """Parse a response packet from servo.

        Args:
            data: Raw bytes received from serial port

        Returns:
            Tuple of (servo_id, error_flags, data_bytes) or (None, None, None) if invalid
        """
        # Find packet start
        start = PacketParser.find_packet_start(data)
        if start < 0:
            return None, None, None

        data = data[start:]

        if len(data) < PacketParser.MIN_RESPONSE_SIZE:
            return None, None, None

        servo_id = data[2]
        length = data[3]

        # Check we have enough data
        total_length = 4 + length
        if len(data) < total_length:
            return None, None, None

        # Validate checksum
        if not PacketParser.validate_checksum(data[:total_length]):
            return None, None, None

        # Extract error flags (first byte after header/id/length)
        error_flags = data[4]

        # Extract data bytes (between error and checksum)
        # length includes error byte and checksum, so data is length - 2 bytes
        data_bytes = bytes(data[5:4+length-1]) if length > 2 else b''

        return servo_id, error_flags, data_bytes

    @staticmethod
    def parse_ping_response(data: bytes) -> Tuple[Optional[int], Optional[int]]:
        """Parse PING response.

        Returns:
            Tuple of (servo_id, error_flags) or (None, None) if invalid
        """
        servo_id, error_flags, _ = PacketParser.parse_response(data)
        return servo_id, error_flags

    @staticmethod
    def parse_read_response(data: bytes) -> Tuple[Optional[int], Optional[int], Optional[bytes]]:
        """Parse READ response.

        Returns:
            Tuple of (servo_id, error_flags, register_data)
        """
        return PacketParser.parse_response(data)

    @staticmethod
    def unpack_word(data: bytes, offset: int = 0, signed: bool = False) -> Optional[int]:
        """Unpack a 2-byte little-endian word from data.

        Args:
            data: Byte data
            offset: Starting offset
            signed: If True, interpret as signed int16

        Returns:
            Unpacked value, or None if data is too short
        """
        if len(data) < offset + 2:
            return None
        value = int.from_bytes(data[offset:offset+2], 'little')
        if signed and value > 32767:
            value -= 65536
        return value

    @staticmethod
    def unpack_byte(data: bytes, offset: int = 0) -> Optional[int]:
        """Unpack a single byte from data.

        Returns:
            Unpacked byte value, or None if data is too short
        """
        if len(data) <= offset:
            return None
        return data[offset]
