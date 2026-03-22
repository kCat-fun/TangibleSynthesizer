"""asyncio-tkinter統合ブリッジ

tkinterのmainloopはメインスレッドで実行し、
asyncioのイベントループはバックグラウンドスレッドで実行する。
"""
import asyncio
import threading
import tkinter as tk
from typing import Callable, Coroutine, Any


class AsyncBridge:
    """バックグラウンドスレッドでasyncioイベントループを管理"""

    def __init__(self, root: tk.Tk):
        self._root = root
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._thread: threading.Thread = threading.Thread(
            target=self._run_loop, daemon=True
        )

    def start(self):
        """バックグラウンドのasyncioイベントループを開始"""
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def submit(self, coro: Coroutine) -> asyncio.Future:
        """GUIスレッドからasyncコルーチンをスケジュール"""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def gui_callback(self, callback: Callable, *args):
        """asyncスレッドからGUIスレッドへのコールバック（スレッドセーフ）"""
        try:
            self._root.after(0, callback, *args)
        except RuntimeError:
            pass  # ウィンドウが閉じられた後

    def stop(self):
        """asyncioイベントループを停止"""
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5.0)
