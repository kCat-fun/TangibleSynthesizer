"""記録フレームデータクラス"""
from dataclasses import dataclass


@dataclass
class RecordedFrame:
    """記録された1フレームのデータ"""
    x: int
    y: int
    angle: int
    timestamp: float  # 記録時刻（相対時間）
    speed: int = 100  # 移動速度（前フレームからの速度）
