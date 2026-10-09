"""自己开一条 waveOut 输出流来放音效，需要时提前把声卡/蓝牙耳机叫醒。

蓝牙耳机（还有一些声卡的省电模式）安静一阵后会挂起音频流，下一段声音开头的零点几秒
会被吞掉。点击音效只有 0.1~0.3 秒，整段都会没了，只有连点时耳机已经醒着才听得到。

所以：鼠标靠近挂件时先打开输出流、持续送静音把设备叫醒；点击时把音效直接混进这条流；
离开一段时间后关掉，不会一直占着声卡（也就不会妨碍系统睡眠）。几段音效可以叠着放。
打不开设备时退回 winsound。
"""
from __future__ import annotations

import array
import ctypes
import ctypes.wintypes as wt
import threading
import time
import wave
import winsound

RATE = 22050
CHUNK = 1024  # 每块约 46ms
NBUF = 3

winmm = ctypes.WinDLL("winmm")


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", wt.WORD), ("nChannels", wt.WORD), ("nSamplesPerSec", wt.DWORD),
                ("nAvgBytesPerSec", wt.DWORD), ("nBlockAlign", wt.WORD), ("wBitsPerSample", wt.WORD),
                ("cbSize", wt.WORD)]


class WAVEHDR(ctypes.Structure):
    _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wt.DWORD), ("dwBytesRecorded", wt.DWORD),
                ("dwUser", ctypes.c_size_t), ("dwFlags", wt.DWORD), ("dwLoops", wt.DWORD),
                ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]


HWAVEOUT = ctypes.c_void_p
winmm.waveOutOpen.argtypes = [ctypes.POINTER(HWAVEOUT), wt.UINT, ctypes.POINTER(WAVEFORMATEX), ctypes.c_size_t,
                              ctypes.c_size_t, wt.DWORD]
winmm.waveOutOpen.restype = wt.UINT
for _name in ("waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite"):
    getattr(winmm, _name).argtypes = [HWAVEOUT, ctypes.POINTER(WAVEHDR), wt.UINT]
    getattr(winmm, _name).restype = wt.UINT
winmm.waveOutReset.argtypes = [HWAVEOUT]
winmm.waveOutClose.argtypes = [HWAVEOUT]

WAVE_MAPPER = 0xFFFFFFFF
WHDR_DONE = 0x1


class Audio:
    def __init__(self, log=lambda msg: None) -> None:
        self.log = log
        self.lock = threading.Lock()
        self.voices: list[list] = []  # [采样, 当前位置(负数表示还没到开始时间), 音量]
        self.cache: dict[str, array.array] = {}
        self.awake_until = 0.0
        self.thread: threading.Thread | None = None
        self.broken = False

    def _load(self, path: str) -> array.array:
        if path not in self.cache:
            with wave.open(path, "rb") as w:
                assert w.getframerate() == RATE and w.getnchannels() == 1 and w.getsampwidth() == 2
                self.cache[path] = array.array("h", w.readframes(w.getnframes()))
        return self.cache[path]

    def wake(self, secs: float = 20.0) -> None:
        """保持输出流开着 secs 秒；没开就现在开。"""
        if self.broken:
            return
        with self.lock:
            self.awake_until = max(self.awake_until, time.monotonic() + secs)
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._run, name="clawd-audio", daemon=True)
                self.thread.start()

    def is_warm(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def play(self, path: str, gain: float = 1.0, delay: float = 0.0) -> None:
        if self.broken:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        samples = self._load(path)
        with self.lock:
            self.voices.append([samples, -int(delay * RATE), gain])
        self.wake(20)

    def _mix(self) -> bytes:
        out = [0] * CHUNK
        with self.lock:
            alive = []
            for v in self.voices:
                samples, pos, gain = v
                start = 0
                if pos < 0:  # 还有 -pos 个采样才轮到它
                    if -pos >= CHUNK:
                        v[1] = pos + CHUNK
                        alive.append(v)
                        continue
                    start, pos = -pos, 0
                n = min(CHUNK - start, len(samples) - pos)
                for i in range(n):
                    out[start + i] += samples[pos + i] * gain
                v[1] = pos + n
                if v[1] < len(samples):
                    alive.append(v)
            self.voices = alive
        return array.array("h", (max(-32767, min(32767, int(s))) for s in out)).tobytes()

    def _run(self) -> None:
        fmt = WAVEFORMATEX(1, 1, RATE, RATE * 2, 2, 16, 0)
        hwo = HWAVEOUT()
        err = winmm.waveOutOpen(ctypes.byref(hwo), WAVE_MAPPER, ctypes.byref(fmt), 0, 0, 0)
        if err:
            self.log(f"waveOutOpen failed: {err}, falling back to winsound")
            self.broken = True
            return
        bufs = [ctypes.create_string_buffer(CHUNK * 2) for _ in range(NBUF)]
        hdrs = [WAVEHDR(ctypes.cast(b, ctypes.c_void_p), CHUNK * 2, 0, 0, 0, 0, None, 0) for b in bufs]
        for h in hdrs:
            winmm.waveOutPrepareHeader(hwo, ctypes.byref(h), ctypes.sizeof(WAVEHDR))
        written = [False] * NBUF
        try:
            while True:
                for i, h in enumerate(hdrs):
                    if not written[i] or h.dwFlags & WHDR_DONE:
                        data = self._mix()
                        ctypes.memmove(bufs[i], data, len(data))
                        h.dwFlags &= ~WHDR_DONE
                        winmm.waveOutWrite(hwo, ctypes.byref(h), ctypes.sizeof(WAVEHDR))
                        written[i] = True
                time.sleep(0.01)
                with self.lock:
                    idle = not self.voices and time.monotonic() > self.awake_until
                if idle:
                    break
        except Exception as e:  # noqa: BLE001 —— 后台线程出错不能把挂件带走
            self.log(f"audio thread: {e!r}")
        finally:
            winmm.waveOutReset(hwo)
            for h in hdrs:
                winmm.waveOutUnprepareHeader(hwo, ctypes.byref(h), ctypes.sizeof(WAVEHDR))
            winmm.waveOutClose(hwo)
