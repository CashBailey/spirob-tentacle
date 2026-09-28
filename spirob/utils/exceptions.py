"""Custom exceptions for spirob servo control."""


class SpirobError(Exception):
    """Base exception for all spirob errors."""
    pass


class CommunicationError(SpirobError):
    """Error in serial/bus communication."""

    def __init__(self, message: str, servo_id: int = None):
        self.servo_id = servo_id
        super().__init__(message)


class ServoTimeoutError(CommunicationError):
    """Communication timeout waiting for response."""
    pass


class ChecksumError(CommunicationError):
    """Checksum validation failed on received packet."""
    pass


class ServoError(SpirobError):
    """Error reported by servo (via error flags)."""

    def __init__(self, message: str, servo_id: int, error_flags: int):
        self.servo_id = servo_id
        self.error_flags = error_flags
        super().__init__(message)


class VoltageError(ServoError):
    """Input voltage out of range."""
    pass


class OverheatError(ServoError):
    """Servo overheating detected."""
    pass


class OverloadError(ServoError):
    """Servo overload detected."""
    pass


class AngleLimitError(ServoError):
    """Angle limit exceeded."""
    pass


class ConfigurationError(SpirobError):
    """Invalid configuration or parameter."""
    pass


class ServoNotFoundError(SpirobError):
    """Servo with specified ID not found on bus."""

    def __init__(self, servo_id: int):
        self.servo_id = servo_id
        super().__init__(f"Servo ID {servo_id} not found on bus")


class PortError(SpirobError):
    """Serial port error (open, close, permission)."""
    pass
