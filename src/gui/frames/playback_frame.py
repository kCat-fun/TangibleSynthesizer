"""保存データ再生モード GUI画面"""
import asyncio
import json
import os
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from gui.async_bridge import AsyncBridge


# 波形の選択肢
WAVE_OPTIONS = [
    ("sine", "サイン波"),
    ("sawtooth", "のこぎり波"),
    ("square", "矩形波"),
]

WAVE_DISPLAY_NAMES = {k: v for k, v in WAVE_OPTIONS}


class PlaybackToioPanel(ttk.Frame):
    """再生モード用のtoio設定パネル（音量とシンプルな状態表示）"""

    def __init__(self, parent, index: int, wave_type: str = "sine",
                 volume: float = 1.0,
                 on_wave_changed=None, on_volume_changed=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._index = index
        self._on_wave_changed = on_wave_changed
        self._on_volume_changed = on_volume_changed
        self._locked = False
        self._build_ui(wave_type, volume)

    def _build_ui(self, wave_type: str, volume: float):
        # --- 波形表示 ---
        wave_frame = ttk.LabelFrame(self, text="波形タイプ", padding=8)
        wave_frame.pack(fill='x', padx=10, pady=(10, 5))

        self._wave_var = tk.StringVar(value=wave_type)
        self._wave_combo = ttk.Combobox(
            wave_frame, 
            textvariable=self._wave_var,
            values=[label for _, label in WAVE_OPTIONS],
            state='readonly',
            width=15
        )
        self._wave_combo.pack(side='left', padx=10)
        self._wave_combo.set(WAVE_DISPLAY_NAMES.get(wave_type, "サイン波"))
        self._wave_combo.bind('<<ComboboxSelected>>', self._on_wave_combo_changed)

        # --- 音量スライダー ---
        volume_frame = ttk.LabelFrame(self, text="音量", padding=8)
        volume_frame.pack(fill='x', padx=10, pady=5)

        volume_row = ttk.Frame(volume_frame)
        volume_row.pack(fill='x')

        self._volume_var = tk.DoubleVar(value=volume)
        self._volume_scale = ttk.Scale(
            volume_row, from_=0.0, to=1.0,
            variable=self._volume_var, orient='horizontal', length=200
        )
        self._volume_scale.pack(side='left', padx=(0, 10))

        self._volume_label = ttk.Label(volume_row, text=f"{int(volume * 100)}%", width=5)
        self._volume_label.pack(side='left')

        self._volume_var.trace_add('write', self._on_volume_scale_changed)

        # --- 状態表示 ---
        status_frame = ttk.LabelFrame(self, text="状態", padding=8)
        status_frame.pack(fill='x', padx=10, pady=5)

        self._status_var = tk.StringVar(value="読み込み中...")
        ttk.Label(status_frame, textvariable=self._status_var, font=('', 11)).pack()

    @property
    def wave_type(self) -> str:
        """現在選択中の波形タイプ（"sine"/"sawtooth"/"square"）"""
        display_name = self._wave_combo.get()
        for value, label in WAVE_OPTIONS:
            if label == display_name:
                return value
        return "sine"

    @property
    def volume(self) -> float:
        return self._volume_var.get()

    @property
    def index(self) -> int:
        return self._index

    def set_wave_type(self, wave_type: str):
        """波形タイプを設定"""
        self._wave_combo.set(WAVE_DISPLAY_NAMES.get(wave_type, "サイン波"))

    def set_status(self, status: str):
        """状態表示を更新"""
        self._status_var.set(status)

    def _on_wave_combo_changed(self, event=None):
        if self._on_wave_changed:
            self._on_wave_changed(self._index, self.wave_type)

    def _on_volume_scale_changed(self, *args):
        vol = self._volume_var.get()
        self._volume_label.config(text=f"{int(vol * 100)}%")
        if self._on_volume_changed:
            self._on_volume_changed(self._index, vol)


class PlaybackFrame(ttk.Frame):
    """保存データ再生モードの操作画面"""

    def __init__(self, parent, bridge: AsyncBridge, log_fn: Callable,
                 quit_event: asyncio.Event, config: dict,
                 on_finished: Callable, status_bar=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._bridge = bridge
        self._log = log_fn
        self._quit_event = quit_event
        self._filepath = config.get('filepath', '')
        self._on_finished = on_finished
        self._status_bar = status_bar
        self._mode = None
        self._toio_panels: List[PlaybackToioPanel] = []
        self._toio_count = 0
        self._wave_types: List[str] = []
        self._load_file_info()
        self._build_ui()

    def _load_file_info(self):
        """ファイルからtoio数と波形タイプを読み込む"""
        if self._filepath and os.path.exists(self._filepath):
            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._toio_count = data.get("toio_count", 0)
                self._wave_types = []
                for toio_data in data.get("toios", []):
                    self._wave_types.append(toio_data.get("wave_type", "sine"))
            except Exception:
                pass

    def _build_ui(self):
        ttk.Label(self, text="保存データ再生モード", font=('', 14, 'bold')).pack(pady=10)

        # ファイル情報
        filename = os.path.basename(self._filepath) if self._filepath else "未選択"
        info_frame = ttk.LabelFrame(self, text="再生ファイル", padding=10)
        info_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(info_frame, text=filename).pack(anchor='w')

        # タブを使用してtoioごとの設定を表示
        if self._toio_count > 0:
            self._notebook = ttk.Notebook(self)
            self._notebook.pack(fill='both', expand=True, padx=10, pady=5)

            for i in range(self._toio_count):
                wave_type = self._wave_types[i] if i < len(self._wave_types) else "sine"
                panel = PlaybackToioPanel(
                    self._notebook,
                    index=i,
                    wave_type=wave_type,
                    volume=1.0,
                    on_wave_changed=self._on_wave_changed,
                    on_volume_changed=self._on_volume_changed
                )
                self._notebook.add(panel, text=f"toio_{i+1}")
                self._toio_panels.append(panel)
        else:
            # toio情報が読み込めなかった場合
            self._status_var = tk.StringVar(value="読み込み中...")
            ttk.Label(self, textvariable=self._status_var, font=('', 11)).pack(pady=10)

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

    def start(self):
        from usecase.playback_mode import PlaybackMode

        # 現在の音量設定を取得
        volumes = [panel.volume for panel in self._toio_panels] if self._toio_panels else None

        self._mode = PlaybackMode(
            log_callback=self._log,
            quit_event=self._quit_event,
            filepath=self._filepath,
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
