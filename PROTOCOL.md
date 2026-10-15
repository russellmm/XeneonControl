# Protocol and evidence

The hardware is USB VID `1b1c`, PID `0d05`; Corsair's device manifest identifies the model as 32UHD144, enumerator `MccsUsb`, SoC `Nt68500`.

Windows uses the existing WinUSB driver through `CreateFileW` and `WinUsb_ControlTransfer`. Linux uses `libusb_control_transfer` on endpoint zero; it does not claim, detach, or replace kernel interface drivers. Both backends use the same packet implementation and setting allowlist.

OUT requests use `bmRequestType=0x40`, `bRequest=0xB2`, `wValue=0`, `wIndex=0`. Read reply requests use `bmRequestType=0xC0`, `bRequest=0xA3`, `wValue=0`, `wIndex=0x006F`, length 12.

| Operation | Packet before checksum |
|---|---|
| Standard feature read | `6E 51 82 01 <code>` |
| Corsair feature read | `6E 51 83 01 FE <code>` |
| Standard feature write | `6E 51 84 03 <code> 00 <value>` |
| Corsair feature write | `6E 51 84 03 E0 <code> <value>` |

Append the XOR of all preceding bytes. Standard replies have 11 meaningful bytes, vendor replies 12; validate header `6E`, length, response opcode `02`, status `00`, requested feature, and whole-message XOR `50`. The current value is the byte preceding the checksum. Reads wait 60 ms after request; transactions are paced, with longer delays for mode changes and Adaptive Sync. Values are bytes, bounded by the setting definitions. These commands do not touch firmware/ISP functions.

## Static analysis sources

The official catalog is [Corsair package metadata](https://www3.corsair.com/software/CUE_V5/public/modules/windows/packages/cuepkg-metadata.json). Inspected packages:

- `dev-xeneon-32uhd144_5.38.1_win32-release-amd64.cuepkg`: device manifest in Qt RCC; confirms model, USB identity, and supported feature names.
- `mccs-proto_5.52.93_win32-release-amd64.cuepkg`: `MccsProtocols.dll`; transport request/reply routines, frame builder/parser, feature dispatch, and value conversions.
- `core_5.52.93_win32-release-amd64.cuepkg`: Qt command and controller enum metadata used to resolve labels to numeric values.

Native DLL addresses relative to image base `0x180000000`: frame builder RVA `0x260F0`, reply parser `0x26410`, USB read `0x27930`, USB write `0x27BB0`, setting dispatch `0x1E5E0`. No third-party code from those DLLs is linked into or distributed with this utility.

Analysis used ordinary resource parsing and disassembly tools. REA readiness was checked, but its native analysis engines were unavailable; no claim here is based on a REA decompilation. The local research folder preserves the detailed resource and mapping records; it is excluded from release archives.

Reference: [Corsair 32UHD144 manual](https://www.corsair.com/us/en/explorer/gamer/monitors/corsair-xeneon-32uhd144-32-inch-ips-uhd-3840-x2160-144hz-refresh-rate-hdr600-gaming-monitor/). The UI exposes only documented or statically mapped settings, and distinguishes preset-controlled values from selectable modes.

## Runtime evidence and limits

Windows reads returned all 25 allowlisted features. The photo's AdobeRGB/33 matched vendor preset `8` and standard brightness `33`. A reversible brightness test read back `34`, restored `33` in a `finally` block, and confirmed every reported setting matched the baseline. Remaining writes are statically mapped and checked by readback when the user applies them; they were not exercised automatically. Tests on Ubuntu WSL cover framing, validation, GUI rendering, libusb loading, and missing USB-device handling; USB passthrough was absent, so Linux hardware operation remains unverified.

## Firmware version (read-only, version 1.2.2)

Corsair's `GetFirmwareVersions` dispatch at VA `0x18001E864` constructs vendor feature `C7 FE 00`, reads it via `0x18001C660`, and builds version major 0 / minor equal to the returned byte (version constructor call at `0x18001E8C5`). This is an ordinary feature read; no firmware update or ISP operation is involved. The utility formats it like the OSD, e.g. `0.08`. C7 is not a writable setting or profile field.

On October 15, 2026 the actual monitor returned `6E 89 02 00 FE C7 01 00 50 00 08 D5`, checksum XOR 50, for request `6E 51 83 01 FE C7 84`: firmware **0.08**. Evidence: `research/firmware-version-read.json`. Static analysis used the existing pefile/Capstone scripts, not a REA engine. A version-read failure is reported separately and does not disable working controls.
