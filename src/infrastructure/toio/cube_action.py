import asyncio
from toio.cube.api.motor import TargetPosition, MovementType, RotationOption, Speed
from toio.cube.api.id_information import CubeLocation, Point

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.toio.cube_controller import CubeController

class CubeAction:
    # toioプレイマットの座標範囲
    MIN_X = 45
    MAX_X = 455
    MIN_Y = 45
    MAX_Y = 455

    def __init__(self, cube_controller: 'CubeController'):
        self.cube_controller = cube_controller
    
    def _normalize_angle(self, angle: int) -> int:
        """角度を0〜360の範囲に正規化"""
        angle = angle % 360
        if angle < 0:
            angle += 360
        return angle
    
    def _clamp_position(self, x: int, y: int) -> tuple:
        """座標をプレイマットの範囲内に制限"""
        x = max(self.MIN_X, min(self.MAX_X, x))
        y = max(self.MIN_Y, min(self.MAX_Y, y))
        return x, y

    async def drive(self, left_speed: int, right_speed: int):
        """左右の速度を指定して前進"""
        if self.cube_controller.logging:
            print(f"▶ キューブ({self.cube_controller.name}) 前進開始 | 左:{left_speed} 右:{right_speed}")
        await self.cube_controller.cube.api.motor.motor_control(left_speed, right_speed)
    
    async def stop(self):
        """停止"""
        if self.cube_controller.logging:
            print(f"⏹ キューブ({self.cube_controller.name}) 停止")
        await self.cube_controller.cube.api.motor.motor_control(0, 0)

    async def drive_for_duration(self, left_speed: int, right_speed: int, duration_sec: int):
        """指定した時間だけ前進"""
        if self.cube_controller.logging:
            print(f"▶ キューブ({self.cube_controller.name}) 前進開始 | 左:{left_speed} 右:{right_speed} 時間:{duration_sec}s")
        await self.cube_controller.cube.api.motor.motor_control(left_speed, right_speed)
        await asyncio.sleep(duration_sec)
        await self.stop()
        if self.cube_controller.logging:
                print(f"⏹ キューブ({self.cube_controller.name}) 前進終了")

    async def move_position(self, x: int, y: int, angle: int, speed: int):
        """指定した位置に移動"""
        # 座標と角度を有効な範囲に制限
        x, y = self._clamp_position(x, y)
        angle = self._normalize_angle(angle)
        
        if self.cube_controller.logging:
            print(f"▶ キューブ({self.cube_controller.name}) 指定位置へ移動 | x:{x} y:{y} angle:{angle} speed:{speed}")

        target = TargetPosition(
            cube_location=CubeLocation(
                point=Point(x=x, y=y),
                angle=angle
            ),
            rotation_option=RotationOption.AbsoluteOptimal
        )
        
        # 移動開始
        asyncio.create_task(
            self.cube_controller.cube.api.motor.motor_control_target(
                timeout=60,
                movement_type=MovementType.Linear,
                speed=Speed(max=speed, speed_change_type=2),
                target=target
            )
        )   

        if self.cube_controller.logging:
            print(f"✅ キューブ({self.cube_controller.name}) 指定位置へ到達")

    async def rotate(self, rotate_angle: int, speed: int = 20):
        """指定した角度だけ回転（現在位置を維持）"""
        # 角度を有効な範囲に正規化
        rotate_angle = self._normalize_angle(rotate_angle)
        
        if self.cube_controller.logging:
            print(f"▶ キューブ({self.cube_controller.name}) 回転開始 | 角度:{rotate_angle} speed:{speed}")
        
        # 現在位置を取得
        pos = await self.cube_controller.sensing.get_position()
        if pos is None:
            if self.cube_controller.logging:
                print(f"❌ キューブ({self.cube_controller.name}) 位置取得失敗")
            return
        
        target = TargetPosition(
            cube_location=CubeLocation(
                point=Point(x=pos.x, y=pos.y),
                angle=rotate_angle
            ),
            rotation_option=RotationOption.AbsoluteOptimal
        )
        
        # 回転開始（現在位置で角度だけ変更）
        asyncio.create_task(
            self.cube_controller.cube.api.motor.motor_control_target(
                timeout=30,
                movement_type=MovementType.Linear,
                speed=Speed(max=speed, speed_change_type=2),
                target=target
            )
        )

        if self.cube_controller.logging:
            print(f"✅ キューブ({self.cube_controller.name}) 回転完了 | 角度:{rotate_angle}")