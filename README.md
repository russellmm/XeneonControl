# Xeneon Control

A small, local control panel for the **CORSAIR XENEON 32UHD144** on Windows and Ubuntu Linux. It talks directly to the monitor over USB. No iCUE, Corsair service, account, network access, or startup task is needed.

Download the current Windows executable or Ubuntu source archive from [GitHub Releases](https://github.com/russellmm/XeneonControl/releases/latest).

## Windows

Double-click **XeneonControl.exe** in the Windows release. No installation or Python setup is needed. Keep the monitor's **USB IN** connection attached to your PC using a USB data cable, in addition to the video connection.

Choose a section, adjust a setting, and click **Apply**. The app reads the value back from the monitor before reporting success. **Refresh** rereads the OSD. **Undo last change** restores the previous value for the last verified individual change during this session.

**Close (X)** and **Hide to tray** hide the window while the utility stays running. Click the tray icon, or choose **Open Xeneon Control** from its right-click menu, to restore it. **Exit**, available in the window and tray menu, removes the icon and quits fully after any active USB request finishes. On Ubuntu, the window stays open if no working tray host is available. The portable EXE is unsigned. It extracts its bundled Python/Tk runtime to a temporary folder while running; the download and installed runtime are much smaller than an iCUE installation.

## Ubuntu

Extract the Ubuntu archive, open its folder in a terminal, and run:

```sh
bash install-ubuntu.sh
bash launch-ubuntu.sh
```

The setup script installs `python3`, `python3-tk`, `libusb-1.0-0`, `python3-gi`, `gir1.2-gtk-3.0`, and `gir1.2-ayatanaappindicator3-0.1`, then installs the included udev rule **only for USB device 1b1c:0d05**. Reconnect the USB data cable after setup if the device cannot be opened. Run the app as your normal desktop user, not root. It works with X11 or Wayland through Tk/XWayland. Ubuntu tray support also needs the desktop AppIndicator extension (normally supplied by Ubuntu Desktop). Without a tray host, the utility keeps its window visible and Exit still works.

Alternatively, install those packages and the rule yourself, then launch `python3 xeneon_control.py`. No pip packages are required at runtime; Ubuntu tray support uses the system PyGObject/AppIndicator packages. Python 3.10 or newer is supported.

Undo Ubuntu setup's device permission rule with:

```sh
sudo rm /etc/udev/rules.d/70-xeneon-control.rules
sudo udevadm control --reload-rules
```

## Controls

The 25 controls include picture presets, brightness, contrast, sharpness, saturation, response time, local dimming, MPRT, crosshair, color temperature, gamma, RGB gains, low blue light, aspect ratio, Adaptive Sync, power LED, refresh overlay, OSD language/transparency, volume, audio input, video input, and automatic source detection.

**Save picture profile** captures the readable, valid Picture and Color settings. **Load profile** previews those settings before applying them. Profiles exclude video inputs and system settings. Some calibrated picture presets and HDR own individual settings; a value that the monitor refuses is reported, and partial profile application is reported explicitly. An entire profile is not a transactional change and is not covered by single-change Undo.

The Information page and `--diagnose` show the monitor firmware version (read-only). OSD timeout editing, USB-C lane selection, factory reset, and firmware updates are not implemented. The operating system manages HDR, resolution, and refresh rate. Input switching can remove this PC's picture; use the monitor joystick to return if needed. The utility targets one connected 32UHD144 control device at a time.

## Command line

From source, on Windows use `python`; on Ubuntu use `python3`:

```sh
python3 xeneon_control.py --list
python3 xeneon_control.py --get brightness
python3 xeneon_control.py --set brightness 33
python3 xeneon_control.py --diagnose --output monitor-report.json
python3 xeneon_control.py --demo
```

`--list` shows the exact numeric values accepted for presets and other choices. Only the known settings in `settings.py` can be written. Arbitrary VCP, firmware, and register commands are not exposed. Reads validate framing, feature identity, status, and checksum. Hardware requests run serially, and only one app/CLI process can control the device per user session. Choose Exit in the utility before running a separate CLI command. Close other monitor-control software while using this utility.

The Windows EXE is a GUI program; for CLI output use `--output`, for example:

```powershell
.\XeneonControl.exe --get brightness --output brightness.json
```

## Validation — version 1.2.2, October 15, 2026

- Real Windows USB device opened using the existing Windows WinUSB driver, without iCUE.
- All 25 controls read successfully. Adobe RGB preset and brightness 33 matched the physical OSD photo.
- Brightness was changed **33 → 34 → 33**, verifying both writes. All 25 settings matched before and after.
- All 20 automated tests passed on Windows. Ubuntu WSL passed 19 tests and skipped the native Windows tray test. The packaged Windows executable also passed the native tray smoke test.
- All seven GUI sections rendered in Windows and Ubuntu WSL smoke tests using demo data.
- Ubuntu libusb loaded and the missing-device path was checked. WSL has no USB passthrough configured here, so **real USB control on Linux has not been tested**. A normal Ubuntu desktop with the USB cable and udev rule is the intended Linux setup. WSL requires separate USB passthrough configuration; the setup script does not install it.

Brightness and the Adobe RGB/sRGB preset round trip have been physically write-tested and restored to their original values. Firmware 0.08 was read successfully. Other controls use mappings recovered from Corsair's module and are readback-verified when used. See `PROTOCOL.md` for the transport and evidence boundaries.

## Development

```sh
python3 -m unittest -v test_protocol test_refresh test_ui test_tray
python3 xeneon_control.py --smoke-test
```

On a headless Linux machine: `xvfb-run -a python3 xeneon_control.py --smoke-test`.

Use `Build-Windows.ps1` to create the portable EXE. Build dependencies are isolated in `.build-env`; Windows runtime dependencies are from Python's standard library plus Windows APIs; Ubuntu additionally uses the system USB and AppIndicator libraries. The release includes no downloaded Corsair DLLs or packages. This is an independent utility, not a Corsair product.

## Version 1.1 — tray and relocation

Windows uses Shell_NotifyIcon directly, with no added pip runtime dependencies. The native tray smoke test checked icon creation, hide, restore, Exit, and icon cleanup using demo data. The same build was retested against the monitor with read-only diagnostics. Ubuntu uses an optional Ayatana AppIndicator; its actual tray needs a desktop tray host and has not been verified inside WSL.

## Version 1.2 — faster control updates

Individual edits now update in place immediately after their own readback verification, without waiting for all 25 controls. Applying a value preserves the current field, scroll position, and other unsaved edits. Preset-dependent values refresh progressively in the background, with foreground edits taking priority. Older background reads cannot overwrite a newer change.

Scalar settle time is now 100 ms; presets use the recovered per-preset timing with a margin. Gamma and Adaptive Sync retain their longer settling intervals. On this monitor, brightness verification measured 0.328 seconds and Adobe RGB to sRGB measured 0.478 seconds, excluding the final GUI event dispatch. The removed full refresh added 2.851 seconds. All 25 values matched the baseline after restoring the original preset and brightness.

Seventeen protocol, scheduling, and GUI regression tests passed on Windows and Ubuntu WSL. To run them on a headless Linux host:

```sh
xvfb-run -a python3 -m unittest -v test_protocol test_refresh test_ui
```

## Version 1.2.1 — tray restore crash

Fixed a fatal Python runtime abort when restoring from the Windows system tray. A native Windows notification callback was re-entering Tk while Tcl was pumping messages; on Python 3.14 this produced a `PyEval_RestoreThread` fatal error. The native callback now only places events on a queue. Tk's normal event loop handles restore, menus, and taskbar recovery.

The previous tray smoke test called the restore function directly and missed this native-callback path. The revised test sends real notification callback messages and checks ten mouse/keyboard restore cycles. An additional Windows regression test exercises notification-driven mouse, keyboard, context-menu Open, and context-menu Exit routes; menu selection itself is deterministic in the test. Eighteen tests passed on Windows. No monitor writes are involved in the tray tests.

## Version 1.2.2 — firmware information

The Information page and JSON diagnostics now read the monitor firmware version over USB. This adds no firmware update capability and does not change monitor settings. An unavailable firmware query is reported separately from control reads.
