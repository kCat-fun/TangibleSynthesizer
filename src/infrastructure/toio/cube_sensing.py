import asyncio
from typing import TYPE_CHECKING
from dataclasses import dataclass
from toio import *

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
        self._magnet_class = None  # 接続後に初期化

    @property
    def magnet_class(self):
        """MagnetTestClassのインスタンスを取得（遅延初期化）"""
        if self._magnet_class is None and self.cube_controller.cube is not None:
            self._magnet_class = self.MagnetTestClass(self.cube_controller.cube)
        return self._magnet_class
    
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
    
    # def is_magnet_in_contact(self) -> int:
    #     """
    #     磁石の状態を返す（SimpleCube APIと同じ）
        
    #     Returns:
    #         int: 磁石状態（0: 磁石なし, 1-6: 磁石の向き）
    #     """
    #     return self._magnetic_sensor.state
    
    # def get_magnetic_strength(self) -> int:
    #     """磁力の強さを取得"""
    #     return self._magnetic_sensor.strength
    
    # def get_magnetic_force(self) -> tuple:
    #     """磁力の方向を取得 (x, y, z)"""
    #     return (self._magnetic_sensor.x, self._magnetic_sensor.y, self._magnetic_sensor.z)
    
    # def get_is_magnet(self) -> bool:
    #     """磁石が検出されているかを取得（strength値で判定）"""
    #     return self._magnetic_sensor.strength >= self.magnet_threshold
    
    # async def check_magnet_below(self) -> bool:
    #     """キューブの下に磁石があるかをチェック（strength値で判定）"""
    #     return self._magnetic_sensor.strength >= self.magnet_threshold
    
    # # 後方互換性のためのエイリアス
    # async def get_is_hall(self) -> bool:
    #     """磁石が検出されているかを取得（get_is_magnetのエイリアス）"""
    #     return self.get_is_magnet()

    class MagnetTestClass:
        def __init__(self, cube):
            self.cube = cube
            self.mean_state = []
            self.mean_strength = []
            self.mean_x = []
            self.mean_y = []
            self.mean_z = []

        def magnet_notification_handler(self, payload: bytearray, info: NotificationHandlerInfo):
            id_info = Sensor.is_my_data(payload)
            # 磁気センサーデータのみ処理（MotionDetectionDataなどは無視）
            if not hasattr(id_info, 'strength'):
                return
            # print(id_info.strength)
            self.mean_state.append(id_info.state)
            self.mean_strength.append(id_info.strength)
            self.mean_x.append(id_info.x)
            self.mean_y.append(id_info.y)
            self.mean_z.append(id_info.z)

        async def magnet_position_check(self):
            await self.cube.api.configuration.set_magnetic_sensor(MagneticSensorFunction.MagneticForce, 20, MagneticSensorCondition.Always)
            await self.cube.api.sensor.register_notification_handler(self.magnet_notification_handler)
            # await asyncio.sleep(10) # 磁石のデータを集める
            await self.cube.api.sensor.unregister_notification_handler(self.magnet_notification_handler)

            # 磁石が存在しない場合の処理
            if self.mean_x.count(0) > 5 and self.mean_y.count(0) > 5 and self.mean_z.count(0) > 5:
                print("No Magnet Detected")
                return -1

            return 1

        async def magnet_position(self) -> 'MagneticSensorInfo':
            """通知ハンドラを使って磁気センサー情報を取得"""
            # 初回呼び出し時に通知ハンドラを登録
            if not self.mean_state:
                await self.cube.api.configuration.set_magnetic_sensor(
                    MagneticSensorFunction.MagneticForce, 20, MagneticSensorCondition.Always
                )
                await self.cube.api.sensor.register_notification_handler(self.magnet_notification_handler)

            await asyncio.sleep(0.1)  # データ受信を待つ

            # 最新のデータを返す
            return MagneticSensorInfo(
                state=self.mean_state[-1] if self.mean_state else 0,
                strength=self.mean_strength[-1] if self.mean_strength else 0,
                x=self.mean_x[-1] if self.mean_x else 0,
                y=self.mean_y[-1] if self.mean_y else 0,
                z=self.mean_z[-1] if self.mean_z else 0
            )