from concurrent.futures import Future
import unittest
from background_refresh import BackgroundRefresh
from settings import BY_KEY
from xeneon_control import apply_one, related_settings, DemoMonitor

class RefreshTests(unittest.TestCase):
    def test_brightness_edit_does_not_query_other_controls(self):
        class Monitor(DemoMonitor):
            def __init__(self):
                super().__init__()
                self.reads=[]
            def get(self, code, vendor=False):
                self.reads.append((code,vendor))
                return super().get(code,vendor)
        m=Monitor()
        self.assertEqual(apply_one(m,BY_KEY['brightness'],34),(33,34,None))
        self.assertEqual(m.reads,[(0x10,False),(0x10,False)])
        self.assertEqual(related_settings(BY_KEY['brightness']),[])

    def make_scheduler(self):
        class Executor:
            def __init__(self): self.jobs=[]
            def submit(self, work, setting):
                f=Future();self.jobs.append((f,setting));return f
        e=Executor();callbacks=[];received=[];busy=[False]
        bg=BackgroundRefresh(e,lambda delay,fn:callbacks.append(fn),None,
                             lambda s,v,error:received.append((s.key,v,error)),lambda:busy[0])
        return bg,e,callbacks,received,busy

    def test_refresh_queues_one_read_and_pauses_for_foreground(self):
        bg,e,callbacks,received,busy=self.make_scheduler()
        bg.request([BY_KEY['red'],BY_KEY['green'],BY_KEY['blue']])
        self.assertEqual(len(e.jobs),1)
        busy[0]=True
        bg.invalidate()
        e.jobs[0][0].set_result(84)
        callbacks.pop(0)()
        self.assertEqual(received,[])  # A read from before the edit must not win the race.
        self.assertEqual(len(e.jobs),1)
        busy[0]=False;bg.resume()
        self.assertEqual(len(e.jobs),2)
        e.jobs[1][0].set_result(90);callbacks.pop(0)()
        self.assertEqual(received,[('green',90,None)])
        self.assertEqual(len(e.jobs),3)

    def test_exit_drops_pending_background_work(self):
        bg,e,callbacks,received,busy=self.make_scheduler()
        bg.request([BY_KEY['red'],BY_KEY['green']]);bg.close()
        e.jobs[0][0].set_result(84);callbacks.pop(0)()
        self.assertEqual(received,[])
        self.assertEqual(len(e.jobs),1)
        self.assertFalse(bg.pending)

    def test_refresh_errors_do_not_stop_remaining_reads(self):
        bg,e,callbacks,received,busy=self.make_scheduler()
        bg.request([BY_KEY['red'],BY_KEY['green']])
        e.jobs[0][0].set_exception(OSError('Disconnected'));callbacks.pop(0)()
        self.assertEqual(received,[('red',None,'Disconnected')])
        self.assertEqual(len(e.jobs),2)

    def test_native_settle_times_remain_long_for_slow_features(self):
        self.assertEqual(BY_KEY['brightness'].settle_delay(33),.1)
        self.assertEqual(BY_KEY['preset'].settle_delay(3),.25)
        self.assertEqual(BY_KEY['preset'].settle_delay(8),.65)
        self.assertEqual(BY_KEY['freesync'].settle_delay(1),8)

if __name__=='__main__': unittest.main()
