"""ループシーケンサモード"""
import asyncio
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Callable

from toio import Color

from domain import ToioLoopState, ToioLooper, MotionRecorder
from infrastructure import CubeController, SynthesizerSound, WaveType
from .ui import TOIO_ADDRESSES, start_input_thread

# 各toioの色
TOIO_COLORS = [
    Color(0, 0, 255),    # 青
    Color(255, 0, 0),    # 赤
    Color(0, 255, 0),    # 緑
    Color(255, 255, 0),  # 黄
    Color(255, 0, 255),  # マゼンタ
    Color(0, 255, 255),  # シアン
]

# 各toioの波形タイプ
TOIO_WAVE_TYPES = [
    WaveType.SINE,      # toio1: サイン波
    WaveType.SAWTOOTH,  # toio2: のこぎり波
    WaveType.SQUARE,    # toio3: 矩形波
]


class LoopSynchronizer:
    """全toioのループ同期を管理"""

    def __init__(self):
        self.loopers: List[ToioLooper] = []
        self.max_loop_duration: float = 0
        self._loop_start_event = asyncio.Event()
        self._ready_count = 0
        self._lock = asyncio.Lock()

    def set_loopers(self, loopers: List[ToioLooper]):
        """管理するloopersを設定"""
        self.loopers = loopers

    def update_max_duration(self):
        """PLAYINGのtoioから最長ループを計算"""
        playing = [l for l in self.loopers if l.state == ToioLoopState.PLAYING]
        if playing:
            self.max_loop_duration = max(l.get_duration() for l in playing)
        else:
            self.max_loop_duration = 0

    async def mark_ready(self, looper: ToioLooper):
        """ループ完了を報告"""
        async with self._lock:
            looper.is_ready_for_next_loop = True
            self._ready_count += 1

            # 全PLAYINGが準備完了したか確認
            playing = [l for l in self.loopers if l.state == ToioLoopState.PLAYING]
            ready = [l for l in playing if l.is_ready_for_next_loop]

            if len(ready) == len(playing) and len(playing) > 0:
                # 全員準備完了 → 最長ループを更新して開始合図
                self.update_max_duration()
                for l in playing:
                    l.is_ready_for_next_loop = False
                self._ready_count = 0
                self._loop_start_event.set()

    async def wait_for_loop_start(self, looper: ToioLooper) -> bool:
        """次のループ開始まで待機"""
        # 自分だけがPLAYINGなら待たない
        playing = [l for l in self.loopers if l.state == ToioLoopState.PLAYING]
        if len(playing) <= 1:
            return True

        # 自分が準備完了でなければまず報告
        if not looper.is_ready_for_next_loop:
            await self.mark_ready(looper)

        # 開始合図を待つ
        await self._loop_start_event.wait()
        self._loop_start_event.clear()
        return True

    def reset(self):
        """同期状態をリセット"""
        self._ready_count = 0
        self._loop_start_event.clear()
        for l in self.loopers:
            l.is_ready_for_next_loop = False


class LoopSequencerMode:
    """DTM風ループシーケンサモード"""

    RECORD_INTERVAL = 0.02  # 記録間隔 (50Hz)
    PLAYBACK_POSITION_THRESHOLD = 5
    PLAYBACK_ANGLE_THRESHOLD = 10

    def __init__(self, toio_count: int,
                 log_callback: Optional[Callable[[str], None]] = None,
                 quit_event: Optional[asyncio.Event] = None,
                 state_callback: Optional[Callable[[int, str, dict], None]] = None,
                 wave_types: Optional[List[WaveType]] = None,
                 volumes: Optional[List[float]] = None):
        self.toio_count = toio_count
        self.controllers: List[CubeController] = []
        self.loopers: List[ToioLooper] = []
        self.button_events: Dict[int, asyncio.Event] = {}
        self.quit_event = quit_event or asyncio.Event()
        self.synchronizer = LoopSynchronizer()
        self.input_thread = None
        self._log = log_callback or print
        self._state_callback = state_callback
        self._gui_mode = log_callback is not None
        self._wave_types = wave_types or [
            TOIO_WAVE_TYPES[i % len(TOIO_WAVE_TYPES)] for i in range(toio_count)
        ]
        self._volumes = volumes or [1.0] * toio_count

    def _notify_state(self, looper: ToioLooper, info: Optional[dict] = None):
        """状態変更をGUIに通知"""
        if self._state_callback:
            state_name = looper.state.value.upper() if hasattr(looper.state, 'value') else str(looper.state)
            self._state_callback(looper.index, state_name, info or {})

    async def set_wave_type(self, index: int, wave_type: str):
        """波形タイプを動的に変更"""
        wave_type_map = {
            "sine": WaveType.SINE,
            "sawtooth": WaveType.SAWTOOTH,
            "square": WaveType.SQUARE
        }
        if index < len(self._wave_types):
            self._wave_types[index] = wave_type_map.get(wave_type, WaveType.SINE)
        if index < len(self.loopers) and self.loopers[index].synth:
            self.loopers[index].synth.set_wave_type(self._wave_types[index])

    async def set_volume(self, index: int, volume: float):
        """音量を動的に変更"""
        if index < len(self._volumes):
            self._volumes[index] = max(0.0, min(1.0, volume))
        if index < len(self.loopers) and self.loopers[index].synth:
            self.loopers[index].synth.set_max_volume(self._volumes[index])

    async def run(self):
        """メイン実行"""
        await self._connect_all()
        await self._setup_button_handlers()
        await self._main_loop()
        await self._cleanup()

    async def _connect_all(self):
        """全toioに接続"""
        self._log("=" * 50)
        self._log("ループシーケンサモードを開始します")
        self._log("=" * 50)

        # toioコントローラーを作成
        for i in range(self.toio_count):
            name = f"toio_{i+1}"
            controller = CubeController(
                address=TOIO_ADDRESSES[i],
                name=name,
                color=TOIO_COLORS[i % len(TOIO_COLORS)],
            )
            self.controllers.append(controller)

        # 接続
        self._log("全toioに接続中...")
        for controller in self.controllers:
            await controller.connect()
            await controller.set_indicator(color=Color(100, 100, 100))
        self._log(f"{self.toio_count}台のtoioに接続しました")

        # ToioLooperを作成
        for i, ctrl in enumerate(self.controllers):
            self.loopers.append(ToioLooper(ctrl, i))

        # 波形の割り当てを表示
        wave_names = {WaveType.SINE: "サイン波", WaveType.SAWTOOTH: "のこぎり波", WaveType.SQUARE: "矩形波"}
        self._log("波形の割り当て:")
        for i in range(self.toio_count):
            wave_type = TOIO_WAVE_TYPES[i % len(TOIO_WAVE_TYPES)]
            self._log(f"  toio_{i+1}: {wave_names[wave_type]}")

        self.synchronizer.set_loopers(self.loopers)

    async def _setup_button_handlers(self):
        """ボタンハンドラを設定"""
        for i, looper in enumerate(self.loopers):
            self.button_events[i] = asyncio.Event()

            def make_handler(idx: int):
                def handler(payload: bytearray):
                    if len(payload) >= 2 and payload[0] == 0x01 and payload[1] == 0x80:
                        self.button_events[idx].set()
                return handler

            await looper.controller.cube.api.button.register_notification_handler(make_handler(i))

    async def _main_loop(self):
        """メインループ"""
        # GUIモードではstdinスレッドを起動しない
        if not self._gui_mode:
            loop = asyncio.get_event_loop()
            self.input_thread = start_input_thread(self.quit_event, loop)

        self._log("=" * 50)
        self._log("準備完了！")
        self._log("=" * 50)
        self._log("操作方法:")
        self._log("  - toioのボタンを押す -> 記録開始（赤LED）")
        self._log("  - toioを手で動かして音を作成")
        self._log("  - もう一度ボタンを押す -> 記録終了、待機（黄LED）")
        self._log("  - 待機中にボタンを押す -> ループ再生開始（緑LED）")
        self._log("  - 再生中にボタンを押す -> 一時停止（黄LED）")
        self._log("  - 一時停止中にボタンを押す -> 再記録開始")
        if not self._gui_mode:
            self._log("  - 終了するには 'q' を入力してEnter")
        self._log("=" * 50)

        try:
            while not self.quit_event.is_set():
                # ボタンイベント処理
                for i, event in self.button_events.items():
                    if event.is_set():
                        event.clear()
                        await self._handle_button_press(self.loopers[i])

                # RECORDING中のtoioの位置を記録
                for looper in self.loopers:
                    if looper.state == ToioLoopState.RECORDING and looper.recorder:
                        await self._record_position(looper)

                await asyncio.sleep(self.RECORD_INTERVAL)

        except KeyboardInterrupt:
            self._log("Ctrl+Cで中断されました")

    async def _record_position(self, looper: ToioLooper):
        """位置を記録"""
        pos = await looper.controller.sensing.get_position()
        current_time = asyncio.get_event_loop().time()

        if pos:
            # 位置検出できた
            if not looper.is_position_valid and looper.position_lost_time is not None:
                lost_duration = current_time - looper.position_lost_time
                looper.recorder.start_time += lost_duration
                looper.position_lost_time = None
                # toio3は磁石検知時のみ音を鳴らすのでここではunmuteしない
                if looper.synth and looper.index != 2:
                    looper.synth.unmute()

            looper.is_position_valid = True
            looper.recorder.record_frame(x=pos.x, y=pos.y, angle=pos.angle)
            if looper.synth:
                looper.synth.update_position(pos.x, pos.y)

                # toio3は磁石検知時に0.1秒だけ音を鳴らす
                if looper.index == 2:
                    sensor = await looper.controller.sensing.magnet_class.magnet_position()
                    magnet_detected = sensor.state > 0 or sensor.strength > 0

                    # 磁石検知の立ち上がりエッジで音を開始
                    if magnet_detected and not looper.was_magnet_detected:
                        looper.magnet_sound_until = current_time + 0.1
                        looper.synth.unmute()

                    looper.was_magnet_detected = magnet_detected

                    # 0.1秒経過したらミュート
                    if looper.magnet_sound_until and current_time >= looper.magnet_sound_until:
                        looper.synth.mute()
                        looper.magnet_sound_until = None
        else:
            # 位置検出できなかった
            if looper.is_position_valid:
                looper.position_lost_time = current_time
                looper.is_position_valid = False
                if looper.synth:
                    looper.synth.mute()

    async def _handle_button_press(self, looper: ToioLooper):
        """ボタン押下時の状態遷移処理"""
        if looper.state == ToioLoopState.IDLE:
            if any(l.state == ToioLoopState.RECORDING for l in self.loopers if l != looper):
                self._log(f"他のtoioが記録中です")
                return
            await self._start_recording(looper)

        elif looper.state == ToioLoopState.RECORDING:
            await self._stop_recording(looper)

        elif looper.state == ToioLoopState.WAITING:
            await self._start_playback(looper)

        elif looper.state == ToioLoopState.PLAYING:
            await self._pause_looper(looper)

        elif looper.state == ToioLoopState.PAUSED:
            if any(l.state == ToioLoopState.RECORDING for l in self.loopers if l != looper):
                self._log(f"他のtoioが記録中です")
                return
            await self._start_recording(looper)

    async def _start_recording(self, looper: ToioLooper):
        """録音開始（0.5秒のカウントダウン後）"""
        # 準備中表示
        await looper.controller.set_indicator(color=Color(255, 255, 0))  # 黄色
        self._log(f"{looper.controller.name} 0.5秒後に記録開始...")
        await asyncio.sleep(0.5)

        # 記録開始
        looper.state = ToioLoopState.RECORDING
        await looper.controller.set_indicator(color=Color(255, 0, 0))  # 赤

        looper.recorder = MotionRecorder()
        looper.recorder.start_recording()
        looper.reset_for_recording()

        if looper.synth is None:
            wave_type = self._wave_types[looper.index] if looper.index < len(self._wave_types) else TOIO_WAVE_TYPES[looper.index % len(TOIO_WAVE_TYPES)]
            volume = self._volumes[looper.index] if looper.index < len(self._volumes) else 1.0
            looper.synth = SynthesizerSound(wave_type=wave_type, max_volume=volume)
            looper.synth.start()
        # toio3は磁石検知時のみ音を鳴らすのでここではunmuteしない
        if looper.index != 2:
            looper.synth.unmute()

        self._log(f"{looper.controller.name} 記録開始 - toioを手で動かしてください")
        self._notify_state(looper)

    async def _stop_recording(self, looper: ToioLooper):
        """録音終了して待機状態へ"""
        if looper.recorder:
            looper.recorder.stop_recording()
            looper.frames = looper.recorder.get_frames()

        if looper.synth:
            looper.synth.mute()

        if len(looper.frames) < 2:
            self._log(f"{looper.controller.name} 記録が短すぎます。やり直してください。")
            looper.state = ToioLoopState.IDLE
            await looper.controller.set_indicator(color=Color(100, 100, 100))
            self._notify_state(looper)
            return

        looper.state = ToioLoopState.WAITING
        await looper.controller.set_indicator(color=Color(255, 255, 0))
        self._log(f"{looper.controller.name} 記録完了 ({len(looper.frames)}フレーム, {looper.get_duration():.1f}秒) - ボタンを押すとループ再生開始")
        self._notify_state(looper, {
            'frame_count': len(looper.frames),
            'duration': looper.get_duration()
        })

    async def _start_playback(self, looper: ToioLooper):
        """ループ再生開始"""
        looper.state = ToioLoopState.PLAYING
        looper.stop_event.clear()
        looper.play_task = asyncio.create_task(self._playback_task(looper))
        self._log(f"{looper.controller.name} ループ再生開始")
        self._notify_state(looper, {
            'frame_count': len(looper.frames),
            'duration': looper.get_duration()
        })

    async def _pause_looper(self, looper: ToioLooper):
        """ループ再生を一時停止"""
        looper.state = ToioLoopState.PAUSED
        looper.stop_event.set()

        if looper.play_task:
            try:
                await asyncio.wait_for(looper.play_task, timeout=2.0)
            except asyncio.TimeoutError:
                looper.play_task.cancel()
            looper.play_task = None

        if looper.synth:
            looper.synth.mute()

        self.synchronizer.update_max_duration()
        await looper.controller.set_indicator(color=Color(255, 255, 0))
        self._log(f"{looper.controller.name} 一時停止 - もう一度押すと再記録")
        self._notify_state(looper)

    async def _playback_task(self, looper: ToioLooper):
        """ループ再生タスク（同期なしで独立して再生）"""
        while not looper.stop_event.is_set():
            if looper.state != ToioLoopState.PLAYING:
                await asyncio.sleep(0.1)
                continue

            if len(looper.frames) < 2:
                await asyncio.sleep(0.1)
                continue

            if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
                continue

            # 開始位置に移動
            first = looper.frames[0]
            await looper.controller.set_indicator(color=Color(255, 100, 0))
            await looper.controller.action.move_position(
                x=first.x, y=first.y, angle=first.angle, speed=50
            )

            # 位置に到達するまで待つ
            for _ in range(30):
                if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
                    break
                pos = await looper.controller.sensing.get_position()
                if pos:
                    dx = abs(pos.x - first.x)
                    dy = abs(pos.y - first.y)
                    if dx < 15 and dy < 15:
                        break
                await asyncio.sleep(0.1)

            if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
                continue

            await looper.controller.set_indicator(color=Color(0, 255, 0))

            # フレーム再生
            # toio3は磁石検知時のみ音を鳴らすのでここではunmuteしない
            if looper.synth and looper.index != 2:
                looper.synth.unmute()

            event_loop = asyncio.get_event_loop()
            start_time = event_loop.time()
            last_sent_x, last_sent_y, last_sent_angle = None, None, None

            for frame in looper.frames:
                if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
                    break

                # タイミングを待つ
                while event_loop.time() - start_time < frame.timestamp:
                    if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
                        break
                    await asyncio.sleep(0.005)

                if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
                    break

                # 有意な移動がある場合のみ移動指示
                should_move = True
                if last_sent_x is not None:
                    dx = abs(frame.x - last_sent_x)
                    dy = abs(frame.y - last_sent_y)
                    dangle = abs(frame.angle - last_sent_angle)
                    if dangle > 180:
                        dangle = 360 - dangle
                    should_move = (dx > self.PLAYBACK_POSITION_THRESHOLD or
                                   dy > self.PLAYBACK_POSITION_THRESHOLD or
                                   dangle > self.PLAYBACK_ANGLE_THRESHOLD)

                if should_move:
                    await looper.controller.action.move_position(
                        x=frame.x, y=frame.y, angle=frame.angle, speed=frame.speed
                    )
                    last_sent_x, last_sent_y, last_sent_angle = frame.x, frame.y, frame.angle

                if looper.synth:
                    looper.synth.update_position(frame.x, frame.y)

                    # toio3は磁石検知時に0.1秒だけ音を鳴らす
                    if looper.index == 2:
                        current_time = event_loop.time()
                        sensor = await looper.controller.sensing.magnet_class.magnet_position()
                        magnet_detected = sensor.state > 0 or sensor.strength > 0

                        # 磁石検知の立ち上がりエッジで音を開始
                        if magnet_detected and not looper.was_magnet_detected:
                            looper.magnet_sound_until = current_time + 0.1
                            looper.synth.unmute()

                        looper.was_magnet_detected = magnet_detected

                        # 0.1秒経過したらミュート
                        if looper.magnet_sound_until and current_time >= looper.magnet_sound_until:
                            looper.synth.mute()
                            looper.magnet_sound_until = None

            if looper.synth:
                looper.synth.mute()

            # ループ終了 - 少し待ってから次のループへ
            await asyncio.sleep(0.1)

    def _save_recording(self) -> Optional[str]:
        """記録データをJSONファイルに保存"""
        # 記録データがあるtoioを確認
        toios_with_data = [l for l in self.loopers if len(l.frames) > 0]
        if not toios_with_data:
            return None

        # 保存ディレクトリを作成
        save_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "recordings")
        os.makedirs(save_dir, exist_ok=True)

        # ファイル名を生成
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.json"
        filepath = os.path.join(save_dir, filename)

        # データを構築
        data = {
            "created_at": datetime.now().isoformat(),
            "toio_count": self.toio_count,
            "toios": []
        }

        for looper in self.loopers:
            toio_data = {
                "index": looper.index,
                "name": looper.controller.name,
                "wave_type": TOIO_WAVE_TYPES[looper.index % len(TOIO_WAVE_TYPES)].value,
                "frames": [
                    {
                        "x": f.x,
                        "y": f.y,
                        "angle": f.angle,
                        "timestamp": f.timestamp,
                        "speed": f.speed
                    }
                    for f in looper.frames
                ]
            }
            data["toios"].append(toio_data)

        # ファイルに保存
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return filepath

    async def _cleanup(self):
        """クリーンアップ"""
        self._log("クリーンアップ中...")
        self.quit_event.set()

        if self.input_thread and self.input_thread.is_alive():
            self.input_thread.join(timeout=1.0)

        for looper in self.loopers:
            looper.stop_event.set()
            if looper.play_task:
                try:
                    await asyncio.wait_for(looper.play_task, timeout=2.0)
                except asyncio.TimeoutError:
                    looper.play_task.cancel()
            if looper.synth:
                looper.synth.stop()

        # 記録データを保存
        saved_path = self._save_recording()
        if saved_path:
            self._log(f"記録データを保存しました: {saved_path}")

        for controller in self.controllers:
            await controller.disconnect()

        self._log("終了しました")
