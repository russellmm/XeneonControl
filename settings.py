"""Allowlisted XENEON 32UHD144 settings, using native monitor wire values.

Mappings are documented in research/metadata/feature-mappings.md.  Choice keys
are wire values, not positions in the monitor menu. No firmware commands exist
in this allowlist.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    group: str
    code: int
    vendor: bool = False
    minimum: int = 0
    maximum: int = 100
    choices: dict[int, str] = field(default_factory=dict)
    delay: float = 0.1
    profile: bool = True
    notes: str = ""

    def settle_delay(self, value: int) -> float:
        if self.key == "preset":
            # Native per-preset delay + 50ms scheduling margin, rounded up.
            return {0: .30, 1: .30, 2: .15, 3: .25, 4: .30,
                    5: .65, 6: .65, 7: .65, 8: .65}[value]
        return self.delay

    def validate(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{self.label} must be an integer")
        if not self.minimum <= value <= self.maximum:
            raise ValueError(f"{self.label} must be between {self.minimum} and {self.maximum}")
        if self.choices and value not in self.choices:
            raise ValueError(f"Unsupported {self.label} value: {value}")


_ON_OFF = {0: "Off", 1: "On"}

SETTINGS = [
    Setting("preset", "Preset", "Picture", 0xD3, True, 0, 8,
            {0: "Standard", 1: "Movie", 2: "Text", 3: "sRGB", 4: "Creative",
             5: "Game", 6: "HDR", 7: "DCI-P3", 8: "Adobe RGB"}, delay=0.7),
    Setting("brightness", "Brightness", "Picture", 0x10),
    Setting("contrast", "Contrast", "Picture", 0x12),
    Setting("sharpness", "Sharpness", "Picture", 0x87, maximum=10),
    Setting("saturation", "Saturation", "Picture", 0xF7, True, maximum=10),
    Setting("response_time", "Response time", "Picture", 0xF6, True, 0, 4,
            {0: "Normal", 1: "Fast", 3: "Faster", 2: "Fastest", 4: "Dynamic OD"}, delay=.2),
    Setting("local_dimming", "Local dimming", "Picture", 0xE5, True, 0, 1, _ON_OFF),
    Setting("mprt", "MPRT", "Picture", 0xF5, True, 0, 1, _ON_OFF),
    Setting("crosshair", "Crosshair", "Picture", 0xE4, True, 0, 6,
            {0: "Off", 1: "Green dot", 2: "Red dot", 3: "Green cross",
             4: "Red cross", 5: "Green angle", 6: "Red angle"}),
    Setting("aspect_ratio", "Aspect ratio", "System", 0x91, True, 0, 2,
            {1: "Auto", 0: "16:9", 2: "4:3"}, profile=False),
    Setting("color_temperature", "Color temperature", "Color", 0xFC, True, 0, 3,
            {0: "Cool", 1: "Normal", 2: "Warm", 3: "Custom"}),
    Setting("gamma", "Gamma", "Color", 0xF8, True, 1, 3,
            {1: "2.0", 2: "2.2", 3: "2.4"}, delay=0.45,
            notes="Firmware may report other current values; only documented modes are selectable."),
    Setting("red", "Red gain", "Color", 0xFB, True),
    Setting("green", "Green gain", "Color", 0xFA, True),
    Setting("blue", "Blue gain", "Color", 0xF9, True),
    Setting("low_blue_light", "Low blue light", "Color", 0xF4, True, 0, 1, _ON_OFF),
    Setting("osd_language", "OSD language", "OSD", 0xCC, False, 1, 10,
            {1: "Chinese", 2: "English", 3: "French", 4: "German", 5: "Italian",
             6: "Japanese", 7: "Korean", 8: "Portuguese", 9: "Russian", 10: "Spanish"},
            profile=False),
    Setting("osd_transparency", "OSD transparency", "OSD", 0xD0, True, 0, 1,
            _ON_OFF, profile=False),
    Setting("freesync", "Adaptive Sync / FreeSync", "System", 0xF3, True, 0, 1,
            _ON_OFF, delay=8.0, profile=False,
            notes="The display may briefly reconnect when Adaptive Sync changes."),
    Setting("power_led", "Power LED", "System", 0xCE, True, 0, 1,
            _ON_OFF, profile=False),
    Setting("refresh_rate_gauge", "Refresh rate overlay", "System", 0xDD, True, 0, 1,
            _ON_OFF, profile=False),
    Setting("volume", "Volume", "Audio", 0x62, profile=False),
    Setting("audio_input", "Audio input", "Audio", 0xEE, True, 0, 4,
            {0: "Auto", 1: "HDMI 1", 2: "HDMI 2", 3: "DisplayPort", 4: "USB-C"},
            profile=False),
    Setting("input_source", "Input source", "Input", 0x60, False, 0x0F, 0x12,
            {0x11: "HDMI 1", 0x12: "HDMI 2", 0x0F: "DisplayPort", 0x10: "USB-C"},
            delay=1.0, profile=False),
    Setting("source_detection", "Source detection", "Input", 0x8F, True, 0, 1,
            {0: "Manual", 1: "Auto"}, profile=False),
]

BY_KEY = {setting.key: setting for setting in SETTINGS}
