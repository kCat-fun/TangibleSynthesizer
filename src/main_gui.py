"""toio 音楽プログラム - GUIエントリーポイント"""
import sys
import os
import tkinter as tk

# srcディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(__file__))

from gui.app import ToioMusicApp


def main():
    root = tk.Tk()
    app = ToioMusicApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
