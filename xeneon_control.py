#!/usr/bin/env python3
"""Xeneon Control: a small, local control panel for the Corsair 32UHD144."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from background_refresh import BackgroundRefresh
from protocol import Monitor
from settings import SETTINGS, BY_KEY
from transport import UsbError, open_usb

VERSION = "1.2.2"
MODEL = "CORSAIR XENEON 32UHD144"


class InstanceLock:
    """Serialize this application's processes so replies cannot cross between them."""
    def __enter__(self):
        self.file = None
        if sys.platform == "win32":
            import ctypes as c
            self.kernel = c.WinDLL("kernel32", use_last_error=True)
            self.kernel.CreateMutexW.argtypes = [c.c_void_p, c.c_int, c.c_wchar_p]
            self.kernel.CreateMutexW.restype = c.c_void_p
            self.kernel.CloseHandle.argtypes = [c.c_void_p]
            self.mutex = self.kernel.CreateMutexW(None, False, "Local\\XeneonControl_1B1C_0D05")
            if not self.mutex or c.get_last_error() == 183:
                if self.mutex:
                    self.kernel.CloseHandle(self.mutex)
                raise UsbError("Xeneon Control is already running. Choose Exit in its window or tray menu before starting another command.")
        else:
            import fcntl
            directory = Path(os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir()))
            self.file = open(directory / ("xeneon-control-%d.lock" % os.getuid()), "a+")
            try:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.file.close()
                self.file = None
                raise UsbError("Xeneon Control is already running. Choose Exit in its window or tray menu before starting another command.")
        return self

    def __exit__(self, *args):
        if self.file:
            self.file.close()
        if sys.platform == "win32":
            self.kernel.CloseHandle(self.mutex)


class DemoMonitor:
    def __init__(self):
        self.values = {s.key: next(iter(s.choices)) if s.choices else s.minimum for s in SETTINGS}
        self.values.update(brightness=33, contrast=50, volume=62, preset=8)

    def get(self, code, vendor=False):
        return next(self.values[s.key] for s in SETTINGS if (s.code, s.vendor) == (code, vendor))

    def firmware_version(self):
        return "0.08"

    def set(self, setting, value):
        setting.validate(value)
        self.values[setting.key] = value

    def close(self):
        pass


def read_all(monitor):
    values, errors = {}, {}
    for s in SETTINGS:
        try:
            values[s.key] = monitor.get(s.code, s.vendor)
        except (UsbError, OSError) as exc:
            errors[s.key] = str(exc)
    return values, errors


def validate_profile(data):
    if not isinstance(data, dict) or data.get("format") != "xeneon-control-v1" or data.get("model") != MODEL:
        raise ValueError("This is not a 32UHD144 Xeneon Control profile.")
    values = data.get("values")
    if not isinstance(values, dict) or not values:
        raise ValueError("The profile contains no settings.")
    result = []
    for key, value in values.items():
        s = BY_KEY.get(key)
        if s is None or not s.profile:
            raise ValueError("Profile contains a setting that cannot be restored: " + str(key))
        if type(value) is not int:
            raise ValueError("Invalid value for " + key)
        s.validate(value)
        result.append((s, value))
    order = {s.key: n for n, s in enumerate(SETTINGS)}
    return sorted(result, key=lambda pair: order[pair[0].key])


def set_verified(monitor, setting, value):
    before = monitor.get(setting.code, setting.vendor)
    monitor.set(setting, value)
    actual = monitor.get(setting.code, setting.vendor)
    if actual != value:
        raise UsbError("%s stayed at %s. The current preset, HDR, or another monitor setting may lock it." % (setting.label, actual))
    return before



def apply_one(monitor, setting, value):
    """Verify only the edited control; unrelated reads must not delay its result."""
    try:
        before = set_verified(monitor, setting, value)
        return before, value, None
    except UsbError as exc:
        try:
            actual = monitor.get(setting.code, setting.vendor)
        except (UsbError, OSError):
            actual = None
        return None, actual, str(exc)


def related_settings(setting):
    if setting.key == "preset":
        return [s for s in SETTINGS if s.group in ("Picture", "Color") and s.key != "preset"]
    dependencies = {
        "color_temperature": ("red", "green", "blue"),
        "low_blue_light": ("color_temperature", "gamma", "red", "green", "blue"),
        "mprt": ("brightness", "local_dimming", "freesync", "response_time"),
        "local_dimming": ("brightness", "contrast"),
        "freesync": ("mprt", "aspect_ratio", "response_time"),
    }
    return [BY_KEY[key] for key in dependencies.get(setting.key, ())]


def read_firmware_version(monitor):
    try:
        return monitor.firmware_version(), None
    except (UsbError, OSError) as exc:
        return None, str(exc)


def diagnostic(monitor):
    values, errors = read_all(monitor)
    firmware, firmware_error = read_firmware_version(monitor)
    return {"firmware_version": firmware, "firmware_error": firmware_error, "application": "Xeneon Control " + VERSION, "model": MODEL,
            "platform": sys.platform, "transport": "USB 1B1C:0D05",
            "read_only": True, "values": values, "errors": errors}


def gui(demo=False, smoke=False, tray_smoke=False, _test_driver=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk()
    root.title("Xeneon Control" + (" — DEMO" if demo else ""))
    root.geometry("930x740")
    root.minsize(810, 590)
    root.configure(bg="#11151b")
    root.option_add("*Font", ("Segoe UI" if sys.platform == "win32" else "DejaVu Sans", 10))
    bg, panel, muted, accent, ink = "#11151b", "#1c222c", "#9daabb", "#c6ee86", "#edf2f7"
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TCombobox", fieldbackground="#293342", background="#293342", foreground=ink, arrowcolor=accent, borderwidth=0, padding=7)
    style.map("TCombobox", fieldbackground=[("readonly", "#293342")], foreground=[("readonly", ink)])
    style.configure("Vertical.TScrollbar", background="#394454", troughcolor=bg, borderwidth=0, arrowcolor=muted)
    style.configure("Horizontal.TScale", background=accent, troughcolor="#384354", borderwidth=0, lightcolor=accent, darkcolor=accent)
    root.option_add("*TCombobox*Listbox.background", "#293342")
    root.option_add("*TCombobox*Listbox.foreground", ink)
    root.option_add("*TCombobox*Listbox.selectBackground", "#465b39")

    class App:
        def __init__(self):
            self.monitor = None
            self.firmware_version, self.firmware_error = None, None
            self.values, self.errors = {}, {}
            self.busy = False
            self.closed = False
            self.future = None
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="monitor-usb")
            self.category = "Picture"
            self.undo = None
            self.widgets = []
            self.rows_by_key = {}
            self.background = BackgroundRefresh(self.executor, root.after,
                lambda setting: self.monitor.get(setting.code, setting.vendor),
                self.receive_background, lambda: self.busy)
            self.tray = None
            self.tray_hidden = False
            header = tk.Frame(root, bg=bg)
            header.pack(fill="x", padx=26, pady=(24, 18))
            tk.Label(header, text="XENEON / CONTROL", fg=accent, bg=bg, font=("Segoe UI", 11, "bold")).pack(anchor="w")
            tk.Label(header, text="Your monitor. Your settings.", fg=ink, bg=bg, font=("Segoe UI", 23, "bold")).pack(anchor="w", pady=(6, 5))
            self.connection = tk.Label(header, text="Connecting to 32UHD144 over USB…", fg=muted, bg=bg)
            self.connection.pack(anchor="w")
            toolbar = tk.Frame(root, bg=bg)
            toolbar.pack(fill="x", padx=26, pady=(0, 18))
            self.refresh_button = self.button(toolbar, "Refresh", self.refresh)
            self.refresh_button.pack(side="left")
            self.save_button = self.button(toolbar, "Save picture profile", self.save_profile)
            self.save_button.pack(side="left", padx=(8, 0))
            self.load_button = self.button(toolbar, "Load profile", self.load_profile)
            self.load_button.pack(side="left", padx=8)
            self.undo_button = self.button(toolbar, "Undo last change", self.undo_change)
            self.undo_button.pack(side="right")
            body = tk.Frame(root, bg=bg)
            body.pack(fill="both", expand=True, padx=26)
            sidebar = tk.Frame(body, bg=bg, width=160)
            sidebar.pack(side="left", fill="y", padx=(0, 20))
            sidebar.pack_propagate(False)
            tk.Label(sidebar, text="MONITOR SETTINGS", bg=bg, fg=muted, font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 14))
            self.nav = {}
            for category in ("Picture", "Color", "OSD", "System", "Audio", "Input", "Information"):
                button = self.button(sidebar, category, lambda c=category: self.show(c))
                button.configure(anchor="w", padx=12, pady=11)
                button.pack(fill="x", pady=3)
                self.nav[category] = button
            right = tk.Frame(body, bg=bg)
            right.pack(fill="both", expand=True)
            self.title = tk.Label(right, text="Picture", font=("Segoe UI", 17, "bold"), bg=bg, fg=ink, anchor="w")
            self.title.pack(fill="x", pady=(2, 6))
            self.hint = tk.Label(right, text="Change a value, then choose Apply.", bg=bg, fg=muted, anchor="w", justify="left", wraplength=590)
            self.hint.pack(fill="x", pady=(0, 12))
            viewport = tk.Frame(right, bg=bg)
            viewport.pack(fill="both", expand=True)
            self.canvas = tk.Canvas(viewport, bg=bg, highlightthickness=0)
            scroll = ttk.Scrollbar(viewport, orient="vertical", command=self.canvas.yview)
            self.canvas.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            self.canvas.pack(side="left", fill="both", expand=True)
            self.rows = tk.Frame(self.canvas, bg=bg)
            self.canvas_window = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")
            self.rows.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
            self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
            root.bind_all("<MouseWheel>", self.wheel)
            self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
            self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
            footer = tk.Frame(root, bg=bg)
            footer.pack(fill="x", padx=26, pady=18)
            self.status = tk.Label(footer, text="Reading monitor settings…", fg=muted, bg=bg, anchor="w", justify="left", wraplength=860)
            actions = tk.Frame(footer, bg=bg)
            actions.pack(side="right", padx=(12, 0))
            self.button(actions, "Hide to tray", self.hide_to_tray).pack(side="left", padx=(0, 8))
            self.button(actions, "Exit", self.close).pack(side="left")
            self.status.configure(wraplength=600)
            self.status.pack(side="left", fill="x", expand=True)
            if not smoke:
                try:
                    from tray import create_tray
                    self.tray = create_tray(root, self.restore, self.close)
                except Exception as exc:
                    self.tray_error = str(exc)
            root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
            self.show("Picture")
            root.after(30, self.refresh)

        def button(self, parent, text, command):
            return tk.Button(parent, text=text, command=command, bg="#293342", fg=ink, activebackground="#3b4b35", activeforeground=accent,
                             relief="flat", bd=0, padx=12, pady=8, cursor="hand2", disabledforeground="#657286", takefocus=True)

        def wheel(self, event):
            # Leave combo boxes and spinboxes to handle their own scrolling.
            if event.widget.winfo_class() not in ("TCombobox", "Spinbox", "Scale"):
                self.canvas.yview_scroll(-int(event.delta / 120), "units")

        def run(self, work, done, text, preserve_editors=False):
            if self.busy:
                return
            self.busy = True
            self.background.invalidate()
            self.status.configure(text=text, fg=muted)
            if preserve_editors:
                self.update_editors()
            else:
                self.show(self.category)
            self.update_toolbar()
            self.future = self.executor.submit(work)
            def poll():
                if self.closed:
                    return
                if not self.future.done():
                    root.after(20, poll)
                    return
                self.busy = False
                try:
                    done(self.future.result())
                except Exception as exc:
                    self.status.configure(text=str(exc), fg="#ffb39b")
                    if self.monitor is None:
                        self.values, self.errors = {}, {}
                        self.firmware_version, self.firmware_error = None, None
                        self.connection.configure(text="USB unavailable · reconnect and Refresh", fg="#ffb39b")
                if preserve_editors:
                    self.update_editors()
                else:
                    self.show(self.category)
                self.update_toolbar()
                self.background.resume()
            root.after(20, poll)

        def update_editors(self):
            for key, row in self.rows_by_key.items():
                active = key in self.values and not self.busy
                for widget in row["editors"]:
                    state = "readonly" if widget.winfo_class() == "TCombobox" else "normal"
                    widget.configure(state=state if active else "disabled")

        def sync_row(self, key, preserve_draft=False):
            row = self.rows_by_key.get(key)
            if row is None:
                return
            setting = BY_KEY[key]
            current = self.values.get(key)
            row["current"].configure(text="Unavailable" if current is None else self.display_value(setting, current))
            if current is not None:
                display = setting.choices.get(current, "Select a value") if setting.choices else current
                try:
                    unchanged = row["variable"].get() == row["displayed"]
                except tk.TclError:
                    unchanged = False
                if not preserve_draft or unchanged:
                    row["variable"].set(display)
                    row["displayed"] = display
            self.update_editors()

        def receive_background(self, setting, value, error):
            if error:
                self.errors[setting.key] = error
            else:
                self.values[setting.key] = value
                self.errors.pop(setting.key, None)
            self.sync_row(setting.key, preserve_draft=True)

        def update_toolbar(self):
            connected = self.monitor is not None
            self.refresh_button.configure(state="disabled" if self.busy else "normal")
            for button in (self.save_button, self.load_button):
                button.configure(state="normal" if connected and not self.busy else "disabled")
            self.undo_button.configure(state="normal" if self.undo and not self.busy else "disabled")

        def refresh(self):
            def work():
                if self.monitor is not None:
                    self.monitor.close()
                    self.monitor = None
                monitor = DemoMonitor() if demo else Monitor(open_usb())
                try:
                    values, errors = read_all(monitor)
                    firmware, firmware_error = read_firmware_version(monitor)
                except BaseException:
                    monitor.close()
                    raise
                self.monitor = monitor
                return monitor, values, errors, firmware, firmware_error
            def done(result):
                self.monitor, self.values, self.errors, self.firmware_version, self.firmware_error = result
                self.connection.configure(text=("DEMO — hardware writes disabled" if demo else "CORSAIR XENEON 32UHD144  ·  USB connected"), fg=accent)
                self.status.configure(text="Read %d controls. Changes apply only when you click Apply.%s" % (len(self.values), " Some controls did not respond." if self.errors else ""), fg=muted)
            self.run(work, done, "Reading OSD settings over USB…")

        def show(self, category):
            self.category = category
            self.title.configure(text=category if category != "OSD" else "OSD settings")
            for key, b in self.nav.items():
                b.configure(bg="#3a4930" if key == category else "#1c222c", fg=accent if key == category else ink)
            for child in self.rows.winfo_children():
                child.destroy()
            self.widgets = []
            self.rows_by_key = {}
            self.canvas.yview_moveto(0)
            if category == "Information":
                self.hint.configure(text="Connection details and current settings.")
                firmware = self.firmware_version or ("Unavailable: " + self.firmware_error if self.firmware_error else "Unavailable — connect and Refresh")
                details = ("Xeneon Control " + VERSION + "\n\n" + MODEL + "\nFirmware version: " + firmware + "\nUSB device 1B1C:0D05\nNative WinUSB / libusb transport\n\n"
                           "No Corsair installation, account, network connection,\nstartup entry, or background service.\n\n"
                           "HDR, refresh rate, and resolution are managed by\nyour operating system. The monitor may lock some\ncontrols in HDR or calibrated picture presets.\n\n"
                           "OSD timeout, USB-C lane selection, and factory reset\nare not exposed in this version.\n\n" +
                           "\n".join("%s: %s" % (s.label, self.display_value(s, self.values[s.key])) for s in SETTINGS if s.key in self.values))
                tk.Label(self.rows, text=details, justify="left", anchor="nw", bg=panel, fg=ink, padx=18, pady=18, wraplength=540).pack(fill="x")
                return
            self.hint.configure(text="Picture presets and HDR can lock individual controls. Every change is read back to verify it.")
            if self.monitor is None and not self.busy:
                tk.Label(self.rows, text="Connect the monitor's USB IN port to your PC\nwith a USB data cable, then click Refresh.\n\nOn Ubuntu, install the included udev rule first.", justify="left", bg=panel, fg=ink, padx=20, pady=24, wraplength=520).pack(fill="x")
                return
            for s in SETTINGS:
                if s.group == category:
                    self.row(s)

        def display_value(self, s, value):
            if s.key == "color_temperature" and value == 4:
                return "Color space (preset controlled)"
            return s.choices.get(value, "Current value %d (preset controlled)" % value) if s.choices else str(value)

        def row(self, s):
            frame = tk.Frame(self.rows, bg=panel, padx=16, pady=12)
            frame.pack(fill="x", pady=(0, 9))
            top = tk.Frame(frame, bg=panel)
            top.pack(fill="x")
            tk.Label(top, text=s.label, bg=panel, fg=ink, anchor="w", font=("Segoe UI", 11, "bold")).pack(side="left")
            current = self.values.get(s.key)
            current_label = tk.Label(top, text="—" if current is None else self.display_value(s, current), bg=panel, fg=accent)
            current_label.pack(side="right")
            controls = tk.Frame(frame, bg=panel)
            controls.pack(fill="x", pady=(10, 0))
            active = current is not None and not self.busy
            button = self.button(controls, "Apply", lambda: None)
            button.pack(side="right", padx=(14, 0))
            if s.choices:
                choices = list(s.choices)
                labels = list(s.choices.values())
                value = tk.StringVar(value=s.choices.get(current, "Select a value"))
                combo = ttk.Combobox(controls, textvariable=value, values=labels, state="readonly" if active else "disabled")
                combo.pack(side="left", fill="x", expand=True)
                def apply():
                    if value.get() not in labels:
                        return
                    self.apply(s, choices[labels.index(value.get())])
                button.configure(command=apply)
                self.widgets.append(combo)
                editors = [combo, button]
            else:
                value = tk.IntVar(value=current if current is not None else s.minimum)
                spin = tk.Spinbox(controls, from_=s.minimum, to=s.maximum, textvariable=value, width=5, bg="#293342", fg=ink, insertbackground=ink, buttonbackground="#293342", relief="flat", font=("Segoe UI", 11), state="normal" if active else "disabled")
                spin.pack(side="right", padx=(12, 0))
                slider = ttk.Scale(controls, from_=s.minimum, to=s.maximum, variable=value, orient="horizontal",
                                   command=lambda v: value.set(round(float(v))), state="normal" if active else "disabled", takefocus=True)
                slider.pack(side="left", fill="x", expand=True)
                def apply():
                    try:
                        self.apply(s, value.get())
                    except (ValueError, tk.TclError) as exc:
                        self.status.configure(text="Enter a valid number for " + s.label, fg="#ffb39b")
                button.configure(command=apply)
                self.widgets.extend([spin, slider])
                editors = [spin, slider, button]
            self.rows_by_key[s.key] = {"variable": value, "displayed": value.get(), "current": current_label, "editors": editors}
            button.configure(state="normal" if active else "disabled")
            if s.key in self.errors:
                tk.Label(frame, text="Unavailable: " + self.errors[s.key], bg=panel, fg=muted, wraplength=510, justify="left").pack(anchor="w", pady=(8, 0))

        def apply(self, setting, value):
            try:
                setting.validate(value)
            except ValueError as exc:
                self.status.configure(text=str(exc), fg="#ffb39b")
                return
            if setting.key == "input_source" and not messagebox.askokcancel("Switch monitor input", "Switch to %s?\n\nThe picture on this PC may disappear. Use the monitor joystick to switch back if needed." % self.display_value(setting, value), parent=root):
                return
            def work():
                return apply_one(self.monitor, setting, value)
            def done(result):
                before, actual, error = result
                if actual is not None:
                    self.values[setting.key] = actual
                    self.errors.pop(setting.key, None)
                self.sync_row(setting.key)
                if error:
                    self.status.configure(text=error, fg="#ffb39b")
                    return
                self.undo = (setting, before)
                self.status.configure(text="%s set to %s · verified on monitor" %
                    (setting.label, self.display_value(setting, value)), fg=accent)
                if before != value:
                    self.background.request(related_settings(setting))
            self.run(work, done, "Applying %s…" % setting.label, preserve_editors=True)

        def undo_change(self):
            if self.undo:
                self.apply(*self.undo)

        def save_profile(self):
            path = filedialog.asksaveasfilename(parent=root, title="Save picture profile", defaultextension=".json", filetypes=[("Xeneon picture profile", "*.json")])
            if not path:
                return
            def work():
                values, errors = read_all(self.monitor)
                saved = {}
                for s in SETTINGS:
                    if s.profile and s.key in values:
                        try:
                            s.validate(values[s.key])
                            saved[s.key] = values[s.key]
                        except ValueError:
                            pass
                if not saved:
                    raise UsbError("No picture settings could be read.")
                Path(path).write_text(json.dumps({"format": "xeneon-control-v1", "model": MODEL, "values": saved}, indent=2), encoding="utf-8")
                return values, errors
            def done(result):
                self.values, self.errors = result
                self.status.configure(text="Picture profile saved to " + path, fg=accent)
            self.run(work, done, "Reading current picture settings for the profile…")

        def load_profile(self):
            path = filedialog.askopenfilename(parent=root, title="Load picture profile", filetypes=[("Xeneon picture profile", "*.json")])
            if not path:
                return
            try:
                if Path(path).stat().st_size > 65536:
                    raise ValueError("Profile is too large.")
                changes = validate_profile(json.loads(Path(path).read_text(encoding="utf-8")))
            except (ValueError, OSError) as exc:
                messagebox.showerror("Cannot load profile", str(exc), parent=root)
                return
            summary = "\n".join("%s: %s" % (s.label, self.display_value(s, v)) for s, v in changes)
            if not messagebox.askokcancel("Apply picture profile", summary + "\n\nApply these settings to the monitor?", parent=root):
                return
            self.undo = None
            def work():
                applied, skipped = [], []
                # Calibrated modes can reject controls they own. Continue and report each one.
                for s, v in changes:
                    try:
                        set_verified(self.monitor, s, v)
                        applied.append(s.label)
                    except UsbError as exc:
                        skipped.append(str(exc))
                values, errors = read_all(self.monitor)
                return values, errors, applied, skipped
            def done(result):
                self.values, self.errors, applied, skipped = result
                self.status.configure(text="Profile applied: %d verified, %d not applied." % (len(applied), len(skipped)), fg="#ffb39b" if skipped else accent)
                if skipped:
                    messagebox.showinfo("Profile results", "\n\n".join(skipped), parent=root)
            self.run(work, done, "Applying picture profile…")

        def restore(self):
            if self.closed:
                return
            self.tray_hidden = False
            root.deiconify()
            root.lift()
            root.focus_force()

        def hide_to_tray(self):
            if self.closed:
                return
            if self.tray and self.tray.available():
                self.tray_hidden = True
                root.withdraw()
            else:
                messagebox.showinfo("System tray unavailable",
                    "A system tray is not available. The window will stay open.\n\n"
                    "Use Exit to quit. On Ubuntu, install the AppIndicator packages "
                    "and enable your desktop's AppIndicator extension.", parent=root)

        def close(self):
            if self.closed:
                return
            self.closed = True
            self.background.close()
            if self.tray:
                self.tray.close()
            root.withdraw()
            # Finish the one in-flight transaction before closing its USB handle.
            def cleanup():
                if self.monitor:
                    self.monitor.close()
            cleaned = self.executor.submit(cleanup)
            self.executor.shutdown(wait=False)
            def finish():
                if not cleaned.done():
                    root.after(40, finish)
                    return
                root.destroy()
            root.after(40, finish)

    app = App()
    if _test_driver is not None:
        root.after(0, lambda: _test_driver(root, app))
    smoke_result = [False]
    if smoke or tray_smoke:
        deadline = time.monotonic() + 20
        def guarded(callback):
            def invoke():
                try:
                    assert time.monotonic() < deadline, "GUI smoke test timed out"
                    callback()
                except Exception as exc:
                    if sys.stderr:
                        print("GUI smoke test failed: " + str(exc), file=sys.stderr)
                    app.close()
            return invoke

        def complete():
            smoke_result[0] = True
            if sys.stdout:
                print("GUI smoke test passed: all seven sections rendered; %d controls read" % len(app.values))
                if tray_smoke and sys.platform == "win32":
                    print("Native tray callbacks passed: 10 mouse/keyboard restore cycles and Exit")
            app.close()

        native_events = [0x400, 0x401] * 5
        def native_restore_cycle():
            assert root.state() == "normal", "Native tray event did not restore the window"
            assert not app.closed, "Native tray restore exited the application"
            if not native_events:
                app.tray.on_exit()
                assert app.closed, "Tray Exit did not begin shutdown"
                assert not app.tray.available(), "Exit did not remove the tray icon"
                complete()
                return
            app.hide_to_tray()
            root.update_idletasks()
            assert root.state() == "withdrawn", "Close did not hide the window"
            event = native_events.pop(0)
            posted = app.tray.user.PostMessageW(app.tray.window, 0x8001, 0, (1 << 16) | event)
            assert posted, "Could not deliver the native tray callback"
            root.after(100, guarded(native_restore_cycle))

        def check():
            if app.busy or app.monitor is None:
                root.after(30, guarded(check))
                return
            for category in app.nav:
                app.show(category)
                root.update_idletasks()
                assert app.rows.winfo_width() > 400, category
            app.show("Picture")
            if tray_smoke:
                assert app.tray and app.tray.available(), "No system tray is available"
                if sys.platform == "win32":
                    native_restore_cycle()
                    return
                app.hide_to_tray()
                root.update_idletasks()
                assert root.state() == "withdrawn", "Close did not hide the window"
                app.tray.on_show()
                root.update_idletasks()
                assert root.state() == "normal", "Tray Open did not restore the window"
                app.tray.on_exit()
                assert app.closed and not app.tray.available(), "Tray Exit did not clean up"
            complete()
        root.after(100, guarded(check))
    root.mainloop()
    return not (smoke or tray_smoke) or smoke_result[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lightweight USB OSD control for Corsair XENEON 32UHD144")
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--demo", action="store_true", help="Preview with simulated settings; no USB access")
    parser.add_argument("--smoke-test", action="store_true", help="Render every section with demo data, then exit")
    parser.add_argument("--tray-smoke-test", action="store_true", help="Test native tray hide, restore, and Exit with demo data")
    parser.add_argument("--diagnose", action="store_true", help="Read settings and print a JSON diagnostic")
    parser.add_argument("--list", action="store_true", help="List supported settings and allowed values")
    parser.add_argument("--get", metavar="SETTING", choices=sorted(BY_KEY))
    parser.add_argument("--set", nargs=2, metavar=("SETTING", "VALUE"), help="Write an allowlisted setting, then verify it")
    parser.add_argument("--output", type=Path, help="Write CLI output to this file (useful for the Windows EXE)")
    args = parser.parse_args(argv)
    def output(value):
        text = json.dumps(value, indent=2, ensure_ascii=False)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        elif sys.stdout:
            print(text)
    if args.list:
        output({s.key: {"label": s.label, "choices": s.choices} if s.choices else {"label": s.label, "minimum": s.minimum, "maximum": s.maximum} for s in SETTINGS})
        return 0
    try:
        with InstanceLock():
            if not (args.diagnose or args.get or args.set):
                passed = gui(args.demo or args.smoke_test or args.tray_smoke_test, args.smoke_test, args.tray_smoke_test)
                if args.output and (args.smoke_test or args.tray_smoke_test):
                    output({"passed": passed, "tray_test": args.tray_smoke_test, "version": VERSION})
                return 0 if passed else 1
            setting = None
            value = None
            if args.set:
                key, raw = args.set
                if key not in BY_KEY:
                    raise ValueError("Unknown setting: " + key)
                setting = BY_KEY[key]
                value = int(raw, 0)
                setting.validate(value)
            monitor = DemoMonitor() if args.demo else Monitor(open_usb())
            try:
                if args.set:
                    before = set_verified(monitor, setting, value)
                    output({"setting": setting.key, "before": before, "value": value, "verified": True, "demo": args.demo})
                elif args.get:
                    s = BY_KEY[args.get]
                    output({"setting": s.key, "value": monitor.get(s.code, s.vendor), "demo": args.demo})
                else:
                    report = diagnostic(monitor)
                    report["demo"] = args.demo
                    output(report)
                    if not report["values"]:
                        return 1
            finally:
                monitor.close()
    except (UsbError, OSError, ValueError) as exc:
        if args.output:
            output({"error": str(exc)})
        elif sys.stderr:
            print("Xeneon Control: " + str(exc), file=sys.stderr)
        else:
            import tkinter.messagebox
            tkinter.messagebox.showerror("Xeneon Control", str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
