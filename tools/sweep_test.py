#!/usr/bin/env python3
"""Automated servo sweep test with comprehensive telemetry logging.

Systematically sweeps ALL servos simultaneously through a dense matrix of
speeds, ranges, and directions while logging raw + decoded + unwrapped
telemetry to CSV. Designed to run overnight and identify the cause of
brief direction reversals.

All 3 servos (u, v, w) execute each test permutation in parallel,
reducing total runtime by ~3x compared to sequential testing.

Usage:
    python3 tools/sweep_test.py                      # Full overnight run
    python3 tools/sweep_test.py --servo u             # Single servo
    python3 tools/sweep_test.py --quick               # Smoke test (5 tests)
    python3 tools/sweep_test.py --port /dev/ttyACM0   # Explicit port
    python3 tools/sweep_test.py --start-from 42       # Resume from test #42
    python3 tools/sweep_test.py --output results.csv  # Custom output path
"""

import sys
import os
import csv
import time
import signal
import argparse
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple

# Add project root to path so we can import spirob modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from spirob.bus import ThreadSafeSerialPort, BusAdapter, PortDiscovery
from spirob.bus.bus_adapter import _sm_decode, _sm_encode
from spirob.protocol.registers import Register
from spirob.protocol.constants import POSITION_MIN, POSITION_MAX
from spirob.utils.conversions import (
    steps_to_degrees, degrees_to_steps, speed_dps_to_raw
)

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger('sweep_test')
logger.setLevel(logging.INFO)

# --- Constants ---

MAX_SPEED_DPS = 360.0
MAX_RANGE_DEG = 2292.0
STEPS_PER_REV = 4096
HALF_REV = 2048
QUARTER_REV = 1024

SERVO_MAP = {'u': 1, 'v': 2, 'w': 3}

SPEED_PERCENTS = [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 80, 90, 100]
RANGE_PERCENTS = [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]

CYCLES_PER_TEST = 3
POLL_RATE_HZ = 50
POLL_PERIOD = 1.0 / POLL_RATE_HZ

# Settle detection: speed below this for N consecutive readings
SETTLE_SPEED_THRESHOLD = 5  # steps/s
SETTLE_COUNT = 5
MOVE_TIMEOUT_S = 60.0

CSV_HEADER = [
    'timestamp_ms', 'elapsed_ms', 'test_num', 'total_tests',
    'servo_id', 'servo_label', 'test_speed_dps', 'test_range_deg',
    'cycle_num', 'phase', 'commanded_deg', 'commanded_steps',
    'raw_pos_bytes', 'raw_spd_bytes', 'raw_load_bytes',
    'decoded_position', 'decoded_speed', 'decoded_load',
    'unwrapped_position', 'unwrapped_deg',
    'turn_count', 'voltage_raw', 'temperature', 'error_flags',
    'delta_steps', 'prev_delta_steps', 'direction_change',
]

# --- Graceful shutdown ---

_shutdown_requested = False


def _signal_handler(sig, frame):
    global _shutdown_requested
    _shutdown_requested = True
    print('\n\u26a0 Ctrl+C \u2014 shutting down gracefully...')


signal.signal(signal.SIGINT, _signal_handler)


# --- SweepLogger ---

class SweepLogger:
    """CSV logger for sweep test telemetry."""

    def __init__(self, csv_path: str):
        self._file = open(csv_path, 'w', newline='')
        self._writer = csv.DictWriter(self._file, fieldnames=CSV_HEADER)
        self._writer.writeheader()
        self._row_count = 0

    def log_row(self, **kwargs):
        self._writer.writerow(kwargs)
        self._row_count += 1
        # Flush periodically to avoid data loss on crash
        if self._row_count % 500 == 0:
            self._file.flush()

    @property
    def row_count(self) -> int:
        return self._row_count

    def close(self):
        self._file.flush()
        self._file.close()


# --- ServoSweeper ---

class ServoSweeper:
    """Manages sweep tests for a single servo with raw telemetry capture."""

    def __init__(self, adapter: BusAdapter, servo_id: int, label: str):
        self._adapter = adapter
        self._servo_id = servo_id
        self._label = label
        self._prev_raw_pos: Optional[int] = None
        self._turn_count: int = 0
        self._prev_unwrapped: Optional[int] = None
        self._prev_delta: int = 0
        self._settle_counter: int = 0
        self._glitch_count: int = 0

    @property
    def servo_id(self) -> int:
        return self._servo_id

    @property
    def label(self) -> str:
        return self._label

    @property
    def glitch_count(self) -> int:
        return self._glitch_count

    def reset_unwrap(self):
        """Reset position unwrapping and tracking state."""
        self._prev_raw_pos = None
        self._turn_count = 0
        self._prev_unwrapped = None
        self._prev_delta = 0
        self._settle_counter = 0
        self._glitch_count = 0

    def is_settled(self) -> bool:
        """Check if servo has settled (speed below threshold for N readings)."""
        return self._settle_counter >= SETTLE_COUNT

    def read_and_log(self, logger: SweepLogger, test_num: int,
                     total_tests: int, speed_dps: float, range_deg: float,
                     cycle: int, phase: str, target_deg: float,
                     commanded_steps: int, start_time: float) -> Optional[bool]:
        """Read telemetry, log to CSV, return direction_change or None on failure.

        Returns:
            True if direction change detected, False if not, None on read failure.
        """
        data = self._adapter.read_register(
            self._servo_id, Register.PRESENT_POSITION, 8
        )
        if not data or len(data) < 8:
            return None

        elapsed_total = time.time() - start_time

        # Raw bytes (for CSV hex logging)
        raw_pos_bytes = data[0:2].hex()
        raw_spd_bytes = data[2:4].hex()
        raw_load_bytes = data[4:6].hex()

        # Raw 16-bit words (little-endian)
        raw_pos_word = int.from_bytes(data[0:2], 'little')
        raw_spd_word = int.from_bytes(data[2:4], 'little')
        raw_load_word = int.from_bytes(data[4:6], 'little')

        # Sign-magnitude decode
        decoded_pos = _sm_decode(raw_pos_word, sign_bit=15)
        decoded_spd = _sm_decode(raw_spd_word, sign_bit=15)
        decoded_load = _sm_decode(raw_load_word, sign_bit=10)

        # Unwrap position (two-tier: standard + speed-validated)
        if self._prev_raw_pos is not None:
            delta = decoded_pos - self._prev_raw_pos
            if delta > HALF_REV:
                self._turn_count -= 1
            elif delta < -HALF_REV:
                self._turn_count += 1
            elif abs(delta) > QUARTER_REV and abs(decoded_spd) > 50:
                if delta < 0 and decoded_spd > 0:
                    self._turn_count += 1
                elif delta > 0 and decoded_spd < 0:
                    self._turn_count -= 1

        self._prev_raw_pos = decoded_pos
        unwrapped_pos = decoded_pos + (self._turn_count * STEPS_PER_REV)
        unwrapped_deg = steps_to_degrees(unwrapped_pos)

        # Direction change detection
        delta_steps = 0
        direction_change = False
        if self._prev_unwrapped is not None:
            delta_steps = unwrapped_pos - self._prev_unwrapped
            # Only flag if both deltas are non-trivial (>2 steps)
            if (self._prev_delta * delta_steps < 0
                    and abs(delta_steps) > 2
                    and abs(self._prev_delta) > 2):
                direction_change = True
                self._glitch_count += 1

        logger.log_row(
            timestamp_ms=int(time.time() * 1000),
            elapsed_ms=int(elapsed_total * 1000),
            test_num=test_num,
            total_tests=total_tests,
            servo_id=self._servo_id,
            servo_label=self._label,
            test_speed_dps=speed_dps,
            test_range_deg=range_deg,
            cycle_num=cycle,
            phase=phase,
            commanded_deg=target_deg,
            commanded_steps=commanded_steps,
            raw_pos_bytes=raw_pos_bytes,
            raw_spd_bytes=raw_spd_bytes,
            raw_load_bytes=raw_load_bytes,
            decoded_position=decoded_pos,
            decoded_speed=decoded_spd,
            decoded_load=decoded_load,
            unwrapped_position=unwrapped_pos,
            unwrapped_deg=f"{unwrapped_deg:.2f}",
            turn_count=self._turn_count,
            voltage_raw=data[6],
            temperature=data[7],
            error_flags=0,
            delta_steps=delta_steps,
            prev_delta_steps=self._prev_delta,
            direction_change=direction_change,
        )

        if self._prev_unwrapped is not None and delta_steps != 0:
            self._prev_delta = delta_steps
        self._prev_unwrapped = unwrapped_pos

        # Settle detection
        if abs(decoded_spd) < SETTLE_SPEED_THRESHOLD:
            self._settle_counter += 1
        else:
            self._settle_counter = 0

        return direction_change

    def reset_settle(self):
        """Reset settle counter for a new move."""
        self._settle_counter = 0


def move_all(adapter: BusAdapter, sweepers: List[ServoSweeper],
             target_deg: float, speed_dps: float):
    """Send position command to all servos."""
    steps = degrees_to_steps(target_deg)
    steps = max(POSITION_MIN, min(POSITION_MAX, steps))
    raw_speed = speed_dps_to_raw(speed_dps) if speed_dps > 0 else 0
    for sweeper in sweepers:
        adapter.write_position(sweeper.servo_id, steps, time_ms=0, speed=raw_speed)


def poll_all_and_log(sweepers: List[ServoSweeper], logger: SweepLogger,
                     test_num: int, total_tests: int, speed_dps: float,
                     range_deg: float, cycle: int, phase: str,
                     target_deg: float, commanded_steps: int,
                     start_time: float):
    """Read telemetry from all servos (sequential reads) and log each."""
    for sweeper in sweepers:
        sweeper.read_and_log(
            logger, test_num, total_tests, speed_dps, range_deg,
            cycle, phase, target_deg, commanded_steps, start_time,
        )


def all_settled(sweepers: List[ServoSweeper]) -> bool:
    """Check if all servos have settled."""
    return all(s.is_settled() for s in sweepers)


# --- Test Matrix ---

def build_test_matrix(
    speed_percents: List[int] = SPEED_PERCENTS,
    range_percents: List[int] = RANGE_PERCENTS,
) -> List[Tuple[float, float]]:
    """Build permutation matrix of (speed_dps, range_deg) pairs.

    All servos run each permutation simultaneously, so the matrix
    is independent of which/how many servos are being tested.

    Returns list of (speed_dps, range_deg) tuples.
    Ordered: all speeds for range[0], then range[1], etc.
    """
    matrix = []
    for rp in range_percents:
        range_deg = round(MAX_RANGE_DEG * rp / 100.0, 1)
        for sp in speed_percents:
            speed_dps = round(MAX_SPEED_DPS * sp / 100.0, 1)
            matrix.append((speed_dps, range_deg))
    return matrix


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description='Automated servo sweep test with telemetry logging'
    )
    parser.add_argument(
        '--port', default=None,
        help='Serial port (default: auto-discover)'
    )
    parser.add_argument(
        '--servo', default=None, choices=['u', 'v', 'w'],
        help='Test single servo only (default: all 3 in parallel)'
    )
    parser.add_argument(
        '--quick', action='store_true',
        help='Quick smoke test (5 permutations only)'
    )
    parser.add_argument(
        '--start-from', type=int, default=1, dest='start_from',
        help='Resume from test number N'
    )
    parser.add_argument(
        '--output', default=None,
        help='CSV output path (default: sweep_YYYYMMDD_HHMMSS.csv)'
    )
    parser.add_argument(
        '--baud', type=int, default=1000000,
        help='Baud rate (default: 1000000)'
    )

    args = parser.parse_args()

    # Resolve output path
    if args.output:
        csv_path = args.output
    else:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_path = f'sweep_{ts}.csv'

    # Discover or use specified port
    port_path = args.port
    if not port_path:
        print('Discovering serial port...')
        port_path = PortDiscovery().discover()
        if not port_path:
            print('ERROR: No servo bus port found. Use --port to specify.')
            sys.exit(1)

    # Determine which servos to test
    if args.servo:
        servos = {args.servo: SERVO_MAP[args.servo]}
    else:
        servos = dict(SERVO_MAP)

    # Build test matrix (speed/range pairs, servo-independent)
    matrix = build_test_matrix()
    if args.quick:
        matrix = matrix[:5]

    total_tests = len(matrix)
    servo_count = len(servos)
    servo_desc = ", ".join(f"{k}({v})" for k, v in sorted(servos.items()))

    # Connect
    print(f'\n{"=" * 60}')
    print(f'  Spirob Servo Sweep Test (Parallel Mode)')
    print(f'{"=" * 60}')
    print(f'Port:    {port_path} @ {args.baud} baud')
    print(f'Servos:  {servo_desc} ({"all parallel" if servo_count > 1 else "single"})')
    print(f'Tests:   {total_tests} permutations, {CYCLES_PER_TEST} cycles each')
    print(f'Output:  {csv_path}')

    # Estimate runtime (~15s avg per test, all servos at once)
    est_seconds = total_tests * 15
    est_hours = est_seconds / 3600
    print(f'Est:     ~{est_hours:.1f} hours')
    print(f'{"=" * 60}\n')

    serial_port = ThreadSafeSerialPort(port_path, baudrate=args.baud)
    if not serial_port.open():
        print(f'ERROR: Failed to open {port_path}')
        sys.exit(1)

    adapter = BusAdapter(serial_port)

    # Verify servos respond
    for label, servo_id in sorted(servos.items()):
        if not adapter.ping(servo_id):
            print(f'ERROR: Servo {label} (ID={servo_id}) not responding')
            serial_port.close()
            sys.exit(1)
        print(f'  Servo {label} (ID={servo_id}): OK')

    # Configure multi-turn on all test servos
    for label, servo_id in sorted(servos.items()):
        adapter.configure_multi_turn(servo_id)

    # Enable torque
    for label, servo_id in sorted(servos.items()):
        adapter.set_torque_enable(servo_id, True)

    # Create sweepers for all servos
    sweepers = [
        ServoSweeper(adapter, servo_id, label)
        for label, servo_id in sorted(servos.items())
    ]

    print()

    # Open logger
    csv_logger = SweepLogger(csv_path)
    start_time = time.time()
    total_glitches = 0
    worst_test = (0, '', 0)  # (glitches, description, test_num)
    tests_completed = 0

    try:
        for i, (speed_dps, range_deg) in enumerate(matrix, 1):
            if _shutdown_requested:
                break

            # Skip if resuming
            if i < args.start_from:
                continue

            desc = f'\u00b1{range_deg:.0f}\u00b0 @ {speed_dps:.0f}dps'
            servo_labels = ','.join(s.label for s in sweepers)
            print(
                f'[{i:>4}/{total_tests}] [{servo_labels}] {desc} \u2014 cycle ',
                end='', flush=True
            )

            # Reset state for all sweepers
            for sweeper in sweepers:
                sweeper.reset_unwrap()

            # Move all servos to start position (0)
            move_all(adapter, sweepers, 0.0, MAX_SPEED_DPS)
            time.sleep(0.5)

            # Run sweep cycles
            commanded_steps = 0
            test_glitches = 0

            for cycle in range(1, CYCLES_PER_TEST + 1):
                if _shutdown_requested:
                    break

                # Targets: +range, -range; on last cycle also return to 0
                targets = [
                    (range_deg, 'moving_positive'),
                    (-range_deg, 'moving_negative'),
                ]
                if cycle == CYCLES_PER_TEST:
                    targets.append((0.0, 'returning'))

                for target_deg, phase in targets:
                    if _shutdown_requested:
                        break

                    commanded_steps = degrees_to_steps(target_deg)

                    # Reset settle counters for all servos
                    for sweeper in sweepers:
                        sweeper.reset_settle()

                    # Command all servos simultaneously
                    move_all(adapter, sweepers, target_deg, speed_dps)

                    # Poll all servos until ALL have settled
                    move_start = time.time()

                    while not _shutdown_requested:
                        poll_start = time.time()

                        # Read and log telemetry for all servos
                        poll_all_and_log(
                            sweepers, csv_logger, i, total_tests,
                            speed_dps, range_deg, cycle, phase,
                            target_deg, commanded_steps, start_time,
                        )

                        # Check if all servos settled
                        if all_settled(sweepers):
                            break

                        # Timeout
                        if time.time() - move_start > MOVE_TIMEOUT_S:
                            # Log timeout for each servo
                            elapsed_total = time.time() - start_time
                            for sweeper in sweepers:
                                csv_logger.log_row(
                                    timestamp_ms=int(time.time() * 1000),
                                    elapsed_ms=int(elapsed_total * 1000),
                                    test_num=i, total_tests=total_tests,
                                    servo_id=sweeper.servo_id,
                                    servo_label=sweeper.label,
                                    test_speed_dps=speed_dps,
                                    test_range_deg=range_deg,
                                    cycle_num=cycle, phase='timeout',
                                    commanded_deg=target_deg,
                                    commanded_steps=commanded_steps,
                                    raw_pos_bytes='', raw_spd_bytes='',
                                    raw_load_bytes='',
                                    decoded_position=0, decoded_speed=0,
                                    decoded_load=0,
                                    unwrapped_position=0, unwrapped_deg='0',
                                    turn_count=0, voltage_raw=0,
                                    temperature=0, error_flags=0,
                                    delta_steps=0, prev_delta_steps=0,
                                    direction_change=False,
                                )
                            break

                        # Sleep to maintain poll rate
                        elapsed_poll = time.time() - poll_start
                        sleep_time = max(0, POLL_PERIOD - elapsed_poll)
                        if sleep_time > 0:
                            time.sleep(sleep_time)

                # Print cycle progress
                print(f'{cycle}/{CYCLES_PER_TEST}...', end='', flush=True)

            # Tally glitches across all servos for this test
            for sweeper in sweepers:
                test_glitches += sweeper.glitch_count

            total_glitches += test_glitches
            tests_completed += 1

            elapsed = time.time() - start_time
            symbol = '\u2713' if test_glitches == 0 else '\u26a0'

            # Show per-servo breakdown if multiple servos
            if len(sweepers) > 1:
                per_servo = ' '.join(
                    f'{s.label}:{s.glitch_count}' for s in sweepers
                )
                print(f' {symbol} {test_glitches} glitches [{per_servo}] ({elapsed:.0f}s)')
            else:
                print(f' {symbol} {test_glitches} glitches ({elapsed:.0f}s)')

            if test_glitches > worst_test[0]:
                worst_test = (test_glitches, desc, i)

    except Exception as e:
        print(f'\nERROR: {e}')
        import traceback
        traceback.print_exc()

    finally:
        # Always disable torque and close cleanly
        print('\nDisabling torque on all servos...')
        for label, servo_id in sorted(servos.items()):
            try:
                adapter.set_torque_enable(servo_id, False)
            except Exception:
                pass

        csv_logger.close()
        serial_port.close()

    # Summary
    runtime = time.time() - start_time
    hours = int(runtime // 3600)
    minutes = int((runtime % 3600) // 60)

    print(f'\n{"=" * 60}')
    print(f'  SUMMARY')
    print(f'{"=" * 60}')
    print(f'Tests completed: {tests_completed}/{total_tests}')
    print(f'Servos tested:   {servo_desc} (parallel)')
    print(f'Total glitches:  {total_glitches}')
    if worst_test[0] > 0:
        print(f'Worst test:      #{worst_test[2]} ({worst_test[1]}) \u2014 {worst_test[0]} direction changes')
    else:
        print(f'Worst test:      none (0 glitches)')
    print(f'CSV rows:        {csv_logger.row_count:,}')
    print(f'Output:          {csv_path}')
    print(f'Runtime:         {hours}h {minutes}m')
    print(f'{"=" * 60}')


if __name__ == '__main__':
    main()
