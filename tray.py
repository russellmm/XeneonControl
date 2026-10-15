"""System tray integration using Windows APIs or Ubuntu's optional AppIndicator."""
import ctypes as C
import queue
import sys
import threading
from pathlib import Path


class WindowsTray:
    def __init__(self, root, on_show, on_exit):
        from ctypes import wintypes as W
        self.root, self.on_show, self.on_exit = root, on_show, on_exit
        self.window = None
        self.added = False
        self.error = ''
        self.events = queue.SimpleQueue()
        self.closed = False
        self.poll_id = None
        self.user = C.WinDLL('user32', use_last_error=True)
        self.shell = C.WinDLL('shell32', use_last_error=True)
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.callback_type = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
        class WindowClass(C.Structure):
            _fields_ = [('style', W.UINT), ('proc', self.callback_type), ('class_extra', C.c_int),
                        ('window_extra', C.c_int), ('instance', W.HINSTANCE), ('icon', W.HICON),
                        ('cursor', W.HANDLE), ('background', W.HBRUSH), ('menu', W.LPCWSTR), ('name', W.LPCWSTR)]
        class Guid(C.Structure):
            _fields_ = [('a', W.DWORD), ('b', W.WORD), ('c', W.WORD), ('d', C.c_ubyte * 8)]
        class NotifyIcon(C.Structure):
            _fields_ = [('size', W.DWORD), ('window', W.HWND), ('id', W.UINT), ('flags', W.UINT),
                        ('callback', W.UINT), ('icon', W.HICON), ('tip', W.WCHAR * 128),
                        ('state', W.DWORD), ('state_mask', W.DWORD), ('info', W.WCHAR * 256),
                        ('version', W.UINT), ('info_title', W.WCHAR * 64), ('info_flags', W.DWORD),
                        ('guid', Guid), ('balloon_icon', W.HICON)]
        self.NotifyIcon = NotifyIcon
        def bind(lib, name, args, result):
            fn = getattr(lib, name)
            fn.argtypes, fn.restype = args, result
            return fn
        bind(self.kernel, 'GetModuleHandleW', [W.LPCWSTR], W.HMODULE)
        bind(self.user, 'RegisterClassW', [C.POINTER(WindowClass)], W.ATOM)
        bind(self.user, 'UnregisterClassW', [W.LPCWSTR, W.HINSTANCE], W.BOOL)
        bind(self.user, 'CreateWindowExW', [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p], W.HWND)
        bind(self.user, 'DefWindowProcW', [W.HWND, W.UINT, W.WPARAM, W.LPARAM], C.c_ssize_t)
        bind(self.user, 'DestroyWindow', [W.HWND], W.BOOL)
        bind(self.user, 'LoadImageW', [W.HINSTANCE, W.LPCWSTR, W.UINT, C.c_int, C.c_int, W.UINT], W.HANDLE)
        bind(self.user, 'LoadIconW', [W.HINSTANCE, C.c_void_p], W.HICON)
        bind(self.user, 'DestroyIcon', [W.HICON], W.BOOL)
        bind(self.user, 'CreatePopupMenu', [], W.HMENU)
        bind(self.user, 'AppendMenuW', [W.HMENU, W.UINT, C.c_size_t, W.LPCWSTR], W.BOOL)
        bind(self.user, 'SetMenuDefaultItem', [W.HMENU, W.UINT, W.UINT], W.BOOL)
        bind(self.user, 'GetCursorPos', [C.POINTER(W.POINT)], W.BOOL)
        bind(self.user, 'SetForegroundWindow', [W.HWND], W.BOOL)
        bind(self.user, 'TrackPopupMenu', [W.HMENU, W.UINT, C.c_int, C.c_int, C.c_int, W.HWND, C.c_void_p], W.UINT)
        bind(self.user, 'DestroyMenu', [W.HMENU], W.BOOL)
        bind(self.user, 'PostMessageW', [W.HWND, W.UINT, W.WPARAM, W.LPARAM], W.BOOL)
        bind(self.user, 'RegisterWindowMessageW', [W.LPCWSTR], W.UINT)
        bind(self.shell, 'Shell_NotifyIconW', [W.DWORD, C.POINTER(NotifyIcon)], W.BOOL)
        self.instance = self.kernel.GetModuleHandleW(None)
        self.class_name = 'XeneonControlTray_' + str(id(self))
        self.taskbar_created = self.user.RegisterWindowMessageW('TaskbarCreated')
        self.proc = self.callback_type(self._window_proc)
        wc = WindowClass()
        wc.proc, wc.instance, wc.name = self.proc, self.instance, self.class_name
        if not self.user.RegisterClassW(C.byref(wc)):
            raise C.WinError(C.get_last_error())
        self.window = self.user.CreateWindowExW(0, self.class_name, 'Xeneon Control tray', 0, 0, 0, 0, 0, None, None, self.instance, None)
        if not self.window:
            self.user.UnregisterClassW(self.class_name, self.instance)
            raise C.WinError(C.get_last_error())
        icon_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'tray.ico'
        self.icon = self.user.LoadImageW(None, str(icon_path), 1, 32, 32, 0x10) if icon_path.exists() else None
        self.owns_icon = bool(self.icon)
        if not self.icon:
            self.icon = self.user.LoadIconW(None, C.c_void_p(32512))
        self.data = NotifyIcon()
        self.data.size, self.data.window, self.data.id = C.sizeof(NotifyIcon), self.window, 1
        self.data.flags, self.data.callback, self.data.icon = 0x87, 0x8001, self.icon
        self.data.tip = 'Xeneon Control - click to open; right-click for Exit'
        if not self._add():
            self.close()
            raise OSError('Windows could not add the system tray icon')
        self.poll_id = self.root.after(30, self._poll)

    def _add(self):
        self.added = bool(self.shell.Shell_NotifyIconW(0, C.byref(self.data)))
        if self.added:
            self.data.version = 4
            self.shell.Shell_NotifyIconW(4, C.byref(self.data))
        return self.added

    def available(self):
        return self.added

    def _window_proc(self, hwnd, message, wparam, lparam):
        # Never call Tk from a ctypes WNDPROC. Windows can invoke this while
        # Tcl is pumping messages with Python's GIL released. Re-entering Tk
        # here causes a fatal PyEval_RestoreThread error on Python 3.14.
        try:
            if not self.closed:
                if message == self.taskbar_created:
                    self.events.put('taskbar-created')
                    return 0
                if message == 0x8001:
                    event = lparam & 0xFFFF
                    if event in (0x400, 0x401):
                        self.events.put('show')
                    elif event == 0x7B:
                        self.events.put('menu')
                    return 0
        except Exception as exc:
            self.error = str(exc)
        return self.user.DefWindowProcW(hwnd, message, wparam, lparam)

    def _poll(self):
        self.poll_id = None
        if self.closed:
            return
        try:
            while not self.closed:
                action = self.events.get_nowait()
                if action == 'show':
                    self.on_show()
                elif action == 'menu':
                    self._menu()
                elif action == 'taskbar-created':
                    if not self._add():
                        self.on_show()
        except queue.Empty:
            pass
        except Exception as exc:
            self.error = str(exc)
            # Keep the application reachable if a menu or shell operation fails.
            self.on_show()
        finally:
            if not self.closed:
                self.poll_id = self.root.after(30, self._poll)

    def _menu(self):
        from ctypes import wintypes as W
        if not self.window:
            return
        menu = self.user.CreatePopupMenu()
        if not menu:
            self.on_show()
            return
        try:
            self.user.AppendMenuW(menu, 0, 1, 'Open Xeneon Control')
            self.user.AppendMenuW(menu, 0x800, 0, None)
            self.user.AppendMenuW(menu, 0, 2, 'Exit')
            self.user.SetMenuDefaultItem(menu, 1, 0)
            point = W.POINT()
            self.user.GetCursorPos(C.byref(point))
            self.user.SetForegroundWindow(self.window)
            choice = self.user.TrackPopupMenu(menu, 0x102, point.x, point.y, 0, self.window, None)
            self.user.PostMessageW(self.window, 0, 0, 0)
            if choice == 1:
                self.on_show()
            elif choice == 2:
                self.on_exit()
        finally:
            self.user.DestroyMenu(menu)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.poll_id is not None:
            self.root.after_cancel(self.poll_id)
            self.poll_id = None
        if self.added:
            self.shell.Shell_NotifyIconW(2, C.byref(self.data))
            self.added = False
        if self.window:
            self.user.DestroyWindow(self.window)
            self.window = None
        if getattr(self, 'owns_icon', False):
            self.user.DestroyIcon(self.icon)
            self.owns_icon = False
        self.user.UnregisterClassW(self.class_name, self.instance)


class LinuxTray:
    def __init__(self, root, on_show, on_exit):
        self.root, self.on_show, self.on_exit = root, on_show, on_exit
        self.events = queue.Queue()
        self.connected = False
        self.closed = False
        self.error = ''
        self.ready = threading.Event()
        self.GLib = self.Gtk = None
        self.thread = threading.Thread(target=self._run, name='tray-indicator', daemon=True)
        self.thread.start()
        self.ready.wait(2)
        root.after(100, self._poll)

    def _run(self):
        try:
            import gi
            gi.require_version('Gtk', '3.0')
            gi.require_version('AyatanaAppIndicator3', '0.1')
            from gi.repository import Gtk, GLib, AyatanaAppIndicator3
            self.Gtk, self.GLib = Gtk, GLib
            if not Gtk.init_check()[0]:
                raise RuntimeError('No display available for the tray')
            indicator = AyatanaAppIndicator3.Indicator.new('xeneon-control', 'video-display', AyatanaAppIndicator3.IndicatorCategory.HARDWARE)
            self.indicator = indicator
            indicator.set_title('Xeneon Control')
            menu = Gtk.Menu()
            for label, action in [('Open Xeneon Control', 'show'), ('Exit', 'exit')]:
                item = Gtk.MenuItem(label=label)
                item.connect('activate', lambda widget, a=action: self.events.put(a))
                menu.append(item)
            menu.show_all()
            indicator.set_menu(menu)
            indicator.connect('connection-changed', lambda obj, connected: self._connected(connected))
            indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
            self.connected = bool(indicator.get_property('connected'))
            self.ready.set()
            if not self.closed:
                Gtk.main()
            indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.PASSIVE)
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.connected = False
            self.ready.set()

    def _connected(self, connected):
        self.connected = bool(connected)
        if not connected and not self.closed:
            self.events.put('show')

    def _poll(self):
        if self.closed:
            return
        try:
            while True:
                action = self.events.get_nowait()
                if action == 'exit':
                    self.on_exit()
                else:
                    self.on_show()
        except queue.Empty:
            pass
        if not self.closed:
            self.root.after(100, self._poll)

    def available(self):
        return self.connected and self.thread.is_alive()

    def close(self):
        self.closed = True
        if self.GLib and self.thread.is_alive():
            self.GLib.idle_add(self.Gtk.main_quit)


def create_tray(root, on_show, on_exit):
    return WindowsTray(root, on_show, on_exit) if sys.platform == 'win32' else LinuxTray(root, on_show, on_exit)
