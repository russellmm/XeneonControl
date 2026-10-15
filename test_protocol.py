import json
import unittest
from unittest.mock import patch
from protocol import packet, parse_reply, checksum, Monitor
from settings import SETTINGS, BY_KEY
from transport import UsbError
from xeneon_control import validate_profile, MODEL, DemoMonitor, set_verified, diagnostic


def reply(code, value, vendor=False):
    if vendor:
        data = bytes([0x6E, 0x89, 2, 0, 0xFE, code, 0, 0, 100, 0, value])
    else:
        data = bytes([0x6E, 0x88, 2, 0, code, 0, 0, 100, 0, value])
    return data + bytes([checksum(data) ^ 0x50]) + (b"" if vendor else b"\0")


class FramingTests(unittest.TestCase):
    def test_standard_get_and_set_packets(self):
        self.assertEqual(packet(0x10), bytes.fromhex("6e 51 82 01 10 ac"))
        self.assertEqual(packet(0x10, value=34), bytes.fromhex("6e 51 84 03 10 00 22 8a"))

    def test_vendor_read_uses_fe_write_uses_e0(self):
        self.assertEqual(packet(0xD3, True), bytes.fromhex("6e 51 83 01 fe d3 90"))
        data = packet(0xD3, True, 8)
        self.assertEqual(data[:7], bytes.fromhex("6e 51 84 03 e0 d3 08"))
        self.assertEqual(checksum(data), 0)

    def test_reply_formats(self):
        self.assertEqual(parse_reply(reply(0x10, 33), 0x10), 33)
        self.assertEqual(parse_reply(reply(0xD3, 8, True), 0xD3, True), 8)

    def test_rejects_invalid_checksums_wrong_features_and_error_status(self):
        valid = reply(0x10, 33)
        cases = [valid[:3], bytes([0]) + valid[1:], valid[:9] + bytes([99]) + valid[10:]]
        for bad in cases:
            with self.assertRaises(UsbError):
                parse_reply(bad, 0x10)
        with self.assertRaises(UsbError):
            parse_reply(valid, 0x12)
        invalid = bytearray(valid)
        invalid[3] = 1
        invalid[10] = checksum(invalid[:10]) ^ 0x50
        with self.assertRaises(UsbError):
            parse_reply(bytes(invalid), 0x10)

    def test_busy_is_retried_before_success(self):
        class Usb:
            def __init__(self):
                self.requests = []
                self.replies = [bytes(12), reply(0x10, 33)]
            def transfer(self, request_type, request, **kwargs):
                self.requests.append((request_type, request, kwargs))
                if request_type & 0x80:
                    return self.replies.pop(0)
        usb = Usb()
        with patch("protocol.time.sleep"):
            self.assertEqual(Monitor(usb).get(0x10), 33)
        self.assertEqual(len(usb.requests), 4)
        self.assertEqual(usb.requests[1], (0xC0, 0xA3, {"index": 0x6F, "length": 12}))

    def test_firmware_query_is_a_vendor_read(self):
        class Usb:
            def __init__(self): self.requests = []
            def transfer(self, request_type, request, **kwargs):
                self.requests.append((request_type, request, kwargs))
                if request_type & 0x80:
                    # Captured from the actual monitor; checksum included.
                    return bytes.fromhex("6e 89 02 00 fe c7 01 00 50 00 08 d5")
        usb = Usb()
        with patch("protocol.time.sleep"):
            self.assertEqual(Monitor(usb).firmware_version(), "0.08")
        self.assertEqual(usb.requests[0], (0x40, 0xB2, {"data": bytes.fromhex("6e 51 83 01 fe c7 84")}))
        self.assertEqual(len(usb.requests), 2)
        self.assertNotIn((0xC7, True), {(s.code, s.vendor) for s in SETTINGS})

    def test_firmware_failure_does_not_hide_working_settings(self):
        class MissingVersion(DemoMonitor):
            def firmware_version(self): raise UsbError("Version unavailable")
        result = diagnostic(MissingVersion())
        self.assertIsNone(result["firmware_version"])
        self.assertEqual(result["firmware_error"], "Version unavailable")
        self.assertEqual(len(result["values"]), len(SETTINGS))
        self.assertEqual(result["errors"], {})

    def test_write_validation_precedes_usb_access(self):
        class NoUsb:
            def transfer(self, *args, **kwargs):
                raise AssertionError("invalid value reached USB")
        for bad in (-1, 101, True, "33"):
            with self.assertRaises(ValueError):
                Monitor(NoUsb()).set(BY_KEY["brightness"], bad)


class SettingTests(unittest.TestCase):
    def test_known_non_sequential_wire_values(self):
        self.assertEqual(BY_KEY["preset"].choices[8], "Adobe RGB")
        self.assertEqual(BY_KEY["response_time"].choices[3], "Faster")
        self.assertEqual(BY_KEY["response_time"].choices[2], "Fastest")
        self.assertEqual(BY_KEY["input_source"].choices[0x10], "USB-C")
        self.assertEqual(BY_KEY["aspect_ratio"].choices[1], "Auto")

    def test_allowlist_is_unique_and_choices_validate(self):
        self.assertEqual(len(SETTINGS), len(BY_KEY))
        self.assertEqual(len(SETTINGS), len({(s.code, s.vendor) for s in SETTINGS}))
        for s in SETTINGS:
            for v in s.choices or [s.minimum, s.maximum]:
                s.validate(v)

    def test_profiles_cannot_switch_inputs_or_write_unknown_controls(self):
        for values in ({"input_source": 17}, {"0xF0": 1}, {"brightness": True}, {"gamma": 4}, {"brightness": 101}):
            with self.assertRaises(ValueError):
                validate_profile({"format": "xeneon-control-v1", "model": MODEL, "values": values})

    def test_profile_sets_preset_before_dependent_controls(self):
        data = {"format": "xeneon-control-v1", "model": MODEL,
                "values": {"brightness": 33, "preset": 8}}
        self.assertEqual([s.key for s, v in validate_profile(data)], ["preset", "brightness"])

    def test_readback_detects_ignored_writes(self):
        class Locked(DemoMonitor):
            def set(self, s, value):
                pass
        with self.assertRaisesRegex(UsbError, "stayed at"):
            set_verified(Locked(), BY_KEY["brightness"], 34)


if __name__ == "__main__":
    unittest.main()
