"""toioループ制御モジュール"""
import asyncio
from typing import List, Optional, TYPE_CHECKING

from .state import ToioLoopState
from ..recording.frame import RecordedFrame
from ..recording.recorder import MotionRecorder

if TYPE_CHECKING:
    from infrastructure.toio import CubeController
    from infrastructure.audio import SynthesizerSound


class ToioLooper:
    """各toioの独立したループ制御"""

    def __init__(self, controller: 'CubeController', index: int):
        self.controller = controller
        self.index = index
        self.state = ToioLoopState.IDLE
        self.frames: List[RecordedFrame] = []
        self.synth: Optional['SynthesizerSound'] = None
        self.play_task: Optional[asyncio.Task] = None
        self.stop_event = asyncio.Event()
        self.recorder: Optional[MotionRecorder] = None

        # 位置検出ロスト追跡用
        self.position_lost_time: Optional[float] = None
        self.is_position_valid: bool = True

        # 同期用
        self.is_ready_for_next_loop: bool = False

        # toio3用: 磁石検知トリガー
        self.was_magnet_detected: bool = False
        self.magnet_sound_until: Optional[float] = None  # 音を鳴らす終了時刻

    def get_duration(self) -> float:
        """ループの長さを取得（秒）"""
        if self.frames:
            return self.frames[-1].timestamp
        return 0.0

    def reset_for_recording(self):
        """記録開始前のリセット"""
        self.is_position_valid = True
        self.position_lost_time = None
        self.is_ready_for_next_loop = False
        self.was_magnet_detected = False
        self.magnet_sound_until = None
