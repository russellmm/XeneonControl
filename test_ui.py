"""GUI regression test. On a headless Linux host, run with xvfb-run."""
import time
import unittest
from unittest.mock import patch
from settings import BY_KEY
from xeneon_control import gui

class UiTests(unittest.TestCase):
    def test_edit_fields_stay_current_while_related_reads_run(self):
        failures=[];checks=[];deadline=time.monotonic()+8
        def driver(root,app):
            def protect(work):
                def checked():
                    try:
                        self.assertLess(time.monotonic(),deadline,'UI operation timed out')
                        work()
                    except BaseException as exc:
                        failures.append(exc);app.close()
                return checked
            def wait_ready():
                if app.monitor is None or app.busy:
                    root.after(10,protect(wait_ready));return
                row=app.rows_by_key['preset'];row['variable'].set('sRGB')
                app.apply(BY_KEY['preset'],3)
                self.assertIs(app.rows_by_key['preset'],row)
                self.assertEqual(row['variable'].get(),'sRGB')
                root.after(10,protect(check_preset))
            def check_preset():
                if app.busy:
                    root.after(10,protect(check_preset));return
                self.assertEqual(app.values['preset'],3)
                self.assertEqual(app.rows_by_key['preset']['variable'].get(),'sRGB')
                self.assertTrue(app.background.active or app.background.pending)
                checks.append('preset updated before dependent refresh finished')
                row=app.rows_by_key['brightness'];row['variable'].set(34)
                app.apply(BY_KEY['brightness'],34)
                self.assertIs(app.rows_by_key['brightness'],row)
                self.assertEqual(row['variable'].get(),34)
                root.after(10,protect(check_brightness))
            def check_brightness():
                if app.busy:
                    root.after(10,protect(check_brightness));return
                self.assertEqual(app.values['brightness'],34)
                self.assertEqual(app.rows_by_key['brightness']['variable'].get(),34)
                app.show('Color')
                row=app.rows_by_key['red'];row['variable'].set(96)
                app.receive_background(BY_KEY['red'],85,None)
                self.assertEqual(row['variable'].get(),96,'Background refresh overwrote an unsaved edit')
                checks.append('foreground brightness and unsaved edits preserved')
                app.show('Information')
                self.assertEqual(app.firmware_version, '0.08')
                self.assertIn('Firmware version: 0.08', app.rows.winfo_children()[0].cget('text'))
                app.close()
            root.after(10,protect(wait_ready))
        with patch('tray.create_tray',return_value=None):
            gui(demo=True,_test_driver=driver)
        if failures: raise failures[0]
        self.assertEqual(len(checks),2)

if __name__=='__main__': unittest.main()
