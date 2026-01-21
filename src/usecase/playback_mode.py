"""保存データ再生モード"""
import asyncio
import json
import os
from typing import List, Dict, Optional

from toio import Color

from domain import RecordedFrame
from infrastructure import CubeController, SynthesizerSound, WaveType
from .ui import TOIO_ADDRESSES, start_input_thread

# 各toioの色
TOIO_COLORS = [
    Color(0, 0, 255),    # 青
    Color(255, 0, 0),    # 赤
    Color(0, 255, 0),    # 緑
]


class PlaybackMode:
    """保存データ再生モード"""

    PLAYBACK_POSITION_THRESHOLD = 8
    PLAYBACK_ANGLE_THRESHOLD = 15

    def __init__(self):
        self.controllers: List[CubeController] = []
        self.synths: List[Optional[SynthesizerSound]] = []
        self.frames_data: List[List[RecordedFrame]] = []
        self.wave_types: List[WaveType] = []
        self.quit_event = asyncio.Event()
        self.input_thread = None
        self.toio_count = 0

    async def run(self):
        """メイン実行"""
        # ファイル選択
        filepath = self._select_recording_file()
        if not filepath:
            return

        # データ読み込み
        if not self._load_recording(filepath):
            return

        # toio接続
        await self._connect_all()

        # 再生
        await self._playback_loop()

        # クリーンアップ
        await self._cleanup()

    def _get_recordings_dir(self) -> str:
        """記録ディレクトリのパスを取得"""
        return os.path.join(os.path.dirname(__file__), "..", "..", "data", "recordings")

    def _select_recording_file(self) -> Optional[str]:
        """保存ファイルを選択"""
        recordings_dir = self._get_recordings_dir()

        if not os.path.exists(recordings_dir):
            print("保存データがありません")
            return None

        # JSONファイル一覧を取得
        files = sorted([f for f in os.listdir(recordings_dir) if f.endswith(".json")], reverse=True)
        if not files:
            print("保存データがありません")
            return None

        print("\n" + "=" * 50)
        print("保存データを選択してください")
        print("=" * 50)
        for i, f in enumerate(files[:10], 1):  # 最新10件を表示
            print(f"  {i}: {f}")
        print("=" * 50)

        while True:
            try:
                choice = input(f"番号を入力 (1-{min(len(files), 10)}): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < min(len(files), 10):
                    return os.path.join(recordings_dir, files[idx])
                print("⚠️ 有効な番号を入力してください")
            except ValueError:
                print("⚠️ 数値を入力してください")
            except KeyboardInterrupt:
                print("\nキャンセルされました")
                return None

    def _load_recording(self, filepath: str) -> bool:
        """記録データを読み込み"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.toio_count = data["toio_count"]
            self.frames_data = []
            self.wave_types = []

            wave_type_map = {
                "sine": WaveType.SINE,
                "sawtooth": WaveType.SAWTOOTH,
                "square": WaveType.SQUARE
            }

            for toio_data in data["toios"]:
                frames = [
                    RecordedFrame(
                        x=f["x"],
                        y=f["y"],
                        angle=f["angle"],
                        timestamp=f["timestamp"],
                        speed=f["speed"]
                    )
                    for f in toio_data["frames"]
                ]
                self.frames_data.append(frames)
                self.wave_types.append(wave_type_map.get(toio_data["wave_type"], WaveType.SINE))

            print(f"✅ データ読み込み完了: {self.toio_count}台分")
            for i, frames in enumerate(self.frames_data):
                if frames:
                    print(f"  toio_{i+1}: {len(frames)}フレーム, {frames[-1].timestamp:.1f}秒")
                else:
                    print(f"  toio_{i+1}: データなし")

            return True

        except Exception as e:
            print(f"❌ データ読み込みエラー: {e}")
            return False

    async def _connect_all(self):
        """全toioに接続"""
        print("\n全toioに接続中...")

        for i in range(self.toio_count):
            name = f"toio_{i+1}"
            controller = CubeController(
                address=TOIO_ADDRESSES[i],
                name=name,
                color=TOIO_COLORS[i % len(TOIO_COLORS)],
            )
            self.controllers.append(controller)
            await controller.connect()
            await controller.set_indicator(color=Color(100, 100, 100))

        print(f"✅ {self.toio_count}台のtoioに接続しました")

        # シンセサイザーを初期化
        for i in range(self.toio_count):
            synth = SynthesizerSound(wave_type=self.wave_types[i])
            synth.start()
            self.synths.append(synth)

    async def _playback_loop(self):
        """再生ループ"""
        loop = asyncio.get_event_loop()
        self.input_thread = start_input_thread(self.quit_event, loop)

        print("\n" + "=" * 50)
        print("再生開始！")
        print("  - 'q' を入力して終了")
        print("=" * 50)

        # 各toioの再生タスクを開始
        tasks = []
        for i in range(self.toio_count):
            if self.frames_data[i]:
                task = asyncio.create_task(self._playback_toio(i))
                tasks.append(task)

        # 終了を待つ
        while not self.quit_event.is_set():
            # 全タスクが終了したか確認
            if all(t.done() for t in tasks):
                break
            await asyncio.sleep(0.1)

        # タスクをキャンセル
        for task in tasks:
            if not task.done():
                task.cancel()

    async def _playback_toio(self, index: int):
        """1台のtoioを再生"""
        controller = self.controllers[index]
        synth = self.synths[index]
        frames = self.frames_data[index]

        if not frames:
            return

        while not self.quit_event.is_set():
            # 開始位置に移動
            first = frames[0]
            await controller.set_indicator(color=Color(255, 100, 0))
            await controller.action.move_position(
                x=first.x, y=first.y, angle=first.angle, speed=50
            )

            # 位置到達を待つ
            for _ in range(30):
                if self.quit_event.is_set():
                    return
                pos = await controller.sensing.get_position()
                if pos:
                    dx = abs(pos.x - first.x)
                    dy = abs(pos.y - first.y)
                    if dx < 15 and dy < 15:
                        break
                await asyncio.sleep(0.1)

            if self.quit_event.is_set():
                return

            await controller.set_indicator(color=Color(0, 255, 0))
            synth.unmute()

            # フレーム再生
            event_loop = asyncio.get_event_loop()
            start_time = event_loop.time()
            last_sent_x, last_sent_y, last_sent_angle = None, None, None

            for frame in frames:
                if self.quit_event.is_set():
                    break

                # タイミングを待つ
                while event_loop.time() - start_time < frame.timestamp:
                    if self.quit_event.is_set():
                        break
                    await asyncio.sleep(0.005)

                if self.quit_event.is_set():
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
                    await controller.action.move_position(
                        x=frame.x, y=frame.y, angle=frame.angle, speed=frame.speed
                    )
                    last_sent_x, last_sent_y, last_sent_angle = frame.x, frame.y, frame.angle

                synth.update_position(frame.x, frame.y)

            synth.mute()
            await asyncio.sleep(0.1)

    async def _cleanup(self):
        """クリーンアップ"""
        print("\nクリーンアップ中...")
        self.quit_event.set()

        if self.input_thread and self.input_thread.is_alive():
            self.input_thread.join(timeout=1.0)

        for synth in self.synths:
            if synth:
                synth.stop()

        for controller in self.controllers:
            await controller.disconnect()

        print("✅ 終了しました")
