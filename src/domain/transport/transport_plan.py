
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class TransportStep:
    """1回の移動ステップを表す"""
    toio_x: int          # toioの移動先X座標
    toio_y: int          # toioの移動先Y座標
    toio_angle: int      # toioの初期角度
    rotate_angle: int    # 回転角度（正:時計回り、負:反時計回り）
    object_start: Tuple[int, int]  # オブジェクトの開始位置
    object_end: Tuple[int, int]    # オブジェクトの終了位置（予測）

class TransportPlan:
    def __init__(self, radius: int, max_rotate_angle: int = 45):
        """
        Args:
            radius: てこモジュールの棒の長さ（toio中心から棒先端まで）
            max_rotate_angle: 1回の回転で許容する最大角度
        """
        self.steps: List[TransportStep] = []
        self.radius = radius
        self.max_rotate_angle = max_rotate_angle
        self.current_object_position: Optional[Tuple[int, int]] = None
        self.target_position: Optional[Tuple[int, int]] = None
    
    def set_target(self, x: int, y: int):
        """目標位置を設定"""
        self.target_position = (x, y)
    
    def set_current_object_position(self, x: int, y: int):
        """オブジェクトの現在位置を設定"""
        self.current_object_position = (x, y)

    def calculate_plan(self) -> List[TransportStep]:
        """
        オブジェクトを目標位置まで移動させるための計画を計算
        
        Returns:
            TransportStepのリスト
        """
        if self.current_object_position is None or self.target_position is None:
            raise ValueError("オブジェクト位置と目標位置を設定してください")
        
        
        
        return self.steps

    def _calculate_next_step(self, object_pos: Tuple[int, int], target_pos: Tuple[int, int]) -> Optional[TransportStep]:
        """
        次の移動ステップを計算
        
        オブジェクトを目標方向に押すために、toioを配置する位置と回転角度を決定
        """
        

    def calculate_move_object_position(self, toio_x: int, toio_y: int, bar_angle: int, rotate_angle: int) -> Tuple[int, int]:
        """
        回転後のオブジェクト位置を計算
        
        Args:
            toio_x: toioのX座標
            toio_y: toioのY座標
            bar_angle: 棒の現在の角度（toioから見た棒の向き）
            rotate_angle: 回転角度
            
        Returns:
            回転後のオブジェクト位置 (x, y)
        """
        new_angle = bar_angle + rotate_angle
        rad_angle = math.radians(new_angle)
        move_x = toio_x + int(self.radius * math.cos(rad_angle))
        move_y = toio_y + int(self.radius * math.sin(rad_angle))
        return (move_x, move_y)

    def _normalize_angle(self, angle: float) -> float:
        """角度を-180〜180の範囲に正規化"""
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle

    def get_plan(self) -> List[TransportStep]:
        """計画されたステップを取得"""
        return self.steps
    
    def print_plan(self):
        """計画を表示"""
        print(f"=== 移動計画 ===")
        print(f"開始位置: {self.current_object_position}")
        print(f"目標位置: {self.target_position}")
        print(f"ステップ数: {len(self.steps)}")
        print()
        for i, step in enumerate(self.steps):
            print(f"Step {i+1}:")
            print(f"  toio移動先: ({step.toio_x}, {step.toio_y}), 角度: {step.toio_angle}°")
            print(f"  回転角度: {step.rotate_angle}°")
            print(f"  オブジェクト: {step.object_start} → {step.object_end}")
            print()
        