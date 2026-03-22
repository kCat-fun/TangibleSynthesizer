"""動作確認モード GUI画面"""
import asyncio
import tkinter as tk
from tkinter import ttk
from typing import Callable

from gui.async_bridge import AsyncBridge


class DebugFrame(ttk.Frame):
    """動作確認モードの操作画面"""

    def __init__(self, parent, bridge: AsyncBridge, log_fn: Callable,
                 quit_event: asyncio.Event, config: dict,
                 on_finished: Callable, status_bar=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._bridge = bridge
        self._log = log_fn
        self._quit_event = quit_event
        self._on_finished = on_finished
        self._status_bar = status_bar
        self._mode = None
        self._sub_stop_event = None
        self._connected = False
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self, text="動作確認モード", font=('', 14, 'bold')).pack(pady=10)

        # サブモード選択ボタン
        btn_frame = ttk.LabelFrame(self, text="機能選択", padding=10)
        btn_frame.pack(fill='x', padx=10, pady=5)

        self._btn_position = ttk.Button(btn_frame, text="座標取得",
                                         command=lambda: self._start_sub("position"))
        self._btn_position.pack(side='left', padx=5, expand=True, fill='x')

        self._btn_magnet = ttk.Button(btn_frame, text="磁石検知",
                                       command=lambda: self._start_sub("magnet"))
        self._btn_magnet.pack(side='left', padx=5, expand=True, fill='x')

        self._btn_notify = ttk.Button(btn_frame, text="notification磁石",
                                       command=lambda: self._start_sub("notify"))
        self._btn_notify.pack(side='left', padx=5, expand=True, fill='x')

        self._btn_move = ttk.Button(btn_frame, text="座標移動",
                                     command=lambda: self._start_sub("move"))
        self._btn_move.pack(side='left', padx=5, expand=True, fill='x')

        # リアルタイム表示エリア
        display_frame = ttk.LabelFrame(self, text="ステータス", padding=10)
        display_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self._display_var = tk.StringVar(value="サブモードを選択してください")
        ttk.Label(display_frame, textvariable=self._display_var,
                  font=('Consolas', 12), justify='left').pack(anchor='w')

        # 座標移動用入力（初期非表示）
        self._move_frame = ttk.Frame(display_frame)
        ttk.Label(self._move_frame, text="X:").grid(row=0, column=0, padx=2)
        self._x_var = tk.StringVar(value="150")
        ttk.Entry(self._move_frame, textvariable=self._x_var, width=6).grid(row=0, column=1, padx=2)
        ttk.Label(self._move_frame, text="Y:").grid(row=0, column=2, padx=2)
        self._y_var = tk.StringVar(value="250")
        ttk.Entry(self._move_frame, textvariable=self._y_var, width=6).grid(row=0, column=3, padx=2)
        ttk.Label(self._move_frame, text="角度:").grid(row=0, column=4, padx=2)
        self._angle_var = tk.StringVar(value="0")
        ttk.Entry(self._move_frame, textvariable=self._angle_var, width=6).grid(row=0, column=5, padx=2)
        self._move_btn = ttk.Button(self._move_frame, text="移動",
                                     command=self._on_move_clicked)
        self._move_btn.grid(row=0, column=6, padx=10)

        # ボタンエリア
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill='x', padx=10, pady=10)

        self._sub_stop_btn = ttk.Button(bottom_frame, text="サブモード停止",
                                         command=self._stop_sub, state='disabled')
        self._sub_stop_btn.pack(side='left', padx=5)

        self._finish_btn = ttk.Button(bottom_frame, text="モード終了",
                                       command=self._on_finish)
        self._finish_btn.pack(side='right', padx=5)

    def start(self):
        """接続開始"""
        from usecase.debug_mode import DebugMode
        self._mode = DebugMode(
            log_callback=self._log,
            quit_event=self._quit_event,
            gui_mode=True
        )
        self._bridge.submit(self._connect())

    async def _connect(self):
        try:
            await self._mode._connect()
            self._connected = True
            self._log("toio接続完了")
        except Exception as e:
            self._log(f"接続エラー: {e}")

    def _start_sub(self, sub_mode: str):
        if not self._connected:
            self._log("toioが接続されていません")
            return
        if self._sub_stop_event and not self._sub_stop_event.is_set():
            self._log("先にサブモードを停止してください")
            return

        self._sub_stop_event = asyncio.Event()
        self._sub_stop_btn.config(state='normal')
        self._move_frame.pack_forget()

        if sub_mode == "position":
            self._log("座標取得モード開始")
            self._bridge.submit(self._run_position_check())
        elif sub_mode == "magnet":
            self._log("磁石検知モード開始")
            self._bridge.submit(self._run_magnet_check())
        elif sub_mode == "notify":
            self._log("notification磁石検知モード開始")
            self._bridge.submit(self._run_notify_magnet())
        elif sub_mode == "move":
            self._log("座標移動モード開始")
            self._move_frame.pack(pady=10)
            self._display_var.set("座標を入力して「移動」を押してください")

    async def _run_position_check(self):
        try:
            last_pos = None
            while not self._sub_stop_event.is_set() and not self._quit_event.is_set():
                pos = await self._mode.controller.sensing.get_position()
                if pos:
                    if last_pos is None or pos.x != last_pos.x or pos.y != last_pos.y:
                        text = f"X: {pos.x:4d}  Y: {pos.y:4d}  角度: {pos.angle:3d}"
                        self._bridge.gui_callback(self._display_var.set, text)
                        last_pos = pos
                else:
                    self._bridge.gui_callback(
                        self._display_var.set, "位置検出できません（マット外）")
                    last_pos = None
                await asyncio.sleep(0.1)
        except Exception as e:
            self._log(f"エラー: {e}")
        self._bridge.gui_callback(self._sub_stop_btn.config, state='disabled')

    async def _run_magnet_check(self):
        try:
            last_state = None
            while not self._sub_stop_event.is_set() and not self._quit_event.is_set():
                await self._mode.controller.cube.api.sensor.request_magnetic_sensor_information()
                sensor = self._mode.controller.sensing.get_magnetic_sensor()
                magnet_detected = sensor.state > 0 or sensor.strength > 0
                if magnet_detected != last_state:
                    if magnet_detected:
                        text = f"磁石検知！ (state={sensor.state}, strength={sensor.strength})"
                    else:
                        text = "磁石なし"
                    self._bridge.gui_callback(self._display_var.set, text)
                    last_state = magnet_detected
                await asyncio.sleep(0.05)
        except Exception as e:
            self._log(f"エラー: {e}")
        self._bridge.gui_callback(self._sub_stop_btn.config, state='disabled')

    async def _run_notify_magnet(self):
        try:
            last_state = None
            while not self._sub_stop_event.is_set() and not self._quit_event.is_set():
                sensor = await self._mode.controller.sensing.magnet_class.magnet_position()
                magnet_detected = sensor.state > 0 or sensor.strength > 0
                if magnet_detected != last_state:
                    if magnet_detected:
                        text = f"磁石検知！ (state={sensor.state}, strength={sensor.strength})"
                    else:
                        text = "磁石なし"
                    self._bridge.gui_callback(self._display_var.set, text)
                    last_state = magnet_detected
                await asyncio.sleep(0.05)
        except Exception as e:
            self._log(f"エラー: {e}")
        self._bridge.gui_callback(self._sub_stop_btn.config, state='disabled')

    def _on_move_clicked(self):
        if not self._connected:
            return
        try:
            x = int(self._x_var.get())
            y = int(self._y_var.get())
            angle = int(self._angle_var.get()) % 360
            if not (45 <= x <= 455) or not (45 <= y <= 455):
                self._log("座標は45-455の範囲で入力してください")
                return
            self._bridge.submit(self._move_to(x, y, angle))
        except ValueError:
            self._log("数値を入力してください")

    async def _move_to(self, x: int, y: int, angle: int):
        try:
            self._log(f"移動中... -> X={x}, Y={y}, 角度={angle}")
            await self._mode.controller.action.move_position(x=x, y=y, angle=angle, speed=50)
            for _ in range(50):
                await asyncio.sleep(0.1)
                pos = await self._mode.controller.sensing.get_position()
                if pos:
                    dx = abs(pos.x - x)
                    dy = abs(pos.y - y)
                    if dx < 10 and dy < 10:
                        break
            pos = await self._mode.controller.sensing.get_position()
            if pos:
                self._log(f"到着: X={pos.x}, Y={pos.y}, 角度={pos.angle}")
                self._bridge.gui_callback(
                    self._display_var.set,
                    f"X: {pos.x:4d}  Y: {pos.y:4d}  角度: {pos.angle:3d}"
                )
            else:
                self._log("位置を確認できません")
        except Exception as e:
            self._log(f"移動エラー: {e}")

    def _stop_sub(self):
        if self._sub_stop_event:
            self._sub_stop_event.set()
        self._sub_stop_btn.config(state='disabled')
        self._display_var.set("サブモード停止")

    def _on_finish(self):
        if self._sub_stop_event:
            self._sub_stop_event.set()
        self._quit_event.set()
        if self._connected:
            self._bridge.submit(self._cleanup())
        else:
            self._on_finished()

    async def _cleanup(self):
        try:
            await self._mode._cleanup()
        except Exception:
            pass
        self._on_finished()
