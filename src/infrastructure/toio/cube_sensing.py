from typing import TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from infrastructure.toio.cube_controller import CubeController

@dataclass
class Position:
    """位置情報を保持"""
    x: int
    y: int
    angle: int = 0

@dataclass
class MagneticSensorInfo:
    """磁気センサー情報を保持（MagneticSensorDataの属性に対応）"""
    state: int = 0       # 磁石状態 (0: なし, 1-6: 磁石の向き)
    strength: int = 0    # 磁力の強さ
    x: int = 0           # 磁力の方向 (X軸)
    y: int = 0           # 磁力の方向 (Y軸)
    z: int = 0           # 磁力の方向 (Z軸)

# 磁石状態の定数（toio仕様より）
# 0: 磁石なし
# 1-6: 磁石の向きを検出
class MagnetState:
    NO_MAGNET = 0
    MAGNET_DETECTED_MIN = 1
    MAGNET_DETECTED_MAX = 6

# 磁力検出の閾値（strengthがこの値以上で磁石ありと判定）
MAGNET_STRENGTH_THRESHOLD = 1

class CubeSensing:
    def __init__(self, cube_controller: 'CubeController'):
        self.cube_controller = cube_controller
        # MagneticSensorDataの全属性を保持
        self._magnetic_sensor: MagneticSensorInfo = MagneticSensorInfo()
        # 磁力検出の閾値（インスタンスごとに変更可能）
        self.magnet_threshold = MAGNET_STRENGTH_THRESHOLD
    
    def update_magnetic_sensor(self, state: int, strength: int, x: int, y: int, z: int) -> None:
        """磁気センサー情報を更新（通知ハンドラから呼ばれる）"""
        self._magnetic_sensor.state = state
        self._magnetic_sensor.strength = strength
        self._magnetic_sensor.x = x
        self._magnetic_sensor.y = y
        self._magnetic_sensor.z = z
    
    async def get_position(self) -> Position:
        """キューブの位置を取得"""
        try:
            pos_data = await self.cube_controller.cube.api.id_information.read()
            if hasattr(pos_data, 'center'):
                return Position(
                    x=pos_data.center.point.x,
                    y=pos_data.center.point.y,
                    angle=pos_data.center.angle if hasattr(pos_data.center, 'angle') else 0
                )
        except Exception as e:
            if self.cube_controller.logging:
                print(f"位置取得エラー: {e}")
        return None
    
    # 磁気センサー情報取得メソッド
    def get_magnetic_sensor(self) -> MagneticSensorInfo:
        """磁気センサー情報全体を取得"""
        return self._magnetic_sensor
    
    def is_magnet_in_contact(self) -> int:
        """
        磁石の状態を返す（SimpleCube APIと同じ）
        
        Returns:
            int: 磁石状態（0: 磁石なし, 1-6: 磁石の向き）
        """
        return self._magnetic_sensor.state
    
    def get_magnetic_strength(self) -> int:
        """磁力の強さを取得"""
        return self._magnetic_sensor.strength
    
    def get_magnetic_force(self) -> tuple:
        """磁力の方向を取得 (x, y, z)"""
        return (self._magnetic_sensor.x, self._magnetic_sensor.y, self._magnetic_sensor.z)
    
    def get_is_magnet(self) -> bool:
        """磁石が検出されているかを取得（strength値で判定）"""
        return self._magnetic_sensor.strength >= self.magnet_threshold
    
    async def check_magnet_below(self) -> bool:
        """キューブの下に磁石があるかをチェック（strength値で判定）"""
        return self._magnetic_sensor.strength >= self.magnet_threshold
    
    # 後方互換性のためのエイリアス
    async def get_is_hall(self) -> bool:
        """磁石が検出されているかを取得（get_is_magnetのエイリアス）"""
        return self.get_is_magnet()