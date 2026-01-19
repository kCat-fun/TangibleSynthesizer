"""toioループ状態の定義"""
from enum import Enum


class ToioLoopState(Enum):
    """toioのループ状態"""
    IDLE = "idle"           # 待機中（未記録）
    RECORDING = "recording" # 記録中
    PLAYING = "playing"     # ループ再生中
    PAUSED = "paused"       # 一時停止中
