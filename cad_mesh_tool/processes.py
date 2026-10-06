"""Start and stop worker processes together with the processes they start.

Auto workers start variant workers. Stopping an Auto worker therefore has to
stop its whole process tree: on Windows through ``taskkill /T``, elsewhere by
starting the worker as a process-group leader and signalling the group.
"""
import os
import signal
import subprocess


def spawn_options(group=False):
    """Popen keyword arguments for a hidden worker; ``group`` makes it a tree root."""
    if os.name == 'nt':
        return dict(creationflags=subprocess.CREATE_NO_WINDOW)
    return dict(start_new_session=True) if group else {}


def _wait(process, timeout):
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def kill_tree(process, timeout=5):
    """Stop ``process`` and its descendants; a finished process is left alone."""
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            leader = os.getpgid(process.pid) == process.pid
        except (OSError, AttributeError):
            leader = False
        if leader:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
        else:
            process.kill()
    _wait(process, timeout)


def kill(process, timeout=5):
    """Stop one process that starts no children of its own."""
    if process.poll() is not None:
        return
    try:
        process.kill()
    except OSError:
        pass
    _wait(process, timeout)
