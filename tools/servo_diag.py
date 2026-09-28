#!/usr/bin/env python3
"""Servo diagnostic and ID programming tool.

Uses correct STS register addresses per official STServo SDK:
  SMS_STS_LOCK = 55 (not 0x22 as in spirob registers.py)
  SMS_STS_ID = 5

Usage:
  servo_diag.py                  # Scan for servos
  servo_diag.py --set-id NEW_ID  # Set the single connected servo to NEW_ID
  servo_diag.py --check-lock     # Read lock register state
"""

import sys
import time
import serial

# Correct STS register addresses (from official STServo SDK sms_sts.py)
STS_ID = 5
STS_LOCK = 55  # Correct EEPROM lock register for STS series

HEADER = bytes([0xFF, 0xFF])
INST_PING = 0x01
INST_READ = 0x02
INST_WRITE = 0x03

PORT = '/dev/ttyACM0'
BAUD = 1000000
TIMEOUT = 0.1


def checksum(data: bytes) -> int:
    return (~sum(data)) & 0xFF


def build_ping(servo_id: int) -> bytes:
    length = 2  # instruction + checksum
    pkt = bytes([servo_id, length, INST_PING])
    return HEADER + pkt + bytes([checksum(pkt)])


def build_read(servo_id: int, address: int, read_len: int) -> bytes:
    length = 4  # instruction + address + read_len + checksum
    pkt = bytes([servo_id, length, INST_READ, address, read_len])
    return HEADER + pkt + bytes([checksum(pkt)])


def build_write(servo_id: int, address: int, data: bytes) -> bytes:
    length = 3 + len(data)  # instruction + address + data + checksum
    pkt = bytes([servo_id, length, INST_WRITE, address]) + data
    return HEADER + pkt + bytes([checksum(pkt)])


def transact(ser: serial.Serial, packet: bytes, expected: int) -> bytes:
    ser.reset_input_buffer()
    ser.write(packet)
    ser.flush()
    time.sleep(0.01)
    return ser.read(expected)


def ping(ser: serial.Serial, servo_id: int) -> bool:
    resp = transact(ser, build_ping(servo_id), 6)
    if len(resp) >= 6 and resp[0] == 0xFF and resp[1] == 0xFF and resp[2] == servo_id:
        return True
    return False


def read_register(ser: serial.Serial, servo_id: int, address: int, length: int) -> bytes:
    expected = 6 + length
    resp = transact(ser, build_read(servo_id, address, length), expected)
    if len(resp) >= expected and resp[0] == 0xFF and resp[1] == 0xFF:
        return resp[5:5+length]
    return b''


def write_register(ser: serial.Serial, servo_id: int, address: int, data: bytes) -> bool:
    resp = transact(ser, build_write(servo_id, address, data), 6)
    if len(resp) >= 6 and resp[0] == 0xFF and resp[1] == 0xFF and resp[2] == servo_id:
        error = resp[4]
        if error != 0:
            print(f"  Write error flags: {error:#04x}")
        return True
    return False


def unlock_eeprom(ser: serial.Serial, servo_id: int) -> bool:
    """Unlock EEPROM using correct STS register 55."""
    print(f"  Unlocking EEPROM (register {STS_LOCK}) for ID {servo_id}...")
    return write_register(ser, servo_id, STS_LOCK, bytes([0]))


def lock_eeprom(ser: serial.Serial, servo_id: int) -> bool:
    """Lock EEPROM using correct STS register 55."""
    print(f"  Locking EEPROM (register {STS_LOCK}) for ID {servo_id}...")
    return write_register(ser, servo_id, STS_LOCK, bytes([1]))


def read_id(ser: serial.Serial, servo_id: int) -> int:
    """Read the ID register from a servo."""
    data = read_register(ser, servo_id, STS_ID, 1)
    if data:
        return data[0]
    return -1


def set_id(ser: serial.Serial, old_id: int, new_id: int) -> bool:
    """Change servo ID using correct EEPROM lock register."""
    print(f"\n--- Changing ID {old_id} -> {new_id} ---")

    if not unlock_eeprom(ser, old_id):
        print("  FAILED to unlock EEPROM!")
        return False
    time.sleep(0.05)

    print(f"  Writing new ID {new_id} to register {STS_ID}...")
    if not write_register(ser, old_id, STS_ID, bytes([new_id])):
        print("  FAILED to write new ID!")
        return False
    time.sleep(0.05)

    if not lock_eeprom(ser, new_id):
        print("  WARNING: Failed to lock EEPROM (servo may already be at new ID)")
    time.sleep(0.05)

    # Verify
    if ping(ser, new_id):
        stored_id = read_id(ser, new_id)
        print(f"  SUCCESS: Servo responds at ID {new_id} (stored ID register = {stored_id})")
        return True
    else:
        print(f"  FAILED: Servo does not respond at new ID {new_id}")
        return False


def scan(ser: serial.Serial) -> list:
    """Scan for servos on the bus."""
    print("--- Scanning for servos ---")
    found = []
    for sid in range(0, 10):
        if ping(ser, sid):
            stored = read_id(ser, sid)
            print(f"  ID {sid}: RESPONDS (stored ID register = {stored})")
            found.append(sid)
        else:
            if sid <= 3:
                print(f"  ID {sid}: no response")

    if not found:
        print("\nNo servos found! Check power and connections.")
    else:
        print(f"\nFound {len(found)} servo(s): {found}")

    return found


def main():
    print(f"=== Servo Diagnostic Tool ===")
    print(f"Port: {PORT} @ {BAUD} baud")
    print(f"Using STS LOCK register = {STS_LOCK} (correct for ST3215)")
    print()

    try:
        ser = serial.Serial(PORT, BAUD, timeout=TIMEOUT)
        ser.setRTS(False)
        ser.setDTR(False)
        time.sleep(0.1)
    except serial.SerialException as e:
        print(f"Failed to open {PORT}: {e}")
        sys.exit(1)

    found = scan(ser)

    if len(sys.argv) > 1 and sys.argv[1] == '--set-id':
        if len(sys.argv) < 3:
            print("Usage: servo_diag.py --set-id NEW_ID")
            ser.close()
            sys.exit(1)

        new_id = int(sys.argv[2])
        print(f"\n--- Programming single connected servo to ID {new_id} ---")

        if len(found) == 0:
            print("No servo found!")
        elif len(found) > 1:
            print(f"WARNING: Multiple servos found ({found}). Connect only ONE servo!")
        else:
            current_id = found[0]
            if current_id == new_id:
                print(f"Servo already at ID {new_id}, re-writing to EEPROM...")
            set_id(ser, current_id, new_id)

    elif len(sys.argv) > 1 and sys.argv[1] == '--check-lock':
        print("\n--- Checking EEPROM lock state ---")
        for sid in found:
            old_lock = read_register(ser, sid, 0x22, 1)
            new_lock = read_register(ser, sid, 55, 1)
            print(f"  ID {sid}: reg[0x22]={old_lock.hex() if old_lock else 'N/A'}, "
                  f"reg[55]={new_lock.hex() if new_lock else 'N/A'}")

    ser.close()
    print("\nDone.")


if __name__ == '__main__':
    main()
