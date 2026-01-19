"""動き記録モジュール"""
import asyncio
import math
from typing import List, Optional

from .frame import RecordedFrame


class MotionRecorder:
    """動きを記録するクラス"""
    # toioの速度範囲（APIの仕様: 10-2560、実用範囲は10-100程度）
    MIN_SPEED = 50
    MAX_SPEED = 100

    def __init__(self, position_threshold: int = 5, angle_threshold: int = 10):
        self.frames: List[RecordedFrame] = []
        self.start_time: float = 0
        self.is_recording: bool = False
        self.last_position: Optional[tuple] = None  # (x, y, timestamp)
        # 停止判定の閾値（この値以下の変化は無視）
        self.position_threshold = position_threshold  # 位置の許容誤差（ピクセル）
        self.angle_threshold = angle_threshold        # 角度の許容誤差（度）

    def _normalize_angle_diff(self, angle1: int, angle2: int) -> int:
        """角度の差を0-180の範囲に正規化"""
        diff = abs(angle1 - angle2)
        if diff > 180:
            diff = 360 - diff
        return diff

    def _is_significant_change(self, x: int, y: int, angle: int) -> bool:
        """前フレームから有意な変化があるかを判定"""
        if not self.frames:
            return True  # 最初のフレームは常に記録

        last = self.frames[-1]
        dx = abs(x - last.x)
        dy = abs(y - last.y)
        dangle = self._normalize_angle_diff(angle, last.angle)

        return dx > self.position_threshold or dy > self.position_threshold or dangle > self.angle_threshold

    def start_recording(self):
        """記録を開始"""
        self.frames.clear()
        self.start_time = asyncio.get_event_loop().time()
        self.is_recording = True
        self.last_position = None
        print("📹 記録開始")

    def _calculate_speed(self, x: int, y: int, timestamp: float) -> int:
        """
        前フレームからの距離と時間から速度を計算
        Returns: toio API用の速度値（50-100）
        """
        if self.last_position is None:
            return self.MAX_SPEED  # 最初のフレームはデフォルト速度

        last_x, last_y, last_time = self.last_position

        # 距離を計算（ピクセル）
        distance = math.sqrt((x - last_x) ** 2 + (y - last_y) ** 2)

        # 時間差を計算（秒）
        dt = timestamp - last_time
        if dt <= 0:
            return self.MAX_SPEED

        # 速度を計算（ピクセル/秒）
        velocity = distance / dt

        # toioの速度にマッピング
        # 実測値に基づく換算: velocity ≈ speed * 2.5 (調整済み)
        speed = int(velocity / 2.5)

        # 範囲内に制限
        speed = max(self.MIN_SPEED, min(self.MAX_SPEED, speed))

        return speed

    def record_frame(self, x: int, y: int, angle: int):
        """1フレーム記録（有意な変化がある場合のみ）"""
        if not self.is_recording:
            return

        # 有意な変化がない場合はスキップ
        if not self._is_significant_change(x, y, angle):
            return

        timestamp = asyncio.get_event_loop().time() - self.start_time

        # 速度を計算
        speed = self._calculate_speed(x, y, timestamp)

        frame = RecordedFrame(x=x, y=y, angle=angle, timestamp=timestamp, speed=speed)
        self.frames.append(frame)

        # 現在位置を保存（次フレームの速度計算用）
        self.last_position = (x, y, timestamp)

    def stop_recording(self):
        """記録を停止"""
        self.is_recording = False
        print(f"⏹ 記録停止 | {len(self.frames)}フレーム記録")

    def get_frames(self) -> List[RecordedFrame]:
        """記録されたフレームを取得"""
        return self.frames

    def get_duration(self) -> float:
        """記録の長さを取得（秒）"""
        if self.frames:
            return self.frames[-1].timestamp
        return 0.0
