"""Thread-safe serial port wrapper for servo bus communication."""

import serial
import threading
import time
from typing import Optional
import logging

from spirob.utils.exceptions import PortError, ServoTimeoutError

logger = logging.getLogger(__name__)


class ThreadSafeSerialPort:
    """Thread-safe wrapper around pyserial for concurrent bus access.

    Uses a reentrant lock to ensure only one transaction occurs at a time.
    This prevents interleaved reads/writes when multiple threads access the bus.
    """

    def __init__(self, port: str, baudrate: int = 1000000,
                 timeout: float = 0.05):
        """Initialize the serial port wrapper.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0')
            baudrate: Communication baud rate (default 1Mbps for ST/SC servos)
            timeout: Read timeout in seconds
        """
        self._port_path = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.RLock()
        self._is_open = False

    @property
    def port(self) -> str:
        """Get the serial port path."""
        return self._port_path

    @property
    def baudrate(self) -> int:
        """Get the baud rate."""
        return self._baudrate

    def is_open(self) -> bool:
        """Check if the serial port is open."""
        with self._lock:
            return self._is_open and self._serial is not None

    def open(self, retry_count: int = 3, retry_delay: float = 0.5) -> bool:
        """Open the serial port with retry logic.

        Args:
            retry_count: Number of open attempts before giving up
            retry_delay: Delay between retry attempts in seconds

        Returns:
            True if port opened successfully, False otherwise

        Raises:
            PortError: If port cannot be opened after all retries
        """
        with self._lock:
            if self._is_open:
                return True

            last_error = None
            for attempt in range(retry_count):
                try:
                    self._serial = serial.Serial(
                        port=self._port_path,
                        baudrate=self._baudrate,
                        timeout=self._timeout,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                    )
                    self._is_open = True
                    logger.info(f"Opened serial port {self._port_path} at {self._baudrate} baud")
                    return True
                except serial.SerialException as e:
                    last_error = e
                    logger.warning(f"Failed to open {self._port_path} (attempt {attempt+1}/{retry_count}): {e}")
                    if attempt < retry_count - 1:
                        time.sleep(retry_delay)

            raise PortError(f"Failed to open serial port {self._port_path}: {last_error}")

    def close(self) -> None:
        """Close the serial port."""
        with self._lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                    logger.info(f"Closed serial port {self._port_path}")
                except (serial.SerialException, OSError) as e:
                    logger.warning(f"Error closing serial port: {e}")
                finally:
                    self._serial = None
                    self._is_open = False

    def flush(self) -> None:
        """Flush input and output buffers."""
        with self._lock:
            if self._serial is not None:
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()

    def transact(self, tx_data: bytes, rx_length: int,
                 timeout: Optional[float] = None) -> bytes:
        """Perform a thread-safe transaction: write then read.

        The lock is held for the entire transaction to prevent interleaved
        communication from other threads.

        Args:
            tx_data: Bytes to transmit
            rx_length: Expected number of bytes to receive
            timeout: Override default timeout for this transaction

        Returns:
            Received bytes (may be shorter than rx_length if timeout)

        Raises:
            PortError: If port is not open
            ServoTimeoutError: If no response received within timeout
        """
        with self._lock:
            if not self._is_open or self._serial is None:
                raise PortError("Serial port is not open")

            # Set timeout for this transaction
            old_timeout = self._serial.timeout
            if timeout is not None:
                self._serial.timeout = timeout

            try:
                # Clear any stale data in buffer
                self._serial.reset_input_buffer()

                # Send the packet
                self._serial.write(tx_data)
                self._serial.flush()

                # Read response
                rx_data = self._serial.read(rx_length)

                return rx_data

            finally:
                # Restore original timeout
                if timeout is not None:
                    self._serial.timeout = old_timeout

    def write(self, data: bytes) -> int:
        """Write data to serial port (thread-safe).

        Args:
            data: Bytes to write

        Returns:
            Number of bytes written
        """
        with self._lock:
            if not self._is_open or self._serial is None:
                raise PortError("Serial port is not open")

            return self._serial.write(data)

    def read(self, size: int, timeout: Optional[float] = None) -> bytes:
        """Read data from serial port (thread-safe).

        Args:
            size: Maximum number of bytes to read
            timeout: Override default timeout

        Returns:
            Bytes read (may be fewer than size if timeout)
        """
        with self._lock:
            if not self._is_open or self._serial is None:
                raise PortError("Serial port is not open")

            old_timeout = self._serial.timeout
            if timeout is not None:
                self._serial.timeout = timeout

            try:
                return self._serial.read(size)
            finally:
                if timeout is not None:
                    self._serial.timeout = old_timeout

    def in_waiting(self) -> int:
        """Get number of bytes waiting in input buffer."""
        with self._lock:
            if not self._is_open or self._serial is None:
                return 0
            return self._serial.in_waiting

    def __enter__(self):
        """Context manager entry - opens port."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes port."""
        self.close()
        return False
