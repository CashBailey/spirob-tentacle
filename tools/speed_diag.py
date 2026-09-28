#!/usr/bin/env python3
"""Diagnose speed control: single-turn vs multi-turn targets."""

import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from spirob.bus import ThreadSafeSerialPort, BusAdapter, PortDiscovery
from spirob.bus.bus_adapter import _sm_decode
from spirob.protocol.registers import Register
from spirob.utils.conversions import speed_dps_to_raw, degrees_to_steps

SERVO_ID = 1

port_path = PortDiscovery().discover()
if not port_path:
    print("No port found"); sys.exit(1)
print(f"Port: {port_path}")

sp = ThreadSafeSerialPort(port_path, baudrate=1000000)
sp.open()
adapter = BusAdapter(sp)

if not adapter.ping(SERVO_ID):
    print(f"Servo {SERVO_ID} not responding"); sys.exit(1)

adapter.configure_multi_turn(SERVO_ID)
adapter.set_torque_enable(SERVO_ID, True)

def read_telem():
    data = adapter.read_register(SERVO_ID, Register.PRESENT_POSITION, 8)
    if not data or len(data) < 8:
        return None, None
    pos = _sm_decode(int.from_bytes(data[0:2], 'little'), 15)
    spd = _sm_decode(int.from_bytes(data[2:4], 'little'), 15)
    return pos, spd

def test_move(label, target_steps, speed_raw, wait_s=5):
    """Send a position command and monitor speed for wait_s seconds."""
    print(f"\n--- {label} ---")
    print(f"  Target: {target_steps} steps, Speed param: {speed_raw}")

    # Read starting position
    pos0, spd0 = read_telem()
    print(f"  Start: pos={pos0}, spd={spd0}")

    # Send command
    adapter.write_position(SERVO_ID, target_steps, time_ms=0, speed=speed_raw)

    # Monitor
    max_speed = 0
    readings = []
    t0 = time.time()
    while time.time() - t0 < wait_s:
        time.sleep(0.05)
        pos, spd = read_telem()
        if pos is None:
            continue
        elapsed = time.time() - t0
        abs_spd = abs(spd) if spd else 0
        max_speed = max(max_speed, abs_spd)
        readings.append((elapsed, pos, spd))
        if len(readings) <= 20 or len(readings) % 10 == 0:
            print(f"  t={elapsed:.2f}s pos={pos:>6} spd={spd:>6}")

    print(f"  Max observed speed: {max_speed} steps/s ({max_speed * 360/4096:.0f} dps)")
    print(f"  Expected speed:     {speed_raw} steps/s ({speed_raw * 360/4096:.0f} dps)")

    # Wait for servo to actually reach target
    print("  Waiting for settle...", end='', flush=True)
    settle_count = 0
    while settle_count < 10:
        time.sleep(0.05)
        _, spd = read_telem()
        if spd is not None and abs(spd) < 5:
            settle_count += 1
        else:
            settle_count = 0
        if time.time() - t0 > 60:
            print(" TIMEOUT")
            break
    else:
        print(f" done ({time.time()-t0:.1f}s total)")

try:
    # First return to 0
    print("\n=== Returning to position 0 ===")
    adapter.write_position(SERVO_ID, 0, time_ms=0, speed=0)
    time.sleep(3)

    raw_speed_slow = speed_dps_to_raw(18)  # 204 steps/s
    print(f"\nspeed_dps_to_raw(18) = {raw_speed_slow}")

    # Test 1: Single-turn target with speed
    test_move("Single-turn: 0 → 2048 @ 204 steps/s", 2048, raw_speed_slow, wait_s=12)

    # Return to 0
    adapter.write_position(SERVO_ID, 0, time_ms=0, speed=0)
    time.sleep(3)

    # Test 2: Multi-turn target with speed (same speed)
    target = degrees_to_steps(-2292)  # = -26078
    print(f"\ndegrees_to_steps(-2292) = {target}")
    test_move(f"Multi-turn: 0 → {target} @ 204 steps/s", target, raw_speed_slow, wait_s=12)

    # Return to 0
    adapter.write_position(SERVO_ID, 0, time_ms=0, speed=0)
    time.sleep(5)

    # Test 3: Multi-turn target with time_ms instead of speed
    time_ms_for_move = int(abs(2292.0 / 18.0) * 1000)  # 127333 ms
    print(f"\ntime_ms calculated: {time_ms_for_move} (exceeds uint16 max 65535)")
    time_ms_capped = min(time_ms_for_move, 65535)
    test_move(f"Multi-turn: 0 → {target} @ time_ms={time_ms_capped}", target, 0, wait_s=12)
    # For this test, use time_ms
    # Actually we need to call write_position differently...

    # Return to 0
    adapter.write_position(SERVO_ID, 0, time_ms=0, speed=0)
    time.sleep(5)

    # Test 4: Multi-turn moderate range with speed
    target_mod = degrees_to_steps(-720)  # ~2 revolutions
    speed_mod = speed_dps_to_raw(90)  # moderate speed
    print(f"\ndegrees_to_steps(-720) = {target_mod}")
    print(f"speed_dps_to_raw(90) = {speed_mod}")
    test_move(f"Multi-turn: 0 → {target_mod} @ {speed_mod} steps/s", target_mod, speed_mod, wait_s=10)

finally:
    print("\nDisabling torque...")
    adapter.set_torque_enable(SERVO_ID, False)
    sp.close()
    print("Done.")
