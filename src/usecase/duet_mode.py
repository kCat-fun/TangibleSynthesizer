"""重奏モード: 指定秒数遅れで追従演奏"""
import asyncio
from typing import Optional

from toio.cube import Color

from infrastructure.toio import CubeController
from infrastructure.audio import SynthesizerSound
from domain.recording import MotionRecorder
from .ui import input_delay_seconds, TOIO_ADDRESSES


class DuetMode:
    """重奏モード: serve_toioの動きをrecive_toioが遅延追従"""

    RECORD_INTERVAL = 0.02  # 記録間隔（秒）= 50Hz
    PLAYBACK_POSITION_THRESHOLD = 5
    PLAYBACK_ANGLE_THRESHOLD = 10

    def __init__(self):
        self.serve_controller: Optional[CubeController] = None
        self.receive_controller: Optional[CubeController] = None
        self.delay_seconds: float = 2.0
        self.button_pressed = asyncio.Event()

        # 再生閾値用
        self.last_sent_x: Optional[int] = None
        self.last_sent_y: Optional[int] = None
        self.last_sent_angle: Optional[int] = None

    async def run(self):
        """メイン実行"""
        print("\n🎶 重奏モードを開始します")

        self.delay_seconds = input_delay_seconds()
        print(f"✅ 遅延時間: {self.delay_seconds}秒")

        try:
            await self._connect()
            await self._run_duet()
        finally:
            await self._cleanup()

    async def _connect(self):
        """toio接続"""
        self.serve_controller = CubeController(TOIO_ADDRESSES[0])
        self.receive_controller = CubeController(TOIO_ADDRESSES[1])

        await self.serve_controller.connect()
        await self.receive_controller.connect()

        # ボタン通知ハンドラを登録
        def button_handler(payload: bytearray):
            if len(payload) >= 2 and payload[0] == 0x01:
                if payload[1] == 0x80:
                    print("🔘 ボタンが押されました！終了します...")
                    self.button_pressed.set()

        await self.serve_controller.cube.api.button.register_notification_handler(button_handler)

        # LED設定（初期状態）
        await asyncio.gather(
            self.serve_controller.set_indicator(),
            self.receive_controller.set_indicator()
        )

    async def _run_duet(self):
        """重奏モード実行"""
        # ====================
        # Phase 1: 初期位置合わせ
        # ====================
        print("\n📍 Phase 1: recive_toioをserve_toioの位置に移動")
        pos = await self.serve_controller.sensing.get_position()
        if pos:
            await self.receive_controller.action.move_position(
                x=pos.x, y=pos.y, angle=pos.angle, speed=100
            )
        await asyncio.sleep(3)

        # 緑LED = 準備完了
        await asyncio.gather(
            self.serve_controller.set_indicator(color=Color(0, 255, 0)),
            self.receive_controller.set_indicator(color=Color(0, 255, 0))
        )
        print("✅ 初期位置合わせ完了")
        await asyncio.sleep(1)

        # ====================
        # Phase 2: 重奏モード開始
        # ====================
        print("\n🎶 Phase 2: 重奏モード")
        print(f"  serve_toioを手で動かしてください")
        print(f"  recive_toioが{self.delay_seconds}秒遅れで追従します")
        print("  LEDボタンを押すと終了")

        # LED設定
        await self.serve_controller.set_indicator(color=Color(0, 100, 255))  # 青 = メイン
        await self.receive_controller.set_indicator(color=Color(255, 100, 0))  # オレンジ = フォロー

        # 両方のtoioで音を鳴らす
        serve_sound = SynthesizerSound()
        receive_sound = SynthesizerSound()
        serve_sound.start()
        receive_sound.start()

        # 記録用のリングバッファ
        recorder = MotionRecorder()
        recorder.start_recording()

        # 磁石検知状態
        serve_magnet_was_detected = False

        loop = asyncio.get_event_loop()
        start_time = loop.time()

        try:
            while not self.button_pressed.is_set():
                current_time = loop.time() - start_time

                # serve_toioの位置を取得・記録
                pos = await self.serve_controller.sensing.get_position()
                magnet_detected = await self.serve_controller.sensing.check_magnet_below()

                if pos:
                    recorder.record_frame(
                        x=pos.x, y=pos.y, angle=pos.angle,
                        magnet_detected=magnet_detected
                    )
                    # serve_toioの音を更新
                    serve_sound.update_position(pos.x, pos.y)

                # 磁石検知で表示（状態変化時のみ）
                if magnet_detected and not serve_magnet_was_detected:
                    print(f"🧲 serve_toio 磁石検出！")
                    await self.serve_controller.set_indicator(color=Color(255, 0, 0))
                elif not magnet_detected and serve_magnet_was_detected:
                    await self.serve_controller.set_indicator(color=Color(0, 100, 255))
                serve_magnet_was_detected = magnet_detected

                # 遅延してrecive_toioを動かす
                frames = recorder.get_frames()
                if frames and current_time >= self.delay_seconds:
                    target_time = current_time - self.delay_seconds

                    # target_timeに最も近いフレームを探す
                    target_frame = None
                    for frame in frames:
                        if frame.timestamp <= target_time:
                            target_frame = frame
                        else:
                            break

                    if target_frame and self._should_move(
                        target_frame.x, target_frame.y, target_frame.angle
                    ):
                        await self.receive_controller.action.move_position(
                            x=target_frame.x, y=target_frame.y,
                            angle=target_frame.angle, speed=target_frame.speed
                        )
                        self.last_sent_x = target_frame.x
                        self.last_sent_y = target_frame.y
                        self.last_sent_angle = target_frame.angle
                        # recive_toioの音を更新（目標位置で）
                        receive_sound.update_position(target_frame.x, target_frame.y)

                await asyncio.sleep(self.RECORD_INTERVAL)
        finally:
            # 音声を停止
            serve_sound.stop()
            receive_sound.stop()
            recorder.stop_recording()

        print("\n✅ 重奏モード終了！")

    def _should_move(self, target_x: int, target_y: int, target_angle: int) -> bool:
        """移動すべきか判定（閾値ベース）"""
        if self.last_sent_x is None:
            return True
        dx = abs(target_x - self.last_sent_x)
        dy = abs(target_y - self.last_sent_y)
        dangle = abs(target_angle - self.last_sent_angle)
        if dangle > 180:
            dangle = 360 - dangle
        return (
            dx > self.PLAYBACK_POSITION_THRESHOLD or
            dy > self.PLAYBACK_POSITION_THRESHOLD or
            dangle > self.PLAYBACK_ANGLE_THRESHOLD
        )

    async def _cleanup(self):
        """クリーンアップ"""
        if self.serve_controller and self.receive_controller:
            await asyncio.gather(
                self.serve_controller.set_indicator(color=Color(0, 255, 0)),
                self.receive_controller.set_indicator(color=Color(0, 255, 0))
            )
            await asyncio.sleep(2)
            await asyncio.gather(
                self.serve_controller.disconnect(),
                self.receive_controller.disconnect()
            )
