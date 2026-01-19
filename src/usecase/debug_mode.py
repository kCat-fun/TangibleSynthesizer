"""動作確認モード"""
import asyncio
from typing import Optional

from toio.cube import Color

from infrastructure.toio import CubeController
from .ui import TOIO_ADDRESSES


class DebugMode:
    """動作確認用モード（1台のtoioを使用）"""

    def __init__(self):
        self.controller: Optional[CubeController] = None

    async def run(self):
        """メイン実行"""
        print("\n" + "=" * 50)
        print("動作確認モード")
        print("=" * 50)

        try:
            await self._connect()
            await self._show_debug_menu()
        finally:
            await self._cleanup()

    async def _connect(self):
        """toio接続"""
        print("\ntoioに接続中...")
        self.controller = CubeController(
            address=TOIO_ADDRESSES[0],
            name="debug_toio",
            color=Color(0, 255, 0)
        )
        await self.controller.connect()
        await self.controller.set_indicator(color=Color(0, 255, 0))  # 緑 = 接続完了
        print("✅ 接続完了")

    async def _show_debug_menu(self):
        """デバッグメニュー表示"""
        while True:
            print("\n" + "-" * 40)
            print("動作確認メニュー")
            print("-" * 40)
            print("  1: 座標取得（リアルタイム表示）")
            print("  2: 磁石検知（リアルタイム表示）")
            print("  3: 座標移動（入力した座標へ移動）")
            print("  q: 終了")
            print("-" * 40)

            try:
                choice = input("選択: ").strip().lower()
                if choice == "1":
                    await self._position_check()
                elif choice == "2":
                    await self._magnet_check()
                elif choice == "3":
                    await self._move_to_position()
                elif choice == "q":
                    print("動作確認モードを終了します")
                    break
                else:
                    print("⚠️ 1, 2, 3, または q を入力してください")
            except KeyboardInterrupt:
                print("\n終了します")
                break

    async def _position_check(self):
        """座標取得モード"""
        print("\n" + "=" * 50)
        print("座標取得モード")
        print("  toioを動かすと座標がリアルタイム表示されます")
        print("  Enter を押すと終了")
        print("=" * 50)

        # 青LED = 座標取得中
        await self.controller.set_indicator(color=Color(0, 100, 255))

        # 別タスクで座標取得
        stop_event = asyncio.Event()

        async def position_loop():
            last_pos = None
            while not stop_event.is_set():
                pos = await self.controller.sensing.get_position()
                if pos:
                    # 位置が変わった時だけ表示
                    if last_pos is None or pos.x != last_pos.x or pos.y != last_pos.y or pos.angle != last_pos.angle:
                        print(f"  X: {pos.x:4d}  Y: {pos.y:4d}  角度: {pos.angle:3d}°")
                        last_pos = pos
                        # 位置検出OK = 緑点滅
                        await self.controller.set_indicator(color=Color(0, 255, 0))
                else:
                    if last_pos is not None:
                        print("  ⚠️ 位置検出できません（マットから外れている可能性）")
                        last_pos = None
                        # 位置検出NG = 赤
                        await self.controller.set_indicator(color=Color(255, 0, 0))
                await asyncio.sleep(0.1)

        task = asyncio.create_task(position_loop())

        # Enter待ち
        await asyncio.get_event_loop().run_in_executor(None, input, "")
        stop_event.set()
        await task

        await self.controller.set_indicator(color=Color(0, 255, 0))
        print("座標取得モード終了")

    async def _magnet_check(self):
        """磁石検知モード"""
        print("\n" + "=" * 50)
        print("磁石検知モード")
        print("  toioの下に磁石を近づけると検知します")
        print("  Enter を押すと終了")
        print("=" * 50)

        # シアンLED = 磁石検知モード
        await self.controller.set_indicator(color=Color(0, 255, 255))

        stop_event = asyncio.Event()

        async def magnet_loop():
            last_state = None

            while not stop_event.is_set():
                try:
                    # 磁気センサー情報を直接リクエスト
                    await self.controller.cube.api.sensor.request_magnetic_sensor_information()
                    await asyncio.sleep(0.05)  # レスポンス待ち

                    # 磁気センサーの生データを取得
                    sensor = self.controller.sensing.get_magnetic_sensor()
                    magnet_state = sensor.state  # 0: なし, 1-6: 磁石の向き
                    strength = sensor.strength

                    # 磁石検知判定（state が 1以上 または strength が閾値以上）
                    magnet_detected = magnet_state > 0 or strength > 0

                    # 状態変化時のみ表示
                    if magnet_detected != last_state:
                        if magnet_detected:
                            print(f"  🧲 磁石検知！ (state={magnet_state}, strength={strength})")
                            await self.controller.set_indicator(color=Color(255, 0, 255))  # マゼンタ
                        else:
                            print("  ○ 磁石なし")
                            await self.controller.set_indicator(color=Color(0, 255, 255))  # シアン
                        last_state = magnet_detected
                except Exception as e:
                    print(f"  エラー: {e}")
                await asyncio.sleep(0.1)

        task = asyncio.create_task(magnet_loop())

        await asyncio.get_event_loop().run_in_executor(None, input, "")
        stop_event.set()
        await task

        await self.controller.set_indicator(color=Color(0, 255, 0))
        print("磁石検知モード終了")

    async def _move_to_position(self):
        """座標移動モード"""
        print("\n" + "=" * 50)
        print("座標移動モード")
        print("  座標を入力するとtoioがその位置に移動します")
        print("  マット座標範囲: X(45-455), Y(45-455)")
        print("  'q' で終了")
        print("=" * 50)

        # 黄LED = 座標入力待ち
        await self.controller.set_indicator(color=Color(255, 255, 0))

        while True:
            try:
                # 現在位置を表示
                pos = await self.controller.sensing.get_position()
                if pos:
                    print(f"\n現在位置: X={pos.x}, Y={pos.y}, 角度={pos.angle}°")

                # X座標入力
                x_input = input("X座標 (45-455, qで終了): ").strip()
                if x_input.lower() == "q":
                    break
                x = int(x_input)
                if not (45 <= x <= 455):
                    print("⚠️ X座標は45-455の範囲で入力してください")
                    continue

                # Y座標入力
                y_input = input("Y座標 (45-455): ").strip()
                if y_input.lower() == "q":
                    break
                y = int(y_input)
                if not (45 <= y <= 455):
                    print("⚠️ Y座標は45-455の範囲で入力してください")
                    continue

                # 角度入力（オプション）
                angle_input = input("角度 (0-359, Enterでスキップ): ").strip()
                if angle_input.lower() == "q":
                    break
                if angle_input == "":
                    angle = pos.angle if pos else 0
                else:
                    angle = int(angle_input) % 360

                # 移動開始
                print(f"\n移動中... → X={x}, Y={y}, 角度={angle}°")
                await self.controller.set_indicator(color=Color(255, 100, 0))  # オレンジ = 移動中

                await self.controller.action.move_position(x=x, y=y, angle=angle, speed=50)

                # 到着待ち
                for _ in range(50):  # 最大5秒待つ
                    await asyncio.sleep(0.1)
                    pos = await self.controller.sensing.get_position()
                    if pos:
                        dx = abs(pos.x - x)
                        dy = abs(pos.y - y)
                        if dx < 10 and dy < 10:
                            break

                # 到着確認
                pos = await self.controller.sensing.get_position()
                if pos:
                    print(f"✅ 到着: X={pos.x}, Y={pos.y}, 角度={pos.angle}°")
                    await self.controller.set_indicator(color=Color(0, 255, 0))  # 緑 = 完了
                else:
                    print("⚠️ 位置を確認できません")
                    await self.controller.set_indicator(color=Color(255, 0, 0))  # 赤 = エラー

                await asyncio.sleep(0.5)
                await self.controller.set_indicator(color=Color(255, 255, 0))  # 黄に戻す

            except ValueError:
                print("⚠️ 数値を入力してください")
            except KeyboardInterrupt:
                break

        await self.controller.set_indicator(color=Color(0, 255, 0))
        print("座標移動モード終了")

    async def _cleanup(self):
        """クリーンアップ"""
        if self.controller:
            await self.controller.set_indicator(color=Color(100, 100, 100))
            await asyncio.sleep(0.5)
            await self.controller.disconnect()
            print("切断完了")
