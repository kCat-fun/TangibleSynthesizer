"""ループシーケンサモード GUI画面"""
import asyncio
import tkinter as tk
from tkinter import ttk
from typing import Callable, List

from gui.async_bridge import AsyncBridge
from gui.widgets.toio_settings_panel import ToioSettingsPanel

# デフォルトの波形タイプ
DEFAULT_WAVE_TYPES = ["sine", "sawtooth", "square"]


class LoopSequencerFrame(ttk.Frame):
    """ループシーケンサモードの操作画面"""

    def __init__(self, parent, bridge: AsyncBridge, log_fn: Callable,
                 quit_event: asyncio.Event, config: dict,
                 on_finished: Callable, status_bar=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._bridge = bridge
        self._log = log_fn
        self._quit_event = quit_event
        self._toio_count = config.get('toio_count', 3)
        self._on_finished = on_finished
        self._status_bar = status_bar
        self._mode = None
        self._toio_panels: List[ToioSettingsPanel] = []
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self, text="ループシーケンサモード", font=('', 14, 'bold')).pack(pady=10)

        # タブを使用してtoioごとの設定を表示
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill='both', expand=True, padx=10, pady=5)

        for i in range(self._toio_count):
            wave_type = DEFAULT_WAVE_TYPES[i % len(DEFAULT_WAVE_TYPES)]
            panel = ToioSettingsPanel(
                self._notebook,
                index=i,
                wave_type=wave_type,
                volume=1.0,
                on_wave_changed=self._on_wave_changed,
                on_volume_changed=self._on_volume_changed
            )
            self._notebook.add(panel, text=f"toio_{i+1}")
            self._toio_panels.append(panel)

        # 操作説明
        info_frame = ttk.LabelFrame(self, text="操作方法", padding=10)
        info_frame.pack(fill='x', padx=10, pady=10)
        instructions = (
            "toioのボタンを押す -> 記録開始（赤LED）\n"
            "もう一度ボタン -> 記録終了、待機（黄LED）\n"
            "待機中にボタン -> ループ再生開始（緑LED）\n"
            "再生中にボタン -> 一時停止（黄LED）\n"
            "一時停止中にボタン -> 再記録開始"
        )
        ttk.Label(info_frame, text=instructions, justify='left').pack(anchor='w')

        # 停止ボタン
        self._stop_btn = ttk.Button(self, text="停止", command=self._on_stop)
        self._stop_btn.pack(pady=15)

    def _on_wave_changed(self, index: int, wave_type: str):
        """波形タイプ変更時のコールバック"""
        if self._mode:
            self._bridge.submit(self._mode.set_wave_type(index, wave_type))
        self._log(f"toio_{index+1} 波形タイプ変更: {wave_type}")

    def _on_volume_changed(self, index: int, volume: float):
        """音量変更時のコールバック"""
        if self._mode:
            self._bridge.submit(self._mode.set_volume(index, volume))

    def _on_state_change(self, index: int, state_name: str, info: dict):
        """モードクラスからの状態変更コールバック（asyncスレッドから呼ばれる）"""
        def update():
            if index < len(self._toio_panels):
                self._toio_panels[index].update_state(state_name, info)
            if self._status_bar:
                self._status_bar.set_toio_state(index, state_name)
        self._bridge.gui_callback(update)

    def start(self):
        """モード実行開始"""
        from usecase.loop_sequencer import LoopSequencerMode
        from infrastructure.audio import WaveType

        # 現在の設定を取得
        wave_types = []
        volumes = []
        wave_type_map = {
            "sine": WaveType.SINE,
            "sawtooth": WaveType.SAWTOOTH,
            "square": WaveType.SQUARE
        }
        for panel in self._toio_panels:
            wave_types.append(wave_type_map.get(panel.wave_type, WaveType.SINE))
            volumes.append(panel.volume)

        self._mode = LoopSequencerMode(
            toio_count=self._toio_count,
            log_callback=self._log,
            quit_event=self._quit_event,
            state_callback=self._on_state_change,
            wave_types=wave_types,
            volumes=volumes
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
        self._stop_btn.config(state='disabled')
