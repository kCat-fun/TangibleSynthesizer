"""UI・入力関連モジュール"""
import asyncio
import sys
import time
import threading
from typing import List

# toioアドレスの設定
TOIO_ADDRESSES = [
    "e0:20:07:f8:6a:82",  # toio 1
    "e2:b2:40:be:b2:73",  # toio 2
    "ff:7e:ed:ba:75:86",  # toio 3
]


async def async_input(prompt: str) -> str:
    """非同期入力（他のタスクをブロックしない）"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, prompt)


async def async_choice_input(prompt: str, valid_choices: List[str]) -> str:
    """非同期で選択肢入力を受け付ける"""
    while True:
        choice = await async_input(prompt)
        choice = choice.strip()
        if choice in valid_choices:
            return choice
        print(f"⚠️ {' または '.join(valid_choices)} を入力してください")


def input_toio_count() -> int:
    """使用するtoioの台数を入力"""
    max_toios = len(TOIO_ADDRESSES)
    print(f"\n使用可能なtoio: 最大{max_toios}台")

    while True:
        try:
            value = input(f"何台のtoioを使いますか？ (1-{max_toios}): ").strip()
            count = int(value)
            if 1 <= count <= max_toios:
                return count
            print(f"⚠️ 1〜{max_toios}の範囲で入力してください")
        except ValueError:
            print("⚠️ 数値を入力してください")
        except KeyboardInterrupt:
            print("\nキャンセルされました")
            return 0


def select_mode() -> int:
    """モード選択メニューを表示"""
    print("\n" + "=" * 50)
    print("モードを選択してください")
    print("=" * 50)
    print("  1: ループシーケンサモード（DTM風 - ボタンで記録/再生を制御）")
    print("  2: 重奏モード（2秒遅れで追従演奏）")
    print("=" * 50)

    while True:
        try:
            choice = input("モード番号を入力 (1 or 2): ").strip()
            if choice in ["1", "2"]:
                return int(choice)
            print("⚠️ 1 または 2 を入力してください")
        except KeyboardInterrupt:
            print("\nキャンセルされました")
            return 0


def input_delay_seconds() -> float:
    """遅延秒数を入力"""
    print("\n⏱️ 遅延秒数を入力してください")
    while True:
        try:
            value = input("遅延秒数 (0.5〜10.0, デフォルト2.0): ").strip()
            if value == "":
                return 2.0
            delay = float(value)
            if 0.5 <= delay <= 10.0:
                return delay
            print("⚠️ 0.5〜10.0の範囲で入力してください")
        except ValueError:
            print("⚠️ 数値を入力してください")
        except KeyboardInterrupt:
            print("\nデフォルト値(2.0秒)を使用します")
            return 2.0


def start_input_thread(quit_event: asyncio.Event, loop: asyncio.AbstractEventLoop) -> threading.Thread:
    """別スレッドでq入力を監視"""
    import select

    def input_thread():
        while not quit_event.is_set():
            # selectでタイムアウト付きで標準入力を監視（0.5秒）
            if sys.platform == 'win32':
                # Windowsではselectが使えないのでブロッキング
                import msvcrt
                if msvcrt.kbhit():
                    char = msvcrt.getwch()
                    if char.lower() == 'q':
                        loop.call_soon_threadsafe(quit_event.set)
                        print("\n🛑 終了します...")
                        break
                else:
                    time.sleep(0.1)
            else:
                # Linux/Mac
                readable, _, _ = select.select([sys.stdin], [], [], 0.5)
                if readable:
                    line = sys.stdin.readline()
                    if line.strip().lower() == 'q':
                        loop.call_soon_threadsafe(quit_event.set)
                        print("\n🛑 終了します...")
                        break

    thread = threading.Thread(target=input_thread, daemon=True)
    thread.start()
    return thread
