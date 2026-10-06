"""kill_tree stops a worker together with the processes it started."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.processes import kill, kill_tree, spawn_options

CHILD = r'''
import subprocess, sys, time
grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open(sys.argv[1], "w").write(str(grandchild.pid))
time.sleep(120)
'''


def alive(pid):
    if os.name == 'nt':
        out = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True, text=True,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A killed but unreaped child of ours would still answer; it is not ours here.
    return True


class KillTree(unittest.TestCase):
    def test_grandchild_is_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'pid'
            process = subprocess.Popen([sys.executable, '-c', CHILD, str(marker)], **spawn_options(group=True))
            try:
                for _ in range(200):
                    if marker.exists() and marker.read_text():
                        break
                    time.sleep(.05)
                grandchild = int(marker.read_text())
                self.assertTrue(alive(grandchild))
                kill_tree(process)
                self.assertIsNotNone(process.poll())
                for _ in range(100):
                    if not alive(grandchild):
                        break
                    time.sleep(.05)
                self.assertFalse(alive(grandchild), 'grandchild survived kill_tree')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_finished_process_is_left_alone(self):
        process = subprocess.Popen([sys.executable, '-c', 'pass'], **spawn_options())
        process.wait()
        kill_tree(process)
        kill(process)
        self.assertEqual(process.returncode, 0)


if __name__ == '__main__':
    unittest.main()
