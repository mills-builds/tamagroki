#!/usr/bin/env python3
"""Continuous serial capture for the Tamagroki cube without resetting it (needs pyserial).
usage: python3 serial_log.py /dev/cu.usbmodemXXXX [out.log]
DTR/RTS are forced low *before* opening: on the ESP32-S3 USB-Serial-JTAG,
toggling them resets the chip or holds it in download mode."""
import sys, time, serial
if len(sys.argv) < 2:
    sys.exit(__doc__)
port = sys.argv[1]
out = open(sys.argv[2] if len(sys.argv) > 2 else "tamagroki-serial.log", "a", buffering=1)
while True:
    try:
        s = serial.Serial()
        s.port, s.baudrate, s.timeout = port, 115200, 0.2
        s.dtr = False; s.rts = False
        s.open()
        print(f"--- opened {port}", file=sys.stderr)
        buf = b""
        while True:
            buf += s.read(4096)
            *lines, buf = buf.split(b"\n")
            for l in lines:
                t = time.strftime("%H:%M:%S")
                txt = l.decode(errors="replace").rstrip("\r")
                print(f"{t} {txt}"); out.write(f"{t} {txt}\n")
    except (serial.SerialException, OSError) as e:
        print(f"--- {e}; retrying", file=sys.stderr); time.sleep(1)
    except KeyboardInterrupt:
        break
