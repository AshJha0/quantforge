"""Process counters for the K-6 soak and capacity scripts. Standard library only. Holds no financial logic.

`sample(pid)` returns a dict with
  rss_bytes      resident set: VmRSS on Linux, the working set on Windows
  private_bytes  memory the process has committed for itself: RssAnon + swap on Linux, PrivateUsage on Windows
  peak_bytes     high-water mark of the resident set: VmHWM on Linux, PeakWorkingSetSize on Windows
  handles        open file descriptors on Linux, kernel handles on Windows
  threads        threads of the process
or None when the process has gone.

Why two memory figures: Windows trims the working set of a process when it pleases (more so for a low-priority
process), so the working set measures the memory manager as much as the program. Committed private memory only
moves when the program allocates or frees, which is what a leak changes. The soak rule (KR-218) judges
`private_bytes` on Windows and `rss_bytes` on Linux, and both are always written down.
"""

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _QUERY = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION

    class _PMC(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    class _TE32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    _k32.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _k32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(_TE32)]
    _k32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_TE32)]

    def _threads(pid: int) -> int:
        snap = _k32.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
        if not snap or snap == wintypes.HANDLE(-1).value:
            return -1
        try:
            te = _TE32()
            te.dwSize = ctypes.sizeof(_TE32)
            n = 0
            ok = _k32.Thread32First(snap, ctypes.byref(te))
            while ok:
                n += te.th32OwnerProcessID == pid
                ok = _k32.Thread32Next(snap, ctypes.byref(te))
            return n
        finally:
            _k32.CloseHandle(snap)

    def sample(pid: int) -> dict | None:
        h = _k32.OpenProcess(_QUERY, False, pid)
        if not h:
            return None
        try:
            code = wintypes.DWORD()
            if _k32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value != 259:  # STILL_ACTIVE
                return None
            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            if not _k32.K32GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
                return None
            hc = wintypes.DWORD()
            handles = hc.value if _k32.GetProcessHandleCount(h, ctypes.byref(hc)) else -1
            return {
                "rss_bytes": pmc.WorkingSetSize,
                "private_bytes": pmc.PrivateUsage,
                "peak_bytes": pmc.PeakWorkingSetSize,
                "handles": handles,
                "threads": _threads(pid),
            }
        finally:
            _k32.CloseHandle(h)

else:

    def sample(pid: int) -> dict | None:
        try:
            text = Path(f"/proc/{pid}/status").read_text()
            handles = len(os.listdir(f"/proc/{pid}/fd"))
        except OSError:
            return None
        f = {}
        for line in text.splitlines():
            k, _, v = line.partition(":")
            f[k] = v.split()
        if f.get("State", ["Z"])[0] in ("Z", "X"):
            return None
        kib = lambda k: int(f.get(k, ["0"])[0]) * 1024
        return {
            "rss_bytes": kib("VmRSS"),
            "private_bytes": kib("RssAnon") + kib("VmSwap"),
            "peak_bytes": kib("VmHWM"),
            "handles": handles,
            "threads": int(f.get("Threads", ["-1"])[0]),
        }


def judged_key() -> str:
    """The memory figure the soak rule judges on this platform (KR-218, see the module docstring)."""
    return "private_bytes" if sys.platform == "win32" else "rss_bytes"
