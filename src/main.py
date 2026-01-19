"""toio 音楽プログラム - エントリーポイント"""
import asyncio

from usecase import input_toio_count, select_mode
from usecase import LoopSequencerMode, DuetMode, DebugMode


async def main():
    """メインエントリーポイント"""
    print("=" * 50)
    print("toio 音楽プログラム")
    print("=" * 50)

    mode = select_mode()
    if mode == 0:
        return

    if mode == 1:
        # ループシーケンサモード
        toio_count = input_toio_count()
        if toio_count == 0:
            return
        sequencer = LoopSequencerMode(toio_count)
        await sequencer.run()
    elif mode == 2:
        # 重奏モード
        duet = DuetMode()
        await duet.run()
    elif mode == 3:
        # 動作確認モード
        debug = DebugMode()
        await debug.run()


if __name__ == "__main__":
    asyncio.run(main())
