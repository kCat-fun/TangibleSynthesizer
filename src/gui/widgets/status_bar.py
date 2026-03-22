"""ステータスバー"""
import tkinter as tk
from tkinter import ttk


class StatusBar(ttk.Frame):
    """下部ステータスバー"""

    def __init__(self, parent, max_toios=3, **kwargs):
        super().__init__(parent, **kwargs)
        self._status_label = ttk.Label(self, text="Ready", width=20, anchor='w')
        self._status_label.pack(side='left', padx=10)

        ttk.Separator(self, orient='vertical').pack(side='left', fill='y', padx=5)

        self._toio_labels = []
        for i in range(max_toios):
            label = ttk.Label(self, text=f"toio{i+1}: --", relief='sunken', width=15)
            label.pack(side='left', padx=3)
            self._toio_labels.append(label)

    def set_status(self, text: str):
        self._status_label.config(text=text)

    def set_toio_state(self, index: int, state: str):
        if 0 <= index < len(self._toio_labels):
            self._toio_labels[index].config(text=f"toio{index+1}: {state}")

    def reset(self):
        self._status_label.config(text="Ready")
        for label in self._toio_labels:
            label.config(text=label.cget('text').split(':')[0] + ': --')
