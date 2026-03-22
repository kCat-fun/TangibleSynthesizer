"""メインアプリケーションウィンドウ"""
import asyncio
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Any, Optional

from gui.async_bridge import AsyncBridge
from gui.widgets.log_panel import LogPanel
from gui.widgets.status_bar import StatusBar
from gui.frames.mode_select_frame import ModeSelectFrame
from gui.frames.loop_sequencer_frame import LoopSequencerFrame
from gui.frames.duet_frame import DuetFrame
from gui.frames.debug_frame import DebugFrame
from gui.frames.playback_frame import PlaybackFrame


class ToioMusicApp:
    """メインアプリケーション"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("toio 音楽プログラム")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)

        # asyncio bridge
        self.bridge = AsyncBridge(root)
        self.bridge.start()

        # 共有quit event
        self._quit_event = asyncio.Event()

        # レイアウト
        main_frame = ttk.Frame(root)
        main_frame.pack(fill='both', expand=True)

        self._content_frame = ttk.Frame(main_frame)
        self._content_frame.pack(fill='both', expand=True)

        self.log_panel = LogPanel(main_frame)
        self.log_panel.pack(fill='x', padx=5, pady=(0, 5))

        self.status_bar = StatusBar(root)
        self.status_bar.pack(fill='x', side='bottom')

        self._current_frame: Optional[ttk.Frame] = None
        self._mode_running = False

        # 初期画面
        self._show_mode_select()

    def log(self, message: str):
        """スレッドセーフなログ出力"""
        self.bridge.gui_callback(self.log_panel.append, message)

    def _show_mode_select(self):
        """モード選択画面を表示"""
        self._clear_content()
        self._quit_event = asyncio.Event()
        self._mode_running = False
        self.status_bar.set_status("モード選択")
        self.status_bar.reset()

        frame = ModeSelectFrame(self._content_frame, on_start=self._on_mode_start)
        frame.pack(fill='both', expand=True)
        self._current_frame = frame

    def _on_mode_start(self, mode: int, config: Dict[str, Any]):
        """モード開始"""
        if self._mode_running:
            return
        self._mode_running = True
        self._clear_content()
        self._quit_event = asyncio.Event()
        self.log_panel.clear()

        mode_names = {
            1: "ループシーケンサ",
            2: "重奏モード",
            3: "動作確認",
            4: "保存データ再生"
        }
        self.status_bar.set_status(mode_names.get(mode, ""))

        frame_cls = {
            1: LoopSequencerFrame,
            2: DuetFrame,
            3: DebugFrame,
            4: PlaybackFrame,
        }.get(mode)

        if frame_cls:
            frame = frame_cls(
                self._content_frame,
                bridge=self.bridge,
                log_fn=self.log,
                quit_event=self._quit_event,
                config=config,
                on_finished=self._on_mode_finished,
                status_bar=self.status_bar
            )
            frame.pack(fill='both', expand=True)
            self._current_frame = frame
            frame.start()

    def _on_mode_finished(self):
        """モード終了時のコールバック"""
        self.bridge.gui_callback(self._show_mode_select)

    def _clear_content(self):
        for widget in self._content_frame.winfo_children():
            widget.destroy()
        self._current_frame = None

    def on_close(self):
        """ウィンドウ閉じるハンドラ"""
        if self._mode_running:
            if not messagebox.askokcancel("終了", "モード実行中です。終了しますか？"):
                return
        self._quit_event.set()
        self.bridge.stop()
        self.root.destroy()
