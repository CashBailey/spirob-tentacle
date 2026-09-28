"""Auto-discovery for servo bus serial ports.

Scans available USB serial ports and attempts to identify
Waveshare ST/SC servo controllers by sending a ping command.
"""

import glob
import logging
import serial
import serial.tools.list_ports
from typing import List, Optional, Tuple

from spirob.protocol.constants import Instruction
from spirob.protocol.packet import PacketBuilder, PacketParser

logger = logging.getLogger(__name__)


class PortDiscovery:
    """Discovers and identifies servo bus serial ports."""

    # Common USB serial port patterns by platform
    PORT_PATTERNS = [
        '/dev/ttyUSB*',      # Linux USB-Serial
        '/dev/ttyACM*',      # Linux Arduino/CDC
        '/dev/serial/by-id/*',  # Linux persistent names
        '/dev/cu.usbserial*',   # macOS USB-Serial
        '/dev/cu.usbmodem*',    # macOS USB-Modem
        'COM*',              # Windows
    ]

    # Baud rates to try (in order of preference)
    BAUD_RATES = [1000000, 500000, 115200]

    # Known servo bus controller USB identifiers (VID, PID)
    KNOWN_DEVICES = [
        (0x1A86, 0x55D3),  # QinHeng CH340 - WaveShare ST/SC servo bus
    ]

    # Servo IDs to try when scanning
    SCAN_IDS = [1, 2, 3, 254]  # Common IDs + broadcast

    def __init__(self):
        """Initialize port discovery."""
        self._found_port: Optional[str] = None
        self._found_baud: int = 1000000

    @property
    def found_port(self) -> Optional[str]:
        """Get the discovered port path."""
        return self._found_port

    @property
    def found_baud(self) -> int:
        """Get the discovered baud rate."""
        return self._found_baud

    def list_serial_ports(self) -> List[str]:
        """List all available serial ports.

        Returns:
            List of port paths
        """
        ports = []

        # Use pyserial's port enumeration
        for port_info in serial.tools.list_ports.comports():
            ports.append(port_info.device)

        # Also try glob patterns for any missed ports
        for pattern in self.PORT_PATTERNS:
            ports.extend(glob.glob(pattern))

        # Remove duplicates while preserving order
        seen = set()
        unique_ports = []
        for port in ports:
            if port not in seen:
                seen.add(port)
                unique_ports.append(port)

        return unique_ports

    def get_port_info(self, port: str) -> dict:
        """Get detailed info about a serial port.

        Args:
            port: Port path

        Returns:
            Dict with port information
        """
        for port_info in serial.tools.list_ports.comports():
            if port_info.device == port:
                return {
                    'device': port_info.device,
                    'name': port_info.name,
                    'description': port_info.description,
                    'hwid': port_info.hwid,
                    'vid': port_info.vid,
                    'pid': port_info.pid,
                    'serial_number': port_info.serial_number,
                    'manufacturer': port_info.manufacturer,
                    'product': port_info.product,
                }
        return {'device': port}

    def find_by_vid_pid(self) -> Optional[str]:
        """Find a servo bus port by matching known USB VID/PID pairs.

        Fallback for when PING probing fails (e.g., servos not powered).

        Returns:
            Port path if a known device is found, None otherwise
        """
        for port_info in serial.tools.list_ports.comports():
            if port_info.vid is not None and port_info.pid is not None:
                for known_vid, known_pid in self.KNOWN_DEVICES:
                    if port_info.vid == known_vid and port_info.pid == known_pid:
                        logger.info(
                            f"Identified servo bus controller by USB ID "
                            f"{port_info.vid:04X}:{port_info.pid:04X} "
                            f"on {port_info.device}"
                        )
                        return port_info.device
        return None

    def probe_port(self, port: str, baudrate: int = 1000000,
                   timeout: float = 0.1) -> Tuple[bool, List[int]]:
        """Probe a port to check if it has ST/SC servos.

        Sends PING commands to common servo IDs and checks for responses.

        Args:
            port: Serial port path
            baudrate: Baud rate to use
            timeout: Response timeout in seconds

        Returns:
            Tuple of (success, list of responding servo IDs)
        """
        found_ids = []

        try:
            with serial.Serial(port, baudrate, timeout=timeout) as ser:
                ser.reset_input_buffer()

                for servo_id in self.SCAN_IDS:
                    if servo_id == 254:  # Skip broadcast for probe
                        continue

                    # Build PING packet
                    packet = PacketBuilder.build_ping(servo_id)

                    # Send and wait for response
                    ser.reset_input_buffer()
                    ser.write(packet)
                    ser.flush()

                    # Read response (PING response is typically 6 bytes)
                    response = ser.read(6)

                    if len(response) >= 6:
                        # Verify it's a valid response
                        if response[0] == 0xFF and response[1] == 0xFF:
                            resp_id = response[2]
                            if resp_id == servo_id:
                                found_ids.append(servo_id)
                                logger.debug(f"Found servo ID {servo_id} on {port}")

        except serial.SerialException as e:
            logger.debug(f"Cannot open {port}: {e}")
            return False, []
        except OSError as e:
            logger.debug(f"Error probing {port}: {e}")
            return False, []

        return len(found_ids) > 0, found_ids

    def discover(self, preferred_baud: int = 1000000) -> Optional[str]:
        """Auto-discover the servo bus port.

        Scans all available serial ports and probes for servo responses.

        Args:
            preferred_baud: Preferred baud rate to try first

        Returns:
            Port path if found, None otherwise
        """
        ports = self.list_serial_ports()
        logger.info(f"Scanning {len(ports)} serial ports for servo bus...")

        # Order baud rates with preferred first
        baud_rates = [preferred_baud] + [b for b in self.BAUD_RATES if b != preferred_baud]

        for port in ports:
            port_info = self.get_port_info(port)
            logger.debug(f"Checking {port}: {port_info.get('description', 'unknown')}")

            for baud in baud_rates:
                success, servo_ids = self.probe_port(port, baud)

                if success:
                    logger.info(
                        f"Found servo bus on {port} at {baud} baud "
                        f"(servos: {servo_ids})"
                    )
                    self._found_port = port
                    self._found_baud = baud
                    return port

        # Fallback: identify controller by USB VID/PID
        logger.info("PING probe found no servos, trying USB VID/PID identification...")
        vid_pid_port = self.find_by_vid_pid()
        if vid_pid_port:
            logger.warning(
                f"Found servo controller by USB ID on {vid_pid_port} "
                f"(no servo responses - are servos powered?)"
            )
            self._found_port = vid_pid_port
            self._found_baud = preferred_baud
            return vid_pid_port

        logger.warning("No servo bus found by PING probe or USB VID/PID")
        return None

    def discover_or_default(self, default_port: str = '/dev/ttyUSB0',
                            default_baud: int = 1000000) -> Tuple[str, int]:
        """Discover servo bus or fall back to defaults.

        Args:
            default_port: Default port if discovery fails
            default_baud: Default baud rate

        Returns:
            Tuple of (port, baud_rate)
        """
        found = self.discover(default_baud)

        if found:
            return self._found_port, self._found_baud
        else:
            logger.info(f"Using default port: {default_port} at {default_baud} baud")
            return default_port, default_baud


def discover_servo_port(timeout: float = 0.1) -> Optional[str]:
    """Convenience function to discover servo port.

    Args:
        timeout: Probe timeout per port

    Returns:
        Port path if found, None otherwise
    """
    discovery = PortDiscovery()
    return discovery.discover()


def list_available_ports() -> List[dict]:
    """List all available serial ports with details.

    Returns:
        List of port info dicts
    """
    discovery = PortDiscovery()
    ports = discovery.list_serial_ports()
    return [discovery.get_port_info(p) for p in ports]
