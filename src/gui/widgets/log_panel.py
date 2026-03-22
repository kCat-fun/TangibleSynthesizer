"""ログ表示パネル"""
import tkinter as tk
from tkinter import ttk, scrolledtext


class LogPanel(ttk.LabelFrame):
    """スクロール可能なログ表示ウィジェット"""

    def __init__(self, parent, max_lines=500, **kwargs):
        super().__init__(parent, text="ログ", **kwargs)
        self._text = scrolledtext.ScrolledText(
            self, state='disabled', height=8, wrap='word',
            font=('Consolas', 9)
        )
        self._text.pack(fill='both', expand=True, padx=5, pady=5)
        self._max_lines = max_lines

    def append(self, message: str):
        """メッセージを追加（メインスレッドから呼ぶこと）"""
        self._text.configure(state='normal')
        self._text.insert('end', message + '\n')
        # 行数制限
        line_count = int(self._text.index('end-1c').split('.')[0])
        if line_count > self._max_lines:
            self._text.delete('1.0', f'{line_count - self._max_lines}.0')
        self._text.configure(state='disabled')
        self._text.see('end')

    def clear(self):
        """全メッセージをクリア"""
        self._text.configure(state='normal')
        self._text.delete('1.0', 'end')
        self._text.configure(state='disabled')
