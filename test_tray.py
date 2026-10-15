"""Native Windows message-path regression; no monitor writes or global input."""
import sys
import time
import unittest
from xeneon_control import gui

@unittest.skipUnless(sys.platform=='win32','Native Windows tray test')
class NativeTrayTests(unittest.TestCase):
    def test_native_notifications_restore_and_menu_exits(self):
        failures=[];restores=[];apps=[]
        def driver(root,app):
            apps.append(app)
            self.assertIsNotNone(app.tray)
            # A deterministic menu selection; all menu creation, notification
            # delivery, queueing, restore and Exit paths remain real.
            app.tray.user.TrackPopupMenu=lambda *args:1
            events=[0x400,0x401,0x7B]*4
            deadline=time.monotonic()+8
            def guarded(callback):
                def invoke():
                    try:
                        self.assertLess(time.monotonic(),deadline)
                        callback()
                    except BaseException as exc:
                        failures.append(exc);app.close()
                return invoke
            def cycle():
                self.assertEqual(root.state(),'normal')
                self.assertFalse(app.closed)
                if not events:
                    # Verify the native context-menu Exit route too.
                    app.tray.user.TrackPopupMenu=lambda *args:2
                    app.hide_to_tray()
                    app.tray.user.PostMessageW(app.tray.window,0x8001,0,(1<<16)|0x7B)
                    root.after(500,guarded(exit_watchdog))
                    return
                app.hide_to_tray()
                self.assertEqual(root.state(),'withdrawn')
                event=events.pop(0)
                self.assertTrue(app.tray.user.PostMessageW(app.tray.window,0x8001,0,(1<<16)|event))
                restores.append(event)
                root.after(100,guarded(cycle))
            def exit_watchdog():
                self.fail('Native tray Exit did not quit')
            root.after(300,guarded(cycle))
        gui(demo=True,_test_driver=driver)
        if failures:raise failures[0]
        self.assertEqual(len(restores),12)
        self.assertTrue(apps[0].closed)
        self.assertFalse(apps[0].tray.available())

if __name__=='__main__':unittest.main()
