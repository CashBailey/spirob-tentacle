"""Register definitions for Waveshare ST/SC serial bus servos.

Register map based on ST3215 servo memory table.
Reference: https://www.waveshare.com/wiki/ST3215_Servo
"""

from dataclasses import dataclass
from enum import IntEnum


class Register(IntEnum):
    """Register addresses for servo memory.

    Registers are divided into EEPROM (persistent) and RAM (volatile) areas.
    EEPROM changes require unlocking before write and are saved on power cycle.
    RAM changes take effect immediately but are lost on power cycle.
    """

    # === EEPROM Area (Persistent Storage) ===

    # Device identification
    FIRMWARE_MAJOR = 0x00      # Firmware major version (R)
    FIRMWARE_MINOR = 0x01      # Firmware minor version (R)
    SERVO_MAJOR = 0x03         # Servo series major version (R)
    SERVO_MINOR = 0x04         # Servo series minor version (R)
    ID = 0x05                  # Servo ID (RW, 0-253)
    BAUD_RATE = 0x06           # Baud rate index (RW, 0-7)
    RETURN_DELAY = 0x07        # Response delay time (RW)
    RESPONSE_STATUS = 0x08     # Response level setting (RW)

    # Angle limits
    MIN_ANGLE_LIMIT = 0x09     # Minimum angle limit (RW, 2 bytes)
    MAX_ANGLE_LIMIT = 0x0B     # Maximum angle limit (RW, 2 bytes)

    # Temperature limit
    MAX_TEMP_LIMIT = 0x0D      # Maximum temperature limit (RW)

    # Voltage limits
    MAX_VOLTAGE_LIMIT = 0x0E   # Maximum input voltage (RW)
    MIN_VOLTAGE_LIMIT = 0x0F   # Minimum input voltage (RW)

    # Torque limit (EEPROM default)
    TORQUE_LIMIT_EEPROM = 0x10  # Max torque limit (RW, 2 bytes)

    # Reserved/Special
    PHASE = 0x12               # Phase setting (RW)
    UNLOAD_CONDITION = 0x13    # Unload condition (RW)
    LED_ALARM_COND = 0x14      # LED alarm condition (RW)
    POS_PROPORTIONAL = 0x15    # Position P gain (RW)
    POS_DERIVATIVE = 0x16      # Position D gain (RW)
    POS_INTEGRAL = 0x17        # Position I gain (RW)
    MIN_STARTUP_FORCE = 0x18   # Minimum startup force (RW, 2 bytes)

    # Clock
    CW_INSENSITIVE = 0x1A      # Clockwise insensitive zone (RW)
    CCW_INSENSITIVE = 0x1B     # Counter-clockwise insensitive zone (RW)

    # Protection
    PROTECT_CURRENT = 0x1C     # Protection current (RW, 2 bytes)
    ANGULAR_RESOLUTION = 0x1E  # Angular resolution (RW)
    POSITION_OFFSET = 0x1F     # Position offset (RW, 2 bytes, signed)

    # === EEPROM Area (continued) ===

    MODE = 0x21                # Operating mode (EEPROM RW): 0=Position, 1=Velocity, 2=PWM, 3=Step

    # Note: Register 0x22 is NOT the EEPROM lock on STS servos.
    # The correct lock register for STS (ST3215) is at address 55 (0x37).
    EEPROM_LOCK = 55           # EEPROM lock (RW): 0=Unlocked, 1=Locked (SMS_STS_LOCK)

    # Torque
    TORQUE_ENABLE = 0x28       # Torque enable (RW): 0=Off, 1=On

    # Motion control
    TARGET_POSITION = 0x2A     # Goal position (RW, 2 bytes, signed multi-turn)
    MOVE_TIME = 0x2C           # Movement time (RW, 2 bytes, ms)
    MOVE_SPEED = 0x2E          # Movement speed (RW, 2 bytes, steps/s)
    TORQUE_LIMIT = 0x30        # Runtime torque limit (RW, 2 bytes, 0-1000)

    # Current limit
    CURRENT_LIMIT = 0x32       # Current limit (RW, 2 bytes)

    # Acceleration
    ACCELERATION = 0x29        # Acceleration (RW)

    # === Feedback Registers (Read-Only) ===

    PRESENT_POSITION = 0x38    # Current position (R, 2 bytes, signed multi-turn)
    PRESENT_SPEED = 0x3A       # Current speed (R, 2 bytes, signed)
    PRESENT_LOAD = 0x3C        # Current load (R, 2 bytes, signed)
    PRESENT_VOLTAGE = 0x3E     # Current voltage (R, 0.1V units)
    PRESENT_TEMP = 0x3F        # Current temperature (R, Celsius)
    ASYNC_WRITE_FLAG = 0x40    # Async write status flag (R)
    STATUS = 0x41              # Servo status/error flags (R)
    MOVING = 0x42              # Moving flag (R): 0=Stopped, 1=Moving
    PRESENT_CURRENT = 0x45     # Current draw (R, 2 bytes, 6.5mA units)


@dataclass
class RegisterInfo:
    """Metadata about a register."""

    address: int
    size: int           # 1 or 2 bytes
    writable: bool
    signed: bool = False
    description: str = ""


# Register metadata lookup table
REGISTER_INFO = {
    Register.ID: RegisterInfo(0x05, 1, True, False, "Servo ID"),
    Register.BAUD_RATE: RegisterInfo(0x06, 1, True, False, "Baud rate index"),
    Register.MIN_ANGLE_LIMIT: RegisterInfo(0x09, 2, True, False, "Minimum angle limit"),
    Register.MAX_ANGLE_LIMIT: RegisterInfo(0x0B, 2, True, False, "Maximum angle limit"),
    Register.MAX_TEMP_LIMIT: RegisterInfo(0x0D, 1, True, False, "Max temperature limit"),
    Register.TORQUE_LIMIT_EEPROM: RegisterInfo(0x10, 2, True, False, "EEPROM torque limit"),
    Register.CW_INSENSITIVE: RegisterInfo(0x1A, 1, True, False, "CW deadband (steps)"),
    Register.CCW_INSENSITIVE: RegisterInfo(0x1B, 1, True, False, "CCW deadband (steps)"),
    Register.MODE: RegisterInfo(0x21, 1, True, False, "Operating mode"),
    Register.EEPROM_LOCK: RegisterInfo(0x22, 1, True, False, "EEPROM lock"),
    Register.TORQUE_ENABLE: RegisterInfo(0x28, 1, True, False, "Torque enable"),
    Register.ACCELERATION: RegisterInfo(0x29, 1, True, False, "Acceleration"),
    Register.TARGET_POSITION: RegisterInfo(0x2A, 2, True, False, "Target position"),
    Register.MOVE_TIME: RegisterInfo(0x2C, 2, True, False, "Move time (ms)"),
    Register.MOVE_SPEED: RegisterInfo(0x2E, 2, True, False, "Move speed"),
    Register.TORQUE_LIMIT: RegisterInfo(0x30, 2, True, False, "Torque limit"),
    Register.PRESENT_POSITION: RegisterInfo(0x38, 2, False, False, "Current position"),
    Register.PRESENT_SPEED: RegisterInfo(0x3A, 2, False, True, "Current speed"),
    Register.PRESENT_LOAD: RegisterInfo(0x3C, 2, False, True, "Current load"),
    Register.PRESENT_VOLTAGE: RegisterInfo(0x3E, 1, False, False, "Voltage (0.1V)"),
    Register.PRESENT_TEMP: RegisterInfo(0x3F, 1, False, False, "Temperature (C)"),
    Register.STATUS: RegisterInfo(0x41, 1, False, False, "Status flags"),
    Register.MOVING: RegisterInfo(0x42, 1, False, False, "Moving flag"),
    Register.PRESENT_CURRENT: RegisterInfo(0x45, 2, False, False, "Current (6.5mA units)"),
}


def get_register_size(register: Register) -> int:
    """Get the size in bytes for a register."""
    if register in REGISTER_INFO:
        return REGISTER_INFO[register].size
    return 1  # Default to 1 byte


def is_register_writable(register: Register) -> bool:
    """Check if a register is writable."""
    if register in REGISTER_INFO:
        return REGISTER_INFO[register].writable
    return False
