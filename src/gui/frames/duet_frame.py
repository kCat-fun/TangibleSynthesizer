"""重奏モード GUI画面"""
import asyncio
import tkinter as tk
from tkinter import ttk
from typing import Callable

from gui.async_bridge import AsyncBridge


class DuetFrame(ttk.Frame):
    """重奏モードの操作画面"""

    def __init__(self, parent, bridge: AsyncBridge, log_fn: Callable,
                 quit_event: asyncio.Event, config: dict,
                 on_finished: Callable, status_bar=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._bridge = bridge
        self._log = log_fn
        self._quit_event = quit_event
        self._delay_seconds = config.get('delay_seconds', 2.0)
        self._on_finished = on_finished
        self._status_bar = status_bar
        self._mode = None
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self, text="重奏モード", font=('', 14, 'bold')).pack(pady=10)

        # 設定表示
        info_frame = ttk.LabelFrame(self, text="設定", padding=10)
        info_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(info_frame, text=f"遅延時間: {self._delay_seconds}秒").pack(anchor='w')

        # toio状態
        status_frame = ttk.Frame(self)
        status_frame.pack(fill='x', padx=10, pady=10)

        serve_frame = ttk.LabelFrame(status_frame, text="serve_toio", padding=10)
        serve_frame.pack(side='left', fill='both', expand=True, padx=5)
        self._serve_status = tk.StringVar(value="接続待ち")
        ttk.Label(serve_frame, textvariable=self._serve_status, font=('', 11)).pack()

        receive_frame = ttk.LabelFrame(status_frame, text="recive_toio", padding=10)
        receive_frame.pack(side='left', fill='both', expand=True, padx=5)
        self._receive_status = tk.StringVar(value="接続待ち")
        ttk.Label(receive_frame, textvariable=self._receive_status, font=('', 11)).pack()

        # フェーズ表示
        self._phase_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._phase_var, font=('', 12)).pack(pady=10)

        # 操作説明
        ttk.Label(self, text=(
            "serve_toioを手で動かしてください\n"
            "toioのLEDボタンを押すと終了"
        ), justify='center').pack(pady=5)

        # 停止ボタン
        self._stop_btn = ttk.Button(self, text="停止", command=self._on_stop)
        self._stop_btn.pack(pady=15)

    def start(self):
        from usecase.duet_mode import DuetMode
        self._mode = DuetMode(
            delay_seconds=self._delay_seconds,
            log_callback=self._log,
            quit_event=self._quit_event
        )
        self._bridge.submit(self._run_mode())

    async def _run_mode(self):
        try:
            await self._mode.run()
        except Exception as e:
            self._log(f"Error: {e}")
        finally:
            self._on_finished()

    def _on_stop(self):
        self._quit_event.set()
        if self._mode:
            self._mode.button_pressed.set()
        self._stop_btn.config(state='disabled')
