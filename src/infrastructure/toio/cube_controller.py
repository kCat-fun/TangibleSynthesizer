from toio.scanner import BLEScanner
from toio.cube import ToioCoreCube
from toio import IndicatorParam, Color
from toio.cube.api.configuration import MagneticSensorFunction, MagneticSensorCondition
from toio.cube.api.sensor import Sensor, MagneticSensorData

from infrastructure.toio.cube_action import CubeAction
from infrastructure.toio.cube_sensing import CubeSensing

class CubeController:
    def __init__(self, address: str, name: str, color: Color, max_toio: int = 2, logging: bool = False):
        self.address = address
        self.name = name
        self.color = color
        self.cube = None
        self.max_toio = max_toio
        self.logging = logging

        self.action = CubeAction(self)
        self.sensing = CubeSensing(self)
    
    async def connect(self):
        if self.logging:
            print(f"🔍 {self.name}をスキャン中...")
        device_list = await BLEScanner.scan(num=self.max_toio)
        target_device = None
        for device in device_list:
            addr = device.device.address.lower()
            if self.logging:
                print("検出:", addr)
            if addr == self.address.lower():
                target_device = device
                break

        if not target_device:
            if self.logging:
                print(f"❌ 指定したアドレスのtoio({self.name})が見つかりません")
            raise RuntimeError(f"❌ 指定したアドレスのtoio({self.name})が見つかりません")

        self.cube = ToioCoreCube(target_device.interface)
        await self.cube.connect()
        
        # 接続安定化のため少し待機
        import asyncio
        await asyncio.sleep(0.5)
        
        # センサー通知ハンドラを登録（設定前に登録する必要がある）
        await self.cube.api.sensor.register_notification_handler(
            self._sensor_notification_handler
        )
        
        # 磁気センサーを有効化（MagneticForce: 磁力検出モード - より詳細な情報を取得）
        await self.cube.api.configuration.set_magnetic_sensor(
            function_type=MagneticSensorFunction.MagneticForce,  # MagnetStateからMagneticForceに変更
            interval_ms=5,  # 最小間隔（20ms x 1 = 20ms）
            condition=MagneticSensorCondition.Always  # 常に通知
        )
        
        # 磁気センサー情報を要求（初期値を取得するため）
        await self.cube.api.sensor.request_magnetic_sensor_information()
        
        if self.logging:
            print(f"✅ {self.name} 接続完了")
    
    def _sensor_notification_handler(self, payload: bytearray) -> None:
        """センサー通知を処理するハンドラ"""
        sensor_info = Sensor.is_my_data(payload)
        
        if isinstance(sensor_info, MagneticSensorData):
            # MagneticSensorDataの全属性を保存
            self.sensing.update_magnetic_sensor(
                state=sensor_info.state,
                strength=sensor_info.strength,
                x=sensor_info.x,
                y=sensor_info.y,
                z=sensor_info.z
            )

    async def disconnect(self, color: Color = None):
        if color and self.cube:
            self.color = color
        if self.cube:
            if self.logging:
                print(f"🔌 {self.name} 切断中...")
            await self.cube.disconnect()
            if self.logging:
                print(f"👋 {self.name} 完了しました")

    async def set_indicator(self, color: Color = None):
        if color:
            self.color = color
        if self.cube:
            if self.logging:
                print(f"💡 {self.name} LED設定中...")
            indicator_param = IndicatorParam(0, self.color)
            await self.cube.api.indicator.turn_on(indicator_param)
            if self.logging:
                print(f"✅ {self.name} LED設定完了")
