"""モード選択画面"""
import os
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Any


class ModeSelectFrame(ttk.Frame):
    """モード選択とモード別設定を行う画面"""

    def __init__(self, parent, on_start: Callable[[int, Dict[str, Any]], None], **kwargs):
        super().__init__(parent, **kwargs)
        self._on_start = on_start
        self._build_ui()

    def _build_ui(self):
        # タイトル
        ttk.Label(self, text="モード選択", font=('', 16, 'bold')).pack(pady=(20, 10))

        # モード選択ラジオボタン
        self._mode_var = tk.IntVar(value=1)
        modes = [
            (1, "ループシーケンサモード（DTM風 - ボタンで記録/再生を制御）"),
            (2, "重奏モード（2秒遅れで追従演奏）"),
            (3, "動作確認モード（座標取得・磁石検知・移動テスト）"),
            (4, "保存データ再生モード（記録したデータを再生）"),
        ]
        radio_frame = ttk.LabelFrame(self, text="モード", padding=10)
        radio_frame.pack(fill='x', padx=20, pady=5)
        for value, text in modes:
            ttk.Radiobutton(
                radio_frame, text=text, variable=self._mode_var, value=value,
                command=self._on_mode_changed
            ).pack(anchor='w', pady=2)

        # モード別設定パネル
        self._config_frame = ttk.LabelFrame(self, text="設定", padding=10)
        self._config_frame.pack(fill='x', padx=20, pady=5)

        # Mode 1: toio台数
        self._toio_count_frame = ttk.Frame(self._config_frame)
        ttk.Label(self._toio_count_frame, text="toio台数:").pack(side='left')
        self._toio_count_var = tk.IntVar(value=3)
        ttk.Spinbox(
            self._toio_count_frame, from_=1, to=3, width=5,
            textvariable=self._toio_count_var
        ).pack(side='left', padx=5)

        # Mode 2: 遅延秒数
        self._delay_frame = ttk.Frame(self._config_frame)
        ttk.Label(self._delay_frame, text="遅延秒数:").pack(side='left')
        self._delay_var = tk.DoubleVar(value=2.0)
        self._delay_scale = ttk.Scale(
            self._delay_frame, from_=0.5, to=10.0,
            variable=self._delay_var, orient='horizontal', length=200
        )
        self._delay_scale.pack(side='left', padx=5)
        self._delay_label = ttk.Label(self._delay_frame, text="2.0秒")
        self._delay_label.pack(side='left')
        self._delay_var.trace_add('write', self._update_delay_label)

        # Mode 4: ファイル選択
        self._file_frame = ttk.Frame(self._config_frame)
        ttk.Label(self._file_frame, text="記録ファイル:").pack(anchor='w')
        self._file_listbox = tk.Listbox(self._file_frame, height=6, width=50)
        self._file_listbox.pack(fill='x', pady=5)
        self._populate_file_list()

        # 開始ボタン
        self._start_btn = ttk.Button(
            self, text="開始", command=self._on_start_clicked,
            style='Accent.TButton'
        )
        self._start_btn.pack(pady=20)

        # 初期表示
        self._on_mode_changed()

    def _on_mode_changed(self):
        """モード変更時に設定パネルを切り替え"""
        # 全て非表示
        for widget in self._config_frame.winfo_children():
            widget.pack_forget()

        mode = self._mode_var.get()
        if mode == 1:
            self._toio_count_frame.pack(fill='x')
        elif mode == 2:
            self._delay_frame.pack(fill='x')
        elif mode == 3:
            ttk.Label(self._config_frame, text="（設定なし）").pack()
        elif mode == 4:
            self._file_frame.pack(fill='x')
            self._populate_file_list()

    def _update_delay_label(self, *args):
        self._delay_label.config(text=f"{self._delay_var.get():.1f}秒")

    def _populate_file_list(self):
        """記録ファイル一覧を取得してリストボックスに表示"""
        self._file_listbox.delete(0, 'end')
        recordings_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "usecase", "..", "..",
            "data", "recordings"
        )
        recordings_dir = os.path.normpath(recordings_dir)
        self._recording_files = []

        if os.path.exists(recordings_dir):
            files = sorted(
                [f for f in os.listdir(recordings_dir) if f.endswith(".json")],
                reverse=True
            )
            for f in files[:10]:
                self._file_listbox.insert('end', f)
                self._recording_files.append(os.path.join(recordings_dir, f))

        if self._file_listbox.size() > 0:
            self._file_listbox.selection_set(0)

    def _on_start_clicked(self):
        """開始ボタン押下"""
        mode = self._mode_var.get()
        config: Dict[str, Any] = {}

        if mode == 1:
            config['toio_count'] = self._toio_count_var.get()
        elif mode == 2:
            config['delay_seconds'] = round(self._delay_var.get(), 1)
        elif mode == 4:
            selection = self._file_listbox.curselection()
            if not selection or not self._recording_files:
                return
            config['filepath'] = self._recording_files[selection[0]]

        self._on_start(mode, config)
