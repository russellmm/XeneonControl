"""Minimal native USB transport. No Corsair libraries or third-party Python packages."""
import ctypes as C
import ctypes.util
import os
import sys

VID, PID = 0x1B1C, 0x0D05


class UsbError(Exception):
    pass


class WindowsUsb:
    def __init__(self, identifier=None):
        from ctypes import wintypes as W
        import winreg
        self.file = None
        self.handle = C.c_void_p()
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.usb = C.WinDLL("winusb", use_last_error=True)
        self.kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, C.c_void_p]
        self.kernel.CreateFileW.restype = C.c_void_p
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.usb.WinUsb_Initialize.argtypes = [C.c_void_p, C.POINTER(C.c_void_p)]
        self.usb.WinUsb_Free.argtypes = [C.c_void_p]

        class Setup(C.LittleEndianStructure):
            _pack_ = 1
            _fields_ = [("request_type", C.c_ubyte), ("request", C.c_ubyte),
                        ("value", C.c_ushort), ("index", C.c_ushort), ("length", C.c_ushort)]
        self.Setup = Setup
        self.usb.WinUsb_ControlTransfer.argtypes = [C.c_void_p, Setup, C.c_void_p, W.ULONG, C.POINTER(W.ULONG), C.c_void_p]
        candidates = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Enum\USB\VID_1B1C&PID_0D05") as root:
                for n in range(winreg.QueryInfoKey(root)[0]):
                    serial = winreg.EnumKey(root, n)
                    try:
                        with winreg.OpenKey(root, serial + r"\Device Parameters") as params:
                            path = winreg.QueryValueEx(params, "SymbolicName")[0]
                            candidates.append((serial, "\\\\?\\" + path[4:]))
                    except OSError:
                        continue
        except OSError:
            pass
        errors = []
        for serial, path in candidates:
            if identifier and identifier != serial:
                continue
            file_handle = self.kernel.CreateFileW(path, 0xC0000000, 3, None, 3, 0x40000000, None)
            if file_handle in (None, C.c_void_p(-1).value):
                errors.append(str(C.WinError(C.get_last_error())))
                continue
            if self.usb.WinUsb_Initialize(file_handle, C.byref(self.handle)):
                self.file = file_handle
                self.identifier = serial
                return
            errors.append(str(C.WinError(C.get_last_error())))
            self.kernel.CloseHandle(file_handle)
        raise UsbError("Cannot open the Corsair USB control device. Connect the monitor's USB IN port to this PC with a data cable. " + "; ".join(errors))

    def transfer(self, request_type, request, value=0, index=0, data=b"", length=0):
        from ctypes import wintypes as W
        size = length if request_type & 0x80 else len(data)
        buf = (C.c_ubyte * size)()
        if data:
            C.memmove(buf, data, len(data))
        transferred = W.ULONG()
        setup = self.Setup(request_type, request, value, index, size)
        if not self.usb.WinUsb_ControlTransfer(self.handle, setup, buf, size, C.byref(transferred), None):
            raise UsbError(str(C.WinError(C.get_last_error())))
        if transferred.value != size:
            raise UsbError("Incomplete USB transfer: %d of %d bytes" % (transferred.value, size))
        return bytes(buf)

    def close(self):
        if self.handle.value:
            self.usb.WinUsb_Free(self.handle)
            self.handle = C.c_void_p()
        if self.file is not None:
            self.kernel.CloseHandle(self.file)
            self.file = None


class LinuxUsb:
    def __init__(self, identifier=None):
        name = ctypes.util.find_library("usb-1.0")
        if not name:
            raise UsbError("Install the USB runtime: sudo apt install libusb-1.0-0")
        self.lib = C.CDLL(name)
        self.context = C.c_void_p()
        self.handle = C.c_void_p()
        self.lib.libusb_init.argtypes = [C.POINTER(C.c_void_p)]
        self.lib.libusb_exit.argtypes = [C.c_void_p]
        self.lib.libusb_close.argtypes = [C.c_void_p]
        self.lib.libusb_open_device_with_vid_pid.argtypes = [C.c_void_p, C.c_ushort, C.c_ushort]
        self.lib.libusb_open_device_with_vid_pid.restype = C.c_void_p
        self.lib.libusb_control_transfer.argtypes = [C.c_void_p, C.c_ubyte, C.c_ubyte, C.c_ushort, C.c_ushort, C.c_void_p, C.c_ushort, C.c_uint]
        self.lib.libusb_error_name.argtypes = [C.c_int]
        self.lib.libusb_error_name.restype = C.c_char_p
        result = self.lib.libusb_init(C.byref(self.context))
        if result < 0:
            raise UsbError(self.lib.libusb_error_name(result).decode())
        self.handle = C.c_void_p(self.lib.libusb_open_device_with_vid_pid(self.context, VID, PID))
        if not self.handle.value:
            self.close()
            raise UsbError("Corsair USB control device not available. Connect USB IN and install the included udev rule. WSL also needs USB passthrough.")
        self.identifier = "1b1c:0d05"

    def transfer(self, request_type, request, value=0, index=0, data=b"", length=0):
        size = length if request_type & 0x80 else len(data)
        buf = (C.c_ubyte * size)()
        if data:
            C.memmove(buf, data, len(data))
        result = self.lib.libusb_control_transfer(self.handle, request_type, request, value, index, buf, size, 1500)
        if result < 0:
            raise UsbError(self.lib.libusb_error_name(result).decode())
        if result != size:
            raise UsbError("Incomplete USB transfer: %d of %d bytes" % (result, size))
        return bytes(buf)

    def close(self):
        if self.handle.value:
            self.lib.libusb_close(self.handle)
            self.handle = C.c_void_p()
        if self.context.value:
            self.lib.libusb_exit(self.context)
            self.context = C.c_void_p()


def open_usb(identifier=None):
    if sys.platform == "win32":
        return WindowsUsb(identifier)
    if sys.platform.startswith("linux"):
        return LinuxUsb(identifier)
    raise UsbError("Supported platforms: Windows and Linux")
