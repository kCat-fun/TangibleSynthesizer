"""toio設定パネルウィジェット"""
import tkinter as tk
from tkinter import ttk


# 波形の選択肢
WAVE_OPTIONS = [
    ("sine", "サイン波"),
    ("sawtooth", "のこぎり波"),
    ("square", "矩形波"),
]

WAVE_DISPLAY_NAMES = {k: v for k, v in WAVE_OPTIONS}


class ToioSettingsPanel(ttk.Frame):
    """1台のtoioの設定・状態表示パネル。
    波形タイプと音量を設定可能。
    """

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
        # --- 状態表示エリア ---
        status_frame = ttk.LabelFrame(self, text="状態", padding=8)
        status_frame.pack(fill='x', padx=10, pady=(10, 5))

        self._state_var = tk.StringVar(value="IDLE")
        self._frames_var = tk.StringVar(value="Frames: --")
        self._duration_var = tk.StringVar(value="Duration: --")

        row = ttk.Frame(status_frame)
        row.pack(fill='x')
        ttk.Label(row, text="State:", width=10).pack(side='left')
        ttk.Label(row, textvariable=self._state_var,
                  font=('', 11, 'bold')).pack(side='left')

        row2 = ttk.Frame(status_frame)
        row2.pack(fill='x')
        ttk.Label(row2, textvariable=self._frames_var).pack(side='left', padx=(0, 15))
        ttk.Label(row2, textvariable=self._duration_var).pack(side='left')

        # --- 波形選択エリア ---
        wave_frame = ttk.LabelFrame(self, text="波形タイプ", padding=8)
        wave_frame.pack(fill='x', padx=10, pady=5)

        self._wave_var = tk.StringVar(value=wave_type)
        self._wave_combo = ttk.Combobox(
            wave_frame, 
            textvariable=self._wave_var,
            values=[label for _, label in WAVE_OPTIONS],
            state='readonly',
            width=15
        )
        self._wave_combo.pack(side='left', padx=10)
        # 初期値をセット（内部値→表示名）
        self._wave_combo.set(WAVE_DISPLAY_NAMES.get(wave_type, "サイン波"))
        self._wave_combo.bind('<<ComboboxSelected>>', self._on_wave_combo_changed)

        # --- 音量スライダーエリア ---
        volume_frame = ttk.LabelFrame(self, text="音量", padding=8)
        volume_frame.pack(fill='x', padx=10, pady=5)

        volume_row = ttk.Frame(volume_frame)
        volume_row.pack(fill='x')

        self._volume_var = tk.DoubleVar(value=volume)
        self._volume_scale = ttk.Scale(
            volume_row, from_=0.0, to=1.0,
            variable=self._volume_var, orient='horizontal', length=150
        )
        self._volume_scale.pack(side='left', padx=(0, 10))
        
        self._volume_label = ttk.Label(volume_row, text=f"{int(volume * 100)}%", width=5)
        self._volume_label.pack(side='left')

        self._volume_var.trace_add('write', self._on_volume_scale_changed)

        # --- 将来の拡張エリア（EGパラメータ等） ---
        self._extensions_frame = ttk.Frame(self)
        self._extensions_frame.pack(fill='both', expand=True, padx=10, pady=5)

    @property
    def wave_type(self) -> str:
        """現在選択中の波形タイプ（"sine"/"sawtooth"/"square"）"""
        # 表示名から内部値に変換
        display_name = self._wave_combo.get()
        for value, label in WAVE_OPTIONS:
            if label == display_name:
                return value
        return "sine"

    @property
    def wave_display_name(self) -> str:
        return self._wave_combo.get()

    @property
    def volume(self) -> float:
        """現在の音量（0.0 ~ 1.0）"""
        return self._volume_var.get()

    @property
    def index(self) -> int:
        return self._index

    def set_locked(self, locked: bool):
        """記録/再生中はロック、IDLE時はアンロック"""
        self._locked = locked
        state = 'disabled' if locked else 'readonly'
        self._wave_combo.config(state=state)
        scale_state = 'disabled' if locked else 'normal'
        self._volume_scale.config(state=scale_state)

    def update_state(self, state: str, info: dict):
        """状態を更新"""
        self._state_var.set(state)
        if 'frame_count' in info:
            self._frames_var.set(f"Frames: {info['frame_count']}")
        if 'duration' in info:
            self._duration_var.set(f"Duration: {info['duration']:.1f}s")

        # IDLE以外はロック
        is_idle = state.upper() == "IDLE"
        self.set_locked(not is_idle)

    def _on_wave_combo_changed(self, event=None):
        """波形コンボボックス変更時"""
        if not self._locked and self._on_wave_changed:
            self._on_wave_changed(self._index, self.wave_type)

    def _on_volume_scale_changed(self, *args):
        """音量スライダー変更時"""
        vol = self._volume_var.get()
        self._volume_label.config(text=f"{int(vol * 100)}%")
        if not self._locked and self._on_volume_changed:
            self._on_volume_changed(self._index, vol)
