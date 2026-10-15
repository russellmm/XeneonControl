"""NT68500 MCCS-over-USB framing recovered from MccsProtocols 5.52.93.

Only allowlisted display settings are exposed; no firmware/ISP/register commands.
"""
from functools import reduce
import operator
import threading
import time
from transport import UsbError


def checksum(data):
    return reduce(operator.xor, data, 0)


def packet(code, vendor=False, value=None):
    if not 0 <= code <= 255:
        raise ValueError("Feature code must be a byte")
    if value is not None and not 0 <= value <= 255:
        raise ValueError("Setting must be a byte")
    if value is None:
        body = [1, 0xFE, code] if vendor else [1, code]
    else:
        body = [3, 0xE0, code, value] if vendor else [3, code, 0, value]
    data = bytes([0x6E, 0x51, 0x80 | len(body)] + body)
    return data + bytes([checksum(data)])


def parse_reply(data, code, vendor=False):
    expected = 12 if vendor else 11
    if len(data) < expected or data[0] != 0x6E:
        raise UsbError("Invalid monitor reply")
    size = data[1] & 0x7F
    if size == 0:
        raise UsbError("Monitor busy")
    if size != expected - 3 or data[2] != 2 or data[3] != 0:
        raise UsbError("Unsupported setting or invalid monitor reply: " + data.hex(" "))
    if checksum(data[:expected]) != 0x50:
        raise UsbError("Monitor reply checksum mismatch")
    if vendor:
        if data[4:6] != bytes([0xFE, code]):
            raise UsbError("Monitor replied to a different setting")
    elif data[4] != code:
        raise UsbError("Monitor replied to a different setting")
    return data[expected - 2]


class Monitor:
    def __init__(self, usb):
        self.usb = usb
        self.lock = threading.RLock()
        self.next_request = 0.0

    def _pace(self):
        time.sleep(max(0.0, self.next_request - time.monotonic()))

    def get(self, code, vendor=False):
        with self.lock:
            last = None
            for attempt in range(3):
                self._pace()
                try:
                    self.usb.transfer(0x40, 0xB2, data=packet(code, vendor))
                    time.sleep(0.06)
                    reply = self.usb.transfer(0xC0, 0xA3, index=0x6F, length=12)
                    self.next_request = time.monotonic() + 0.05
                    return parse_reply(reply, code, vendor)
                except UsbError as exc:
                    last = exc
                    self.next_request = time.monotonic() + 0.2
            raise last

    def firmware_version(self):
        # Corsair's GetFirmwareVersions dispatch reads vendor C7 and builds
        # Version(major=0, minor=reply_byte). Match the OSD's two-digit minor.
        return "0.%02d" % self.get(0xC7, vendor=True)

    def set(self, setting, value):
        # Validation lives here as well as in the UI and CLI.
        setting.validate(value)
        with self.lock:
            self._pace()
            self.usb.transfer(0x40, 0xB2, data=packet(setting.code, setting.vendor, value))
            self.next_request = time.monotonic() + setting.settle_delay(value)

    def close(self):
        with self.lock:
            self.usb.close()
