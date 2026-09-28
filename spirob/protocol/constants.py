"""Protocol constants for Waveshare ST/SC serial bus servos.

These servos use the Feetech-compatible protocol with the following packet format:
[0xFF][0xFF][ID][LENGTH][INSTRUCTION][PARAMS...][CHECKSUM]

Reference: https://www.waveshare.com/wiki/ST3215_Servo
"""

from enum import IntEnum


# Packet header bytes
HEADER = bytes([0xFF, 0xFF])

# Broadcast ID (all servos respond)
BROADCAST_ID = 0xFE

# Maximum valid servo ID
MAX_SERVO_ID = 253

# Default communication settings
DEFAULT_BAUDRATE = 1000000  # 1 Mbps


class Instruction(IntEnum):
    """Instruction codes for servo commands."""

    PING = 0x01        # Check if servo is present
    READ = 0x02        # Read data from register(s)
    WRITE = 0x03       # Write data to register(s)
    REG_WRITE = 0x04   # Write data to buffer (executed on ACTION)
    ACTION = 0x05      # Execute buffered REG_WRITE commands
    SYNC_WRITE = 0x83  # Synchronized write to multiple servos
    RESET = 0x06       # Reset servo to factory defaults


class ErrorFlag(IntEnum):
    """Error flags returned in servo status responses."""

    VOLTAGE = 0x01       # Input voltage error
    ANGLE_LIMIT = 0x02   # Angle limit exceeded
    OVERHEAT = 0x04      # Overheating detected
    RANGE = 0x08         # Command out of range
    CHECKSUM = 0x10      # Checksum error in received packet
    OVERLOAD = 0x20      # Overload detected
    INSTRUCTION = 0x40   # Unknown instruction


def get_error_flag_names(error_flags: int) -> list[str]:
    """Get list of active error flag names from error flags bitmask.

    Args:
        error_flags: Bitmask of error flags from servo status

    Returns:
        List of active error flag names (e.g., ["VOLTAGE", "OVERHEAT"])
    """
    names = []
    if error_flags & ErrorFlag.VOLTAGE:
        names.append("VOLTAGE")
    if error_flags & ErrorFlag.ANGLE_LIMIT:
        names.append("ANGLE_LIMIT")
    if error_flags & ErrorFlag.OVERHEAT:
        names.append("OVERHEAT")
    if error_flags & ErrorFlag.RANGE:
        names.append("RANGE")
    if error_flags & ErrorFlag.CHECKSUM:
        names.append("CHECKSUM")
    if error_flags & ErrorFlag.OVERLOAD:
        names.append("OVERLOAD")
    if error_flags & ErrorFlag.INSTRUCTION:
        names.append("INSTRUCTION")
    return names


# Baud rate index to actual rate mapping
BAUD_RATES = {
    0: 1000000,
    1: 500000,
    2: 250000,
    3: 128000,
    4: 115200,
    5: 76800,
    6: 57600,
    7: 38400,
}


class ServoModeValue(IntEnum):
    """Servo operating mode values."""

    POSITION = 0      # Position control mode (servo mode)
    VELOCITY = 1      # Velocity/speed control mode
    PWM = 2           # PWM control mode
    STEP = 3          # Step mode


# Position constants (signed 16-bit for multi-turn, 4096 steps/revolution)
POSITION_MIN = -32767
POSITION_MAX = 32767
POSITION_CENTER = 0
DEGREES_PER_STEP = 360.0 / 4096.0
STEPS_PER_DEGREE = 4096.0 / 360.0

# Torque limit range (0-1000, representing 0-100%)
TORQUE_MIN = 0
TORQUE_MAX = 1000

# Speed range for position moves (steps per second, 0 = max speed)
SPEED_MIN = 0
SPEED_MAX = 4095

# Response timeout defaults (milliseconds)
DEFAULT_TIMEOUT_MS = 50
DEFAULT_RETRY_COUNT = 3
