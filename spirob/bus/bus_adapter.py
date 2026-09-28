"""Low-level bus communication adapter for servo control."""

import time
import logging
from typing import Optional, Dict, List

import serial

from spirob.protocol.constants import (
    Instruction, ErrorFlag, DEFAULT_TIMEOUT_MS, DEFAULT_RETRY_COUNT,
    BROADCAST_ID, MAX_SERVO_ID, POSITION_MIN, POSITION_MAX,
    ServoModeValue
)
from spirob.protocol.registers import Register
from spirob.protocol.packet import PacketBuilder, PacketParser
from spirob.bus.serial_port import ThreadSafeSerialPort
from spirob.utils.exceptions import (
    CommunicationError, ChecksumError, ServoError, ServoNotFoundError,
    PortError, ServoTimeoutError
)

# Register address validation constants
MAX_REGISTER_ADDRESS = 0xFF  # Single byte address
MAX_READ_LENGTH = 128        # Reasonable max for bulk reads

# Telemetry block: position(2) + speed(2) + load(2) + voltage(1) + temp(1)
TELEMETRY_BLOCK_SIZE = 8

logger = logging.getLogger(__name__)


def _sm_encode(value: int, sign_bit: int = 15) -> int:
    """Encode signed value to STS sign-magnitude format.

    STS servos use sign-magnitude encoding where a specific bit
    indicates the sign, NOT two's complement.

    Args:
        value: Signed integer value
        sign_bit: Bit position used as sign flag (15 for position/speed)
    """
    if value < 0:
        return (-value) | (1 << sign_bit)
    return value


def _sm_decode(raw: int, sign_bit: int = 15) -> int:
    """Decode STS sign-magnitude format to signed value.

    Args:
        raw: Raw unsigned value from servo
        sign_bit: Bit position used as sign flag (15 for position/speed, 10 for load)
    """
    if raw & (1 << sign_bit):
        return -(raw & ~(1 << sign_bit))
    return raw


class BusAdapter:
    """Low-level bus communication with ST/SC serial bus servos.

    Handles packet building, transmission, response parsing, and retries.
    All methods are thread-safe through the underlying serial port.
    """

    # Expected response sizes (header + id + length + data + checksum)
    PING_RESPONSE_SIZE = 6     # Header(2) + ID(1) + Len(1) + Error(1) + Checksum(1)
    READ_OVERHEAD_SIZE = 6     # Same as ping, plus data bytes
    WRITE_RESPONSE_SIZE = 6    # Same as ping

    def __init__(self, serial_port: ThreadSafeSerialPort,
                 retry_count: int = DEFAULT_RETRY_COUNT,
                 timeout_ms: int = DEFAULT_TIMEOUT_MS):
        """Initialize bus adapter.

        Args:
            serial_port: Thread-safe serial port wrapper
            retry_count: Number of retries for failed communications
            timeout_ms: Response timeout in milliseconds
        """
        self._port = serial_port
        self._retry_count = retry_count
        self._timeout = timeout_ms / 1000.0  # Convert to seconds

    @property
    def is_connected(self) -> bool:
        """Check if serial port is open."""
        return self._port.is_open()

    def scan(self, id_range: range = None) -> List[int]:
        """Scan bus for connected servos.

        Args:
            id_range: Range of IDs to scan (default 1-253)

        Returns:
            List of responding servo IDs
        """
        if id_range is None:
            id_range = range(1, MAX_SERVO_ID + 1)

        found_ids = []
        for servo_id in id_range:
            if self.ping(servo_id):
                found_ids.append(servo_id)
                logger.debug(f"Found servo at ID {servo_id}")

        logger.info(f"Bus scan found {len(found_ids)} servos: {found_ids}")
        return found_ids

    def ping(self, servo_id: int) -> bool:
        """Ping a servo to check if it's present.

        Args:
            servo_id: Servo ID to ping

        Returns:
            True if servo responds, False otherwise
        """
        packet = PacketBuilder.build_ping(servo_id)

        try:
            response = self._port.transact(
                packet, self.PING_RESPONSE_SIZE, timeout=self._timeout
            )

            if len(response) < self.PING_RESPONSE_SIZE:
                return False

            resp_id, error_flags, _ = PacketParser.parse_response(response)
            return resp_id == servo_id

        except (PortError, ServoTimeoutError, serial.SerialException, OSError) as e:
            logger.debug(f"Ping failed for ID {servo_id}: {e}")
            return False

    def read_register(self, servo_id: int, address: int,
                      length: int) -> Optional[bytes]:
        """Read register(s) from a servo.

        Args:
            servo_id: Target servo ID
            address: Starting register address
            length: Number of bytes to read

        Returns:
            Register data bytes, or None on failure
        """
        # Validate inputs at boundary
        if address < 0 or address > MAX_REGISTER_ADDRESS:
            logger.error(f"Invalid register address: {address:#x}")
            return None
        if length < 1 or length > MAX_READ_LENGTH:
            logger.error(f"Invalid read length: {length}")
            return None

        packet = PacketBuilder.build_read(servo_id, address, length)
        expected_size = self.READ_OVERHEAD_SIZE + length

        for attempt in range(self._retry_count):
            try:
                response = self._port.transact(
                    packet, expected_size, timeout=self._timeout
                )

                if len(response) < expected_size:
                    logger.debug(f"Short response reading {address:#x} from ID {servo_id}")
                    continue

                resp_id, error_flags, data = PacketParser.parse_response(response)

                if resp_id != servo_id:
                    logger.debug(f"ID mismatch reading from {servo_id}, got {resp_id}")
                    continue

                if error_flags and error_flags != 0:
                    logger.warning(f"Servo {servo_id} error flags: {error_flags:#x}")

                return data

            except (PortError, ServoTimeoutError, serial.SerialException, OSError) as e:
                logger.debug(f"Read attempt {attempt+1} failed: {e}")

        return None

    def write_register(self, servo_id: int, address: int,
                       data: bytes) -> bool:
        """Write register(s) to a servo.

        Args:
            servo_id: Target servo ID
            address: Starting register address
            data: Data bytes to write

        Returns:
            True if write acknowledged, False otherwise
        """
        # Validate inputs at boundary
        if address < 0 or address > MAX_REGISTER_ADDRESS:
            logger.error(f"Invalid register address: {address:#x}")
            return False
        if not data:
            logger.error("Empty data for write_register")
            return False

        packet = PacketBuilder.build_write(servo_id, address, data)

        for attempt in range(self._retry_count):
            try:
                response = self._port.transact(
                    packet, self.WRITE_RESPONSE_SIZE, timeout=self._timeout
                )

                if len(response) < self.WRITE_RESPONSE_SIZE:
                    logger.debug(f"Short response writing to ID {servo_id}")
                    continue

                resp_id, error_flags, _ = PacketParser.parse_response(response)

                if resp_id != servo_id:
                    continue

                if error_flags and error_flags != 0:
                    logger.warning(f"Servo {servo_id} write error: {error_flags:#x}")
                    return False

                return True

            except (PortError, ServoTimeoutError, serial.SerialException, OSError) as e:
                logger.debug(f"Write attempt {attempt+1} failed: {e}")

        return False

    def sync_write(self, servo_ids: List[int], address: int,
                   data_list: List[bytes]) -> bool:
        """Synchronized write to multiple servos.

        No response expected for sync write (uses broadcast).

        Args:
            servo_ids: List of target servo IDs
            address: Starting register address
            data_list: List of data bytes for each servo

        Returns:
            True if packet sent successfully
        """
        try:
            packet = PacketBuilder.build_sync_write(servo_ids, address, data_list)
            self._port.write(packet)
            return True
        except (PortError, ServoTimeoutError, serial.SerialException, OSError) as e:
            logger.error(f"Sync write failed: {e}")
            return False

    # === Convenience Methods ===

    def read_byte(self, servo_id: int, address: int) -> Optional[int]:
        """Read a single byte register."""
        data = self.read_register(servo_id, address, 1)
        return data[0] if data else None

    def read_word(self, servo_id: int, address: int,
                  signed: bool = False) -> Optional[int]:
        """Read a 2-byte register (little-endian)."""
        data = self.read_register(servo_id, address, 2)
        if not data:
            return None
        return PacketParser.unpack_word(data, signed=signed)

    def write_byte(self, servo_id: int, address: int, value: int) -> bool:
        """Write a single byte register."""
        return self.write_register(servo_id, address, bytes([value & 0xFF]))

    def write_word(self, servo_id: int, address: int, value: int) -> bool:
        """Write a 2-byte register (little-endian)."""
        data = value.to_bytes(2, 'little')
        return self.write_register(servo_id, address, data)

    # === Servo-Specific Operations ===

    def read_position(self, servo_id: int) -> Optional[int]:
        """Read current position (0-4095)."""
        return self.read_word(servo_id, Register.PRESENT_POSITION)

    def read_speed(self, servo_id: int) -> Optional[int]:
        """Read current speed (signed)."""
        return self.read_word(servo_id, Register.PRESENT_SPEED, signed=True)

    def read_load(self, servo_id: int) -> Optional[int]:
        """Read current load (signed)."""
        return self.read_word(servo_id, Register.PRESENT_LOAD, signed=True)

    def read_voltage(self, servo_id: int) -> Optional[int]:
        """Read current voltage (0.1V units)."""
        return self.read_byte(servo_id, Register.PRESENT_VOLTAGE)

    def read_temperature(self, servo_id: int) -> Optional[int]:
        """Read current temperature (Celsius)."""
        return self.read_byte(servo_id, Register.PRESENT_TEMP)

    def read_current(self, servo_id: int) -> Optional[int]:
        """Read current draw (6.5mA units)."""
        return self.read_word(servo_id, Register.PRESENT_CURRENT)

    def read_status(self, servo_id: int) -> Optional[int]:
        """Read status/error flags."""
        return self.read_byte(servo_id, Register.STATUS)

    def read_moving(self, servo_id: int) -> Optional[bool]:
        """Read moving flag."""
        val = self.read_byte(servo_id, Register.MOVING)
        return val == 1 if val is not None else None

    def read_telemetry(self, servo_id: int) -> Optional[Dict]:
        """Read all feedback registers in one transaction.

        Reads position, speed, load, voltage, temp in a single bulk read.

        Returns:
            Dictionary with all telemetry values, or None on failure
        """
        # Read from PRESENT_POSITION (0x38) through PRESENT_TEMP (0x3F)
        data = self.read_register(servo_id, Register.PRESENT_POSITION, TELEMETRY_BLOCK_SIZE)
        if not data or len(data) < TELEMETRY_BLOCK_SIZE:
            return None

        # STS servos use sign-magnitude encoding, not two's complement
        # Position/speed: bit 15 = sign, Load: bit 10 = sign
        return {
            'position': _sm_decode(PacketParser.unpack_word(data, 0), sign_bit=15),
            'speed': _sm_decode(PacketParser.unpack_word(data, 2), sign_bit=15),
            'load': _sm_decode(PacketParser.unpack_word(data, 4), sign_bit=10),
            'voltage': data[6],
            'temperature': data[7],
        }

    def write_position(self, servo_id: int, position: int,
                       time_ms: int = 0, speed: int = 0) -> bool:
        """Write target position with optional time and speed.

        Args:
            servo_id: Target servo ID
            position: Target position (signed, multi-turn)
            time_ms: Move duration in milliseconds (0 = use speed)
            speed: Move speed (0 = max speed, ignored if time_ms > 0)

        Returns:
            True if command acknowledged
        """
        # Clamp position to signed 16-bit range
        position = max(POSITION_MIN, min(POSITION_MAX, position))

        # Build data: position(2) + time(2) + speed(2)
        # STS servos use sign-magnitude encoding (bit 15 = sign), not two's complement
        raw_pos = _sm_encode(position)
        data = bytearray()
        data.extend(raw_pos.to_bytes(2, 'little'))
        data.extend(time_ms.to_bytes(2, 'little'))
        data.extend(speed.to_bytes(2, 'little'))

        return self.write_register(servo_id, Register.TARGET_POSITION, bytes(data))

    def set_torque_enable(self, servo_id: int, enable: bool) -> bool:
        """Enable or disable torque output.

        Args:
            servo_id: Target servo ID
            enable: True to enable, False to disable

        Returns:
            True if command acknowledged
        """
        return self.write_byte(servo_id, Register.TORQUE_ENABLE, 1 if enable else 0)

    def set_torque_limit(self, servo_id: int, limit: int) -> bool:
        """Set torque limit (0-1000, representing 0-100%).

        Args:
            servo_id: Target servo ID
            limit: Torque limit value (0-1000)

        Returns:
            True if command acknowledged
        """
        limit = max(0, min(1000, limit))
        return self.write_word(servo_id, Register.TORQUE_LIMIT, limit)

    def set_mode(self, servo_id: int, mode: int) -> bool:
        """Set operating mode.

        Args:
            servo_id: Target servo ID
            mode: Mode value (0=Position, 1=Velocity, 2=PWM, 3=Step)

        Returns:
            True if command acknowledged
        """
        return self.write_byte(servo_id, Register.MODE, mode)

    def unlock_eeprom(self, servo_id: int) -> bool:
        """Unlock EEPROM for writing persistent settings."""
        return self.write_byte(servo_id, Register.EEPROM_LOCK, 0)

    def lock_eeprom(self, servo_id: int) -> bool:
        """Lock EEPROM to protect settings."""
        return self.write_byte(servo_id, Register.EEPROM_LOCK, 1)

    def set_id(self, old_id: int, new_id: int) -> bool:
        """Change servo ID.

        Requires EEPROM unlock. The servo will respond at the new ID
        after this command.

        Args:
            old_id: Current servo ID
            new_id: Desired new ID (1-253)

        Returns:
            True if command acknowledged
        """
        if new_id < 1 or new_id > MAX_SERVO_ID:
            logger.error(f"Invalid new ID: {new_id}")
            return False

        # Unlock EEPROM
        if not self.unlock_eeprom(old_id):
            logger.error(f"Failed to unlock EEPROM for ID {old_id}")
            return False

        # Write new ID
        if not self.write_byte(old_id, Register.ID, new_id):
            logger.error(f"Failed to write new ID {new_id}")
            return False

        # Lock EEPROM
        self.lock_eeprom(new_id)

        logger.info(f"Changed servo ID from {old_id} to {new_id}")
        return True

    def factory_reset(self, servo_id: int) -> bool:
        """Reset servo to factory defaults.

        Warning: This resets ID to 1 and baud to default!

        Args:
            servo_id: Target servo ID

        Returns:
            True if reset command sent
        """
        packet = PacketBuilder.build_reset(servo_id)
        try:
            self._port.write(packet)
            time.sleep(0.5)  # Give servo time to reset
            return True
        except (PortError, ServoTimeoutError, serial.SerialException, OSError) as e:
            logger.error(f"Factory reset failed: {e}")
            return False

    # Deadband (steps) for position control — eliminates PID hunting at targets
    DEADBAND_STEPS = 3

    def configure_multi_turn(self, servo_id: int) -> bool:
        """Configure servo for multi-turn absolute position control (±7 rotations).

        Feetech "Multi-Loop Mode": MODE=0 (position) with both angle limits=0.
        This unlocks the full signed 16-bit position range (±32767 steps)
        while keeping the servo's internal PID for absolute positioning.

        Also sets CW/CCW deadband to reduce PID hunting at target positions.

        Reads current values first to avoid unnecessary EEPROM writes.

        Args:
            servo_id: Target servo ID

        Returns:
            True if configuration succeeded (or was already correct)
        """
        # Read current settings
        mode = self.read_byte(servo_id, Register.MODE)
        min_limit = self.read_word(servo_id, Register.MIN_ANGLE_LIMIT)
        max_limit = self.read_word(servo_id, Register.MAX_ANGLE_LIMIT)
        cw_dead = self.read_byte(servo_id, Register.CW_INSENSITIVE)
        ccw_dead = self.read_byte(servo_id, Register.CCW_INSENSITIVE)

        if mode is None or min_limit is None or max_limit is None:
            logger.error(f"Cannot read current config from servo {servo_id}")
            return False

        need_mode = (mode != ServoModeValue.POSITION)
        need_limits = (min_limit != 0 or max_limit != 0)
        need_deadband = (
            cw_dead is not None and ccw_dead is not None
            and (cw_dead < self.DEADBAND_STEPS or ccw_dead < self.DEADBAND_STEPS)
        )

        if not need_mode and not need_limits and not need_deadband:
            logger.info(f"Servo {servo_id} already configured for multi-turn")
            return True

        changes = []
        if need_mode:
            changes.append(f"MODE {mode}->{ServoModeValue.POSITION}")
        if need_limits:
            changes.append(f"limits [{min_limit},{max_limit}]->[0,0]")
        if need_deadband:
            changes.append(f"deadband [{cw_dead},{ccw_dead}]->[{self.DEADBAND_STEPS},{self.DEADBAND_STEPS}]")
        logger.info(f"Configuring servo {servo_id}: {', '.join(changes)}")

        # Disable torque before changing mode (required by protocol)
        self.set_torque_enable(servo_id, False)

        # Unlock EEPROM (MODE, angle limits, and deadband are EEPROM registers)
        if not self.unlock_eeprom(servo_id):
            logger.error(f"Failed to unlock EEPROM for servo {servo_id}")
            return False

        ok = True

        if need_limits:
            if not self.write_word(servo_id, Register.MIN_ANGLE_LIMIT, 0):
                logger.error(f"Failed to set MIN_ANGLE_LIMIT=0 on servo {servo_id}")
                ok = False
            if not self.write_word(servo_id, Register.MAX_ANGLE_LIMIT, 0):
                logger.error(f"Failed to set MAX_ANGLE_LIMIT=0 on servo {servo_id}")
                ok = False

        if need_mode:
            if not self.write_byte(servo_id, Register.MODE, ServoModeValue.POSITION):
                logger.error(f"Failed to set MODE=POSITION on servo {servo_id}")
                ok = False

        if need_deadband:
            if not self.write_byte(servo_id, Register.CW_INSENSITIVE, self.DEADBAND_STEPS):
                logger.error(f"Failed to set CW deadband on servo {servo_id}")
                ok = False
            if not self.write_byte(servo_id, Register.CCW_INSENSITIVE, self.DEADBAND_STEPS):
                logger.error(f"Failed to set CCW deadband on servo {servo_id}")
                ok = False

        # Lock EEPROM to protect settings
        self.lock_eeprom(servo_id)

        if ok:
            logger.info(f"Servo {servo_id} configured for multi-turn successfully")
        else:
            logger.error(f"Servo {servo_id} multi-turn config had errors")

        return ok
