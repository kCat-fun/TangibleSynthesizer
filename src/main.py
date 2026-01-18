import asyncio
import threading
import math
import time
import numpy as np
import pyaudio
from dataclasses import dataclass
from typing import List, Optional, Dict
from enum import Enum
from toio import Color

from domain import *
from infrastructure import *

# 利用可能なtoioアドレスのリスト
TOIO_ADDRESSES = [
    "e0:20:07:f8:6a:82",  # serve_toio（青）- 常に最初
    "e2:b2:40:be:b2:73",  # toio 2
    "ff:7e:ed:ba:75:86",  # toio 3
    # 追加のtoioアドレスをここに追加
]

# 各toioの色
TOIO_COLORS = [
    Color(0, 0, 255),    # 青
    Color(255, 0, 0),    # 赤
    Color(0, 255, 0),    # 緑
    Color(255, 255, 0),  # 黄
    Color(255, 0, 255),  # マゼンタ
    Color(0, 255, 255),  # シアン
]


@dataclass
class RecordedFrame:
    """記録された1フレームのデータ"""
    x: int
    y: int
    angle: int
    magnet_detected: bool
    timestamp: float  # 記録時刻（相対時間）
    speed: int = 100  # 移動速度（前フレームからの速度）


class ToioLoopState(Enum):
    """toioのループ状態"""
    IDLE = "idle"           # 待機中（未記録）
    RECORDING = "recording" # 記録中
    PLAYING = "playing"     # ループ再生中
    PAUSED = "paused"       # 一時停止中


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
        self.recorder: Optional['MotionRecorder'] = None
        # 位置検出ロスト追跡用
        self.position_lost_time: Optional[float] = None  # 位置検出できなくなった時刻
        self.is_position_valid: bool = True  # 現在位置検出できているか


class SynthesizerSound:
    """
    pyaudioを使用したシンセサイザー音生成クラス
    Y座標: 周波数 (261.626Hz ~ 493.883Hz)
    X座標: 音量 (0 ~ 最大)
    専用スレッドで連続的な正弦波を生成
    """
    # マットの座標範囲
    X_MIN = 135
    X_MAX = 220
    Y_MIN = 190
    Y_MAX = 315
    
    # 周波数範囲 (Hz)
    FREQ_MIN = 261.626  # C4 (Y_MIN側)
    FREQ_MAX = 1975.533  # B6 (Y_MAX側)
    
    # オーディオ設定
    SAMPLE_RATE = 44100
    CHUNK_SIZE = 1024
    
    def __init__(self):
        # 現在の周波数と音量（スレッド間で共有）
        self._current_frequency: float = (self.FREQ_MIN + self.FREQ_MAX) / 2
        self._current_volume: float = 0.5  # 0.0 ~ 1.0
        self._muted: bool = True  # 初期状態はミュート
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._phase: float = 0.0  # 位相を保持して連続的な波形を生成

        # PyAudio
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None
    
    def start(self):
        """音声スレッドを開始"""
        if self._running:
            return
        
        # PyAudioの初期化
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.SAMPLE_RATE,
            output=True,
            frames_per_buffer=self.CHUNK_SIZE
        )
        
        self._running = True
        self._thread = threading.Thread(target=self._sound_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """音声スレッドを停止"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        
        # PyAudioのクリーンアップ
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa:
            self._pa.terminate()
            self._pa = None
    
    def _generate_samples(self, frequency: float, volume: float) -> np.ndarray:
        """正弦波のサンプルを生成（位相を連続的に保持）"""
        # 1チャンクあたりの時間
        t = np.arange(self.CHUNK_SIZE) / self.SAMPLE_RATE
        
        # 位相を連続的に保持して正弦波を生成
        samples = volume * np.sin(2 * np.pi * frequency * t + self._phase)
        
        # 次のチャンクのための位相を更新
        self._phase += 2 * np.pi * frequency * self.CHUNK_SIZE / self.SAMPLE_RATE
        self._phase %= 2 * np.pi  # 位相を0~2πに保持
        
        return samples.astype(np.float32)
    
    def _sound_loop(self):
        """音声スレッドのメインループ - 連続的に音を生成"""
        while self._running:
            try:
                with self._lock:
                    frequency = self._current_frequency
                    volume = 0.0 if self._muted else self._current_volume

                # 正弦波サンプルを生成
                samples = self._generate_samples(frequency, volume)

                # オーディオストリームに書き込み
                if self._stream:
                    self._stream.write(samples.tobytes())
            except Exception as e:
                print(f"音声エラー: {e}")

    def mute(self):
        """ミュート（無音にする）"""
        with self._lock:
            self._muted = True

    def unmute(self):
        """ミュート解除"""
        with self._lock:
            self._muted = False
    
    def _clamp(self, value: float, min_val: float, max_val: float) -> float:
        """値を範囲内に制限"""
        return max(min_val, min(max_val, value))
    
    def _map_value(self, value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
        """値を入力範囲から出力範囲にマッピング"""
        return (value - in_min) / (in_max - in_min) * (out_max - out_min) + out_min
    
    def update_position(self, x: int, y: int) -> Optional[str]:
        """
        座標に応じて周波数と音量を更新
        Returns: 現在の状態を示す文字列
        """
        # 座標を範囲内に制限
        x = self._clamp(x, self.X_MIN, self.X_MAX)
        y = self._clamp(y, self.Y_MIN, self.Y_MAX)
        
        # Y座標から周波数を計算（Y_MIN: FREQ_MIN, Y_MAX: FREQ_MAX）
        frequency = self._map_value(y, self.Y_MIN, self.Y_MAX, self.FREQ_MIN, self.FREQ_MAX)
        
        # X座標から音量を計算（X_MIN: 0, X_MAX: 1.0）
        volume = self._map_value(x, self.X_MIN, self.X_MAX, 0.0, 1.0)
        
        # 値を更新
        with self._lock:
            self._current_frequency = frequency
            self._current_volume = volume
        
        return f"🎵 {frequency:.1f}Hz (vol: {volume:.2f})"
    
    def reset(self):
        """状態をリセット"""
        with self._lock:
            self._current_frequency = (self.FREQ_MIN + self.FREQ_MAX) / 2
            self._current_volume = 0.5
            self._phase = 0.0


class CountdownSound:
    """
    カウントダウン音を再生するクラス
    テッ、テッ、テッ、テー（短い音3回 + 長い音1回）
    """
    SAMPLE_RATE = 44100
    FREQUENCY = 880.0  # A5

    def __init__(self):
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None

    def _generate_beep(self, duration: float, volume: float = 0.5) -> np.ndarray:
        """ビープ音を生成"""
        num_samples = int(self.SAMPLE_RATE * duration)
        t = np.arange(num_samples) / self.SAMPLE_RATE
        samples = volume * np.sin(2 * np.pi * self.FREQUENCY * t)

        # フェードイン・フェードアウト（クリック音防止）
        fade_samples = int(self.SAMPLE_RATE * 0.01)  # 10ms
        if fade_samples > 0 and num_samples > fade_samples * 2:
            fade_in = np.linspace(0, 1, fade_samples)
            fade_out = np.linspace(1, 0, fade_samples)
            samples[:fade_samples] *= fade_in
            samples[-fade_samples:] *= fade_out

        return samples.astype(np.float32)

    def _generate_silence(self, duration: float) -> np.ndarray:
        """無音を生成"""
        num_samples = int(self.SAMPLE_RATE * duration)
        return np.zeros(num_samples, dtype=np.float32)

    def play_countdown(self):
        """テッ、テッ、テッ、テー のカウントダウンを再生"""
        # PyAudioの初期化
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.SAMPLE_RATE,
            output=True
        )

        try:
            # テッ（短い音）× 3
            short_beep = self._generate_beep(0.1)
            silence = self._generate_silence(0.9)  # 1秒間隔になるように

            for i in range(3):
                print(f"テッ ({i+1}/3)")
                self._stream.write(short_beep.tobytes())
                self._stream.write(silence.tobytes())

            # テー（長い音）
            long_beep = self._generate_beep(0.5)
            print("テー！ 記録開始！")
            self._stream.write(long_beep.tobytes())

        finally:
            # クリーンアップ
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
            if self._pa:
                self._pa.terminate()


class MotionRecorder:
    """動きを記録するクラス"""
    # toioの速度範囲（APIの仕様: 10-2560、実用範囲は10-100程度）
    # 最小速度を高めに設定して、フレーム間で確実に目標位置に到達できるようにする
    MIN_SPEED = 50
    MAX_SPEED = 100
    
    def __init__(self, position_threshold: int = 5, angle_threshold: int = 10):
        self.frames: List[RecordedFrame] = []
        self.start_time: float = 0
        self.is_recording: bool = False
        self.last_position: Optional[tuple] = None  # (x, y, timestamp)
        # 停止判定の閾値（この値以下の変化は無視）
        self.position_threshold = position_threshold  # 位置の許容誤差（ピクセル）
        self.angle_threshold = angle_threshold        # 角度の許容誤差（度）
    
    def _normalize_angle_diff(self, angle1: int, angle2: int) -> int:
        """角度の差を0-180の範囲に正規化"""
        diff = abs(angle1 - angle2)
        if diff > 180:
            diff = 360 - diff
        return diff
    
    def _is_significant_change(self, x: int, y: int, angle: int) -> bool:
        """前フレームから有意な変化があるかを判定"""
        if not self.frames:
            return True  # 最初のフレームは常に記録
        
        last = self.frames[-1]
        dx = abs(x - last.x)
        dy = abs(y - last.y)
        dangle = self._normalize_angle_diff(angle, last.angle)
        
        return dx > self.position_threshold or dy > self.position_threshold or dangle > self.angle_threshold
    
    def start_recording(self):
        """記録を開始"""
        self.frames.clear()
        self.start_time = asyncio.get_event_loop().time()
        self.is_recording = True
        self.last_position = None
        print("📹 記録開始")
    
    def _calculate_speed(self, x: int, y: int, timestamp: float) -> int:
        """
        前フレームからの距離と時間から速度を計算
        Returns: toio API用の速度値（10-100）
        """
        import math
        
        if self.last_position is None:
            return self.MAX_SPEED  # 最初のフレームはデフォルト速度
        
        last_x, last_y, last_time = self.last_position
        
        # 距離を計算（ピクセル）
        distance = math.sqrt((x - last_x) ** 2 + (y - last_y) ** 2)
        
        # 時間差を計算（秒）
        dt = timestamp - last_time
        if dt <= 0:
            return self.MAX_SPEED
        
        # 速度を計算（ピクセル/秒）
        velocity = distance / dt
        
        # toioの速度にマッピング
        # 実測値に基づく換算: velocity ≈ speed * 2.5 (調整済み)
        # 速度100で約250ピクセル/秒程度
        speed = int(velocity / 2.5)
        
        # 範囲内に制限
        speed = max(self.MIN_SPEED, min(self.MAX_SPEED, speed))
        
        return speed
    
    def record_frame(self, x: int, y: int, angle: int, magnet_detected: bool):
        """1フレーム記録（有意な変化がある場合のみ）"""
        if not self.is_recording:
            return
        
        # 有意な変化がない場合はスキップ（ただし磁石状態の変化は常に記録）
        last_magnet = self.frames[-1].magnet_detected if self.frames else False
        if not self._is_significant_change(x, y, angle) and magnet_detected == last_magnet:
            return
        
        timestamp = asyncio.get_event_loop().time() - self.start_time
        
        # 速度を計算
        speed = self._calculate_speed(x, y, timestamp)
        
        frame = RecordedFrame(x=x, y=y, angle=angle, magnet_detected=magnet_detected, timestamp=timestamp, speed=speed)
        self.frames.append(frame)
        
        # 現在位置を保存（次フレームの速度計算用）
        self.last_position = (x, y, timestamp)
    
    def stop_recording(self):
        """記録を停止"""
        self.is_recording = False
        print(f"⏹ 記録停止 | {len(self.frames)}フレーム記録")
    
    def get_frames(self) -> List[RecordedFrame]:
        """記録されたフレームを取得"""
        return self.frames


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


async def main():
    print("=" * 50)
    print("toio 動き記録・再生プログラム")
    print("=" * 50)

    # モード選択
    mode = select_mode()
    if mode == 0:
        print("プログラム終了")
        return

    if mode == 1:
        # ループシーケンサモード
        toio_count = input_toio_count()
        if toio_count == 0:
            print("プログラム終了")
            return
        await run_loop_sequencer_mode(toio_count)
    else:
        # 重奏モード（従来通り2台）
        serve_controller = CubeController(
            address=TOIO_ADDRESSES[0], name="serve_toio",
            color=TOIO_COLORS[0], logging=True
        )
        receive_controller = CubeController(
            address=TOIO_ADDRESSES[1], name="recive_toio",
            color=TOIO_COLORS[1], logging=False
        )
        await run_duet_mode(serve_controller, receive_controller)

    print("プログラム終了")


async def play_single_bar(
    controller: CubeController,
    frames: List[RecordedFrame],
    sound: SynthesizerSound,
    stop_event: asyncio.Event
) -> bool:
    """
    1小節分を再生する
    Returns: True=正常終了, False=中断された
    """
    if len(frames) < 2:
        return True

    BAR_DURATION = 4.0
    PLAYBACK_POSITION_THRESHOLD = 8
    PLAYBACK_ANGLE_THRESHOLD = 15
    last_sent_x, last_sent_y, last_sent_angle = None, None, None

    def should_move(target_x: int, target_y: int, target_angle: int) -> bool:
        nonlocal last_sent_x, last_sent_y, last_sent_angle
        if last_sent_x is None:
            return True
        dx = abs(target_x - last_sent_x)
        dy = abs(target_y - last_sent_y)
        dangle = abs(target_angle - last_sent_angle)
        if dangle > 180:
            dangle = 360 - dangle
        return dx > PLAYBACK_POSITION_THRESHOLD or dy > PLAYBACK_POSITION_THRESHOLD or dangle > PLAYBACK_ANGLE_THRESHOLD

    # LED: 移動中（オレンジ）
    await controller.set_indicator(color=Color(255, 100, 0))

    # 最初に開始位置に移動
    first_frame = frames[0]
    await controller.action.move_position(
        x=first_frame.x, y=first_frame.y, angle=first_frame.angle, speed=50
    )

    # 位置に到達するまで待つ
    POSITION_THRESHOLD = 15
    for _ in range(50):  # 最大5秒待つ
        if stop_event.is_set():
            return False
        pos = await controller.sensing.get_position()
        if pos:
            dx = abs(pos.x - first_frame.x)
            dy = abs(pos.y - first_frame.y)
            if dx < POSITION_THRESHOLD and dy < POSITION_THRESHOLD:
                break
        await asyncio.sleep(0.1)

    # LED: 再生中（黄色）
    await controller.set_indicator(color=Color(255, 255, 0))

    if stop_event.is_set():
        return False

    loop = asyncio.get_event_loop()
    start_time = loop.time()
    frame_index = 0

    sound.unmute()

    while frame_index < len(frames):
        if stop_event.is_set():
            sound.mute()
            return False

        current_time = loop.time() - start_time
        frame = frames[frame_index]

        if current_time >= frame.timestamp:
            if should_move(frame.x, frame.y, frame.angle):
                await controller.action.move_position(
                    x=frame.x, y=frame.y, angle=frame.angle, speed=frame.speed
                )
                last_sent_x, last_sent_y, last_sent_angle = frame.x, frame.y, frame.angle
                sound.update_position(frame.x, frame.y)
            frame_index += 1

        await asyncio.sleep(0.005)

    # 1小節の残り時間を待つ
    elapsed = loop.time() - start_time
    if elapsed < BAR_DURATION and not stop_event.is_set():
        await asyncio.sleep(BAR_DURATION - elapsed)

    sound.mute()
    # LED: 待機中（緑）
    await controller.set_indicator(color=Color(0, 255, 0))
    return True


async def move_to_start_position(
    controller: CubeController,
    frames: List[RecordedFrame]
):
    """
    toioを小節の開始位置に移動させる（再生はしない）
    """
    if len(frames) < 2:
        return

    first_frame = frames[0]

    # LED: 移動中（オレンジ）
    await controller.set_indicator(color=Color(255, 100, 0))

    await controller.action.move_position(
        x=first_frame.x, y=first_frame.y, angle=first_frame.angle, speed=50
    )

    # 位置に到達するまで待つ
    POSITION_THRESHOLD = 15
    for _ in range(50):  # 最大5秒待つ
        pos = await controller.sensing.get_position()
        if pos:
            dx = abs(pos.x - first_frame.x)
            dy = abs(pos.y - first_frame.y)
            if dx < POSITION_THRESHOLD and dy < POSITION_THRESHOLD:
                break
        await asyncio.sleep(0.1)

    # LED: 待機中（緑）
    await controller.set_indicator(color=Color(0, 255, 0))


async def play_bar_without_move(
    controller: CubeController,
    frames: List[RecordedFrame],
    sound: SynthesizerSound,
    stop_event: asyncio.Event
) -> bool:
    """
    1小節分を再生する（開始位置への移動なし - 既に移動済みの前提）
    """
    if len(frames) < 2:
        return True

    BAR_DURATION = 4.0
    PLAYBACK_POSITION_THRESHOLD = 8
    PLAYBACK_ANGLE_THRESHOLD = 15
    last_sent_x, last_sent_y, last_sent_angle = None, None, None

    def should_move(target_x: int, target_y: int, target_angle: int) -> bool:
        nonlocal last_sent_x, last_sent_y, last_sent_angle
        if last_sent_x is None:
            return True
        dx = abs(target_x - last_sent_x)
        dy = abs(target_y - last_sent_y)
        dangle = abs(target_angle - last_sent_angle)
        if dangle > 180:
            dangle = 360 - dangle
        return dx > PLAYBACK_POSITION_THRESHOLD or dy > PLAYBACK_POSITION_THRESHOLD or dangle > PLAYBACK_ANGLE_THRESHOLD

    # LED: 再生中（黄色）
    await controller.set_indicator(color=Color(255, 255, 0))

    if stop_event.is_set():
        return False

    loop = asyncio.get_event_loop()
    start_time = loop.time()
    frame_index = 0

    sound.unmute()

    while frame_index < len(frames):
        if stop_event.is_set():
            sound.mute()
            return False

        current_time = loop.time() - start_time
        frame = frames[frame_index]

        if current_time >= frame.timestamp:
            if should_move(frame.x, frame.y, frame.angle):
                await controller.action.move_position(
                    x=frame.x, y=frame.y, angle=frame.angle, speed=frame.speed
                )
                last_sent_x, last_sent_y, last_sent_angle = frame.x, frame.y, frame.angle
                sound.update_position(frame.x, frame.y)
            frame_index += 1

        await asyncio.sleep(0.005)

    # 1小節の残り時間を待つ
    elapsed = loop.time() - start_time
    if elapsed < BAR_DURATION and not stop_event.is_set():
        await asyncio.sleep(BAR_DURATION - elapsed)

    sound.mute()
    # LED: 待機中（緑）
    await controller.set_indicator(color=Color(0, 255, 0))
    return True


async def sequential_loop_playback(
    bars: List[tuple],  # [(controller, frames), ...]
    stop_event: asyncio.Event,
    sound: SynthesizerSound,
    loop_pause: float = 0.5
):
    """
    複数の小節を順番にループ再生する（stop_eventがセットされるまで）
    bars: [(controller, frames), ...] のリスト
    loop_pause: ループ間の休止時間（秒）
    """
    if not bars:
        return

    while not stop_event.is_set():
        # 各小節を順番に再生
        for controller, frames in bars:
            if stop_event.is_set():
                break
            success = await play_single_bar(controller, frames, sound, stop_event)
            if not success:
                break

        # ループ間に少し間を置く
        if not stop_event.is_set():
            await asyncio.sleep(loop_pause)


# ===============================================
# 新ループシーケンサ用ヘルパー関数
# ===============================================

async def loop_playback_task(looper: ToioLooper):
    """各toioの独立したループ再生タスク"""
    PLAYBACK_POSITION_THRESHOLD = 8
    PLAYBACK_ANGLE_THRESHOLD = 15

    while not looper.stop_event.is_set():
        if looper.state != ToioLoopState.PLAYING:
            await asyncio.sleep(0.1)
            continue

        if len(looper.frames) < 2:
            await asyncio.sleep(0.1)
            continue

        # 開始位置に移動
        first = looper.frames[0]
        await looper.controller.set_indicator(color=Color(255, 100, 0))  # オレンジ=移動中
        await looper.controller.action.move_position(
            x=first.x, y=first.y, angle=first.angle, speed=50
        )

        # 位置に到達するまで待つ
        for _ in range(30):  # 最大3秒待つ
            if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
                break
            pos = await looper.controller.sensing.get_position()
            if pos:
                dx = abs(pos.x - first.x)
                dy = abs(pos.y - first.y)
                if dx < 15 and dy < 15:
                    break
            await asyncio.sleep(0.1)

        if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
            continue

        await looper.controller.set_indicator(color=Color(0, 255, 0))  # 緑=再生中

        # フレーム再生
        if looper.synth:
            looper.synth.unmute()

        loop = asyncio.get_event_loop()
        start_time = loop.time()
        last_sent_x, last_sent_y, last_sent_angle = None, None, None

        for frame in looper.frames:
            if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
                break

            # タイミングを待つ
            while loop.time() - start_time < frame.timestamp:
                if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
                    break
                await asyncio.sleep(0.005)

            if looper.stop_event.is_set() or looper.state != ToioLoopState.PLAYING:
                break

            # 有意な移動がある場合のみ移動指示
            should_move = True
            if last_sent_x is not None:
                dx = abs(frame.x - last_sent_x)
                dy = abs(frame.y - last_sent_y)
                dangle = abs(frame.angle - last_sent_angle)
                if dangle > 180:
                    dangle = 360 - dangle
                should_move = dx > PLAYBACK_POSITION_THRESHOLD or dy > PLAYBACK_POSITION_THRESHOLD or dangle > PLAYBACK_ANGLE_THRESHOLD

            if should_move:
                await looper.controller.action.move_position(
                    x=frame.x, y=frame.y, angle=frame.angle, speed=frame.speed
                )
                last_sent_x, last_sent_y, last_sent_angle = frame.x, frame.y, frame.angle

            if looper.synth:
                looper.synth.update_position(frame.x, frame.y)

        if looper.synth:
            looper.synth.mute()

        # ループ間の短い休止
        await asyncio.sleep(0.3)


async def start_looper_recording(looper: ToioLooper):
    """録音開始"""
    looper.state = ToioLoopState.RECORDING
    await looper.controller.set_indicator(color=Color(255, 0, 0))  # 赤=記録中

    looper.recorder = MotionRecorder()
    looper.recorder.start_recording()

    # 位置検出状態をリセット
    looper.is_position_valid = True
    looper.position_lost_time = None

    # シンセサイザーを開始
    if looper.synth is None:
        looper.synth = SynthesizerSound()
        looper.synth.start()
    looper.synth.unmute()

    print(f"🔴 {looper.controller.name} 記録開始 - toioを手で動かしてください")


async def stop_looper_recording_and_start_loop(looper: ToioLooper):
    """録音終了してループ再生開始"""
    if looper.recorder:
        looper.recorder.stop_recording()
        looper.frames = looper.recorder.get_frames()

    if looper.synth:
        looper.synth.mute()

    if len(looper.frames) < 2:
        print(f"⚠️ {looper.controller.name} 記録が短すぎます。やり直してください。")
        looper.state = ToioLoopState.IDLE
        await looper.controller.set_indicator(color=Color(100, 100, 100))  # グレー
        return

    print(f"⏸️ {looper.controller.name} 2秒後にループ再生開始...")
    await looper.controller.set_indicator(color=Color(255, 255, 0))  # 黄色=待機中
    await asyncio.sleep(2)

    looper.state = ToioLoopState.PLAYING
    looper.stop_event.clear()
    looper.play_task = asyncio.create_task(loop_playback_task(looper))
    print(f"🟢 {looper.controller.name} ループ再生開始 ({len(looper.frames)}フレーム)")


async def pause_looper(looper: ToioLooper):
    """ループ再生を一時停止"""
    looper.state = ToioLoopState.PAUSED
    looper.stop_event.set()

    if looper.play_task:
        try:
            await asyncio.wait_for(looper.play_task, timeout=2.0)
        except asyncio.TimeoutError:
            looper.play_task.cancel()
        looper.play_task = None

    if looper.synth:
        looper.synth.mute()

    await looper.controller.set_indicator(color=Color(255, 255, 0))  # 黄色=一時停止
    print(f"⏸️ {looper.controller.name} 一時停止 - もう一度押すと再記録")


async def handle_looper_button_press(looper: ToioLooper, all_loopers: List[ToioLooper]):
    """ボタン押下時の状態遷移処理"""
    if looper.state == ToioLoopState.IDLE:
        # 他のtoioがRECORDING中なら拒否
        if any(l.state == ToioLoopState.RECORDING for l in all_loopers if l != looper):
            print(f"⚠️ 他のtoioが記録中です")
            return
        await start_looper_recording(looper)

    elif looper.state == ToioLoopState.RECORDING:
        await stop_looper_recording_and_start_loop(looper)

    elif looper.state == ToioLoopState.PLAYING:
        await pause_looper(looper)

    elif looper.state == ToioLoopState.PAUSED:
        # 他のtoioがRECORDING中なら拒否
        if any(l.state == ToioLoopState.RECORDING for l in all_loopers if l != looper):
            print(f"⚠️ 他のtoioが記録中です")
            return
        await start_looper_recording(looper)


def start_input_thread(quit_event: asyncio.Event, loop: asyncio.AbstractEventLoop):
    """別スレッドでq入力を監視"""
    import sys
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


async def run_loop_sequencer_mode(toio_count: int):
    """新ループシーケンサモード: DTMのように各toioが独立してループ再生"""
    print("\n" + "=" * 50)
    print("新ループシーケンサモードを開始します")
    print("=" * 50)

    RECORD_INTERVAL = 0.02  # 記録間隔 (50Hz)

    # toioコントローラーを作成
    controllers: List[CubeController] = []
    for i in range(toio_count):
        name = f"toio_{i+1}"
        controller = CubeController(
            address=TOIO_ADDRESSES[i],
            name=name,
            color=TOIO_COLORS[i % len(TOIO_COLORS)],
        )
        controllers.append(controller)

    # 全toioに接続
    print("\n全toioに接続中...")
    for controller in controllers:
        await controller.connect()
        await controller.set_indicator(color=Color(100, 100, 100))  # グレー=待機中
    print(f"✅ {toio_count}台のtoioに接続しました")

    # ToioLooperを作成
    loopers: List[ToioLooper] = []
    for i, ctrl in enumerate(controllers):
        loopers.append(ToioLooper(ctrl, i))

    # ボタンイベント辞書
    button_events: Dict[int, asyncio.Event] = {}

    # 各toioにボタンハンドラを登録
    for i, looper in enumerate(loopers):
        button_events[i] = asyncio.Event()

        def make_handler(idx: int):
            def handler(payload: bytearray):
                if len(payload) >= 2 and payload[0] == 0x01 and payload[1] == 0x80:
                    button_events[idx].set()
            return handler

        await looper.controller.cube.api.button.register_notification_handler(make_handler(i))

    # 終了イベント
    quit_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    input_thread = start_input_thread(quit_event, loop)

    print("\n" + "=" * 50)
    print("準備完了！")
    print("=" * 50)
    print("\n操作方法:")
    print("  - toioのボタンを押す → 記録開始（赤LED）")
    print("  - toioを手で動かして音を作成")
    print("  - もう一度ボタンを押す → 記録終了、2秒後ループ再生開始（緑LED）")
    print("  - 再生中のtoioのボタンを押す → 一時停止（黄LED）")
    print("  - 一時停止中にボタンを押す → 再記録開始")
    print("  - 終了するには 'q' を入力してEnter")
    print("=" * 50)

    try:
        # メインループ
        while not quit_event.is_set():
            # ボタンイベント処理
            for i, event in button_events.items():
                if event.is_set():
                    event.clear()
                    await handle_looper_button_press(loopers[i], loopers)

            # RECORDING中のtoioの位置を記録
            for looper in loopers:
                if looper.state == ToioLoopState.RECORDING and looper.recorder:
                    pos = await looper.controller.sensing.get_position()
                    current_time = asyncio.get_event_loop().time()

                    if pos:
                        # 位置検出できた
                        if not looper.is_position_valid and looper.position_lost_time is not None:
                            # 位置検出が復帰した - ロストしていた時間分だけstart_timeを進める
                            lost_duration = current_time - looper.position_lost_time
                            looper.recorder.start_time += lost_duration
                            looper.position_lost_time = None
                            if looper.synth:
                                looper.synth.unmute()

                        looper.is_position_valid = True
                        looper.recorder.record_frame(
                            x=pos.x, y=pos.y, angle=pos.angle, magnet_detected=False
                        )
                        if looper.synth:
                            looper.synth.update_position(pos.x, pos.y)
                    else:
                        # 位置検出できなかった
                        if looper.is_position_valid:
                            # 位置検出ロスト開始
                            looper.position_lost_time = current_time
                            looper.is_position_valid = False
                            if looper.synth:
                                looper.synth.mute()

            await asyncio.sleep(RECORD_INTERVAL)

    except KeyboardInterrupt:
        print("\n🛑 Ctrl+Cで中断されました")
    finally:
        # クリーンアップ
        print("\nクリーンアップ中...")
        quit_event.set()

        # 入力スレッドの終了を待つ（daemonなので自動終了するが念のため）
        if input_thread.is_alive():
            input_thread.join(timeout=1.0)

        # 全looperを停止
        for looper in loopers:
            looper.stop_event.set()
            if looper.play_task:
                try:
                    await asyncio.wait_for(looper.play_task, timeout=2.0)
                except asyncio.TimeoutError:
                    looper.play_task.cancel()
            if looper.synth:
                looper.synth.stop()

        # 全toioを切断
        for controller in controllers:
            await controller.disconnect()

        print("✅ 終了しました")


async def run_playback_mode(serve_controller: CubeController, receive_controller: CubeController):
    """再生モード: 記録後に再生（旧モード - 参考用）"""
    print("\n🎵 再生モードを開始します")
    # 接続（順番に接続してタイムアウトを回避）
    await serve_controller.connect()
    await receive_controller.connect()

    # ボタン通知ハンドラを登録
    button_pressed = asyncio.Event()
    
    def button_handler(payload: bytearray):
        """ボタン押下を検知するハンドラ"""
        if len(payload) >= 2 and payload[0] == 0x01:
            # ボタン情報の形式: [0x01, button_state]
            # button_state: 0x80 = 押下, 0x00 = 離された
            if payload[1] == 0x80:
                print("🔘 ボタンが押されました！")
                button_pressed.set()
    
    # serve_toioにボタン通知ハンドラを登録
    await serve_controller.cube.api.button.register_notification_handler(button_handler)

    # LED設定（初期状態）
    await asyncio.gather(
        serve_controller.set_indicator(),
        receive_controller.set_indicator()
    )

    # ====================
    # Phase 1: 初期位置合わせ
    # ====================
    print("\n📍 Phase 1: recive_toioをserve_toioの位置に移動")
    pos = await serve_controller.sensing.get_position()
    if pos:
        await receive_controller.action.move_position(x=pos.x, y=pos.y, angle=pos.angle, speed=100)
    await asyncio.sleep(3)  # 動作完了を待つ

    # 緑LED = 準備完了
    await asyncio.gather(
        serve_controller.set_indicator(color=Color(0, 255, 0)),
        receive_controller.set_indicator(color=Color(0, 255, 0))
    )
    print("✅ 初期位置合わせ完了")
    await asyncio.sleep(1)

    # ====================
    # Phase 2: 記録モード
    # ====================
    print("\n📹 Phase 2: 記録モード")
    print("  serve_toioを手で自由に動かしてください")
    print("  LEDボタンを押すと記録終了 → 再生開始")
    
    # LED設定（青 = 記録中）
    await serve_controller.set_indicator(color=Color(0, 100, 255))
    await receive_controller.set_indicator(color=Color(100, 100, 100))  # グレー = 待機中

    recorder = MotionRecorder()
    recorder.start_recording()
    
    # 記録中の音声（serve_toio用）- シンセサイザー
    recording_sound = SynthesizerSound()
    recording_sound.start()

    # 磁石検知状態を追跡
    serve_magnet_was_detected = False
    
    RECORD_INTERVAL = 0.001  # 記録間隔（秒）= 50Hz
    
    # ボタンが押されるまで記録を続ける
    while not button_pressed.is_set():
        # serve_toioの位置を取得・記録
        pos = await serve_controller.sensing.get_position()
        magnet_detected = await serve_controller.sensing.check_magnet_below()
        
        if pos:
            recorder.record_frame(x=pos.x, y=pos.y, angle=pos.angle, magnet_detected=magnet_detected)
            # 座標に応じた音を鳴らす
            recording_sound.update_position(pos.x, pos.y)
        
        # 磁石検知で表示（状態変化時のみ）
        if magnet_detected and not serve_magnet_was_detected:
            print(f"🧲 serve_toio 磁石検出！ (strength={serve_controller.sensing.get_magnetic_strength()})")
            await serve_controller.set_indicator(color=Color(255, 0, 0))
        elif not magnet_detected and serve_magnet_was_detected:
            print(f"⭕ serve_toio 磁石なし")
            await serve_controller.set_indicator(color=Color(0, 100, 255))
        
        serve_magnet_was_detected = magnet_detected
        
        await asyncio.sleep(RECORD_INTERVAL)
    
    # 記録中の音声を停止
    recording_sound.stop()
    
    recorder.stop_recording()
    button_pressed.clear()

    # ====================
    # Phase 3: 再生モード
    # ====================
    print("\n▶️ Phase 3: 再生モード")
    print(f"  {len(recorder.frames)}フレームを再生")
    
    # LED設定（黄色 = 再生中）
    await asyncio.gather(
        serve_controller.set_indicator(color=Color(255, 255, 0)),
        receive_controller.set_indicator(color=Color(255, 255, 0))
    )

    frames = recorder.get_frames()
    if len(frames) < 2:
        print("⚠️ 記録が短すぎます。最低2フレーム必要です。")
        return

    # 再生開始
    start_time = asyncio.get_event_loop().time()
    frame_index = 0
    playback_running = True  # 再生中フラグ
    
    # asyncioイベントループを取得（スレッドから非同期関数を呼ぶため）
    loop = asyncio.get_event_loop()
    
    # 座標に応じた音を鳴らす（recive_toio用）- シンセサイザー
    positional_sound = SynthesizerSound()
    positional_sound.start()  # 音声スレッドを開始
    
    # recive_toioの現在位置（キャッシュ）- スレッドセーフに共有
    cached_x = frames[0].x if frames else 180
    cached_y = frames[0].y if frames else 250
    position_lock = threading.Lock()
    
    # 再生時の閾値（現在位置との差がこれ以下なら移動指示をスキップ）
    PLAYBACK_POSITION_THRESHOLD = 8   # 位置の許容誤差（ピクセル）
    PLAYBACK_ANGLE_THRESHOLD = 15     # 角度の許容誤差（度）
    last_sent_x, last_sent_y, last_sent_angle = None, None, None
    
    def should_move(target_x: int, target_y: int, target_angle: int) -> bool:
        """移動が必要かを判定"""
        nonlocal last_sent_x, last_sent_y, last_sent_angle
        if last_sent_x is None:
            return True
        dx = abs(target_x - last_sent_x)
        dy = abs(target_y - last_sent_y)
        dangle = abs(target_angle - last_sent_angle)
        if dangle > 180:
            dangle = 360 - dangle
        return dx > PLAYBACK_POSITION_THRESHOLD or dy > PLAYBACK_POSITION_THRESHOLD or dangle > PLAYBACK_ANGLE_THRESHOLD
    
    def sound_position_updater():
        """recive_toioの実際の位置に基づいて音を更新するスレッド"""
        nonlocal cached_x, cached_y
        while playback_running:
            try:
                # asyncioイベントループで非同期関数を実行
                future = asyncio.run_coroutine_threadsafe(
                    receive_controller.sensing.get_position(),
                    loop
                )
                pos = future.result(timeout=0.5)  # 最大0.5秒待つ
                if pos:
                    with position_lock:
                        cached_x = pos.x
                        cached_y = pos.y
            except Exception:
                pass  # エラー時はキャッシュを維持
            
            with position_lock:
                x, y = cached_x, cached_y
            positional_sound.update_position(x, y)
            threading.Event().wait(0.05)  # 50msごとに更新
    
    # 音声位置更新スレッドを開始
    sound_update_thread = threading.Thread(target=sound_position_updater, daemon=True)
    sound_update_thread.start()
    
    # フレーム再生ループ（移動指示のみ）
    while frame_index < len(frames):
        current_time = asyncio.get_event_loop().time() - start_time
        frame = frames[frame_index]
        
        # フレームのタイミングに達したか確認
        if current_time >= frame.timestamp:
            # 有意な移動がある場合のみ移動指示を送る
            if should_move(frame.x, frame.y, frame.angle):
                await receive_controller.action.move_position(
                    x=frame.x, y=frame.y, angle=frame.angle, speed=frame.speed
                )
                last_sent_x, last_sent_y, last_sent_angle = frame.x, frame.y, frame.angle
            frame_index += 1
        
        await asyncio.sleep(0.005)  # 5msごとに確認

    # 最後の位置に到達するまで少し待つ
    await asyncio.sleep(1)
    
    # 再生終了
    playback_running = False
    sound_update_thread.join(timeout=1)
    
    # 音声スレッドを停止
    positional_sound.stop()

    # ====================
    # 完了
    # ====================
    print("\n✅ 再生完了！")
    
    # LED設定（緑 = 完了）
    await asyncio.gather(
        serve_controller.set_indicator(color=Color(0, 255, 0)),
        receive_controller.set_indicator(color=Color(0, 255, 0))
    )

    await asyncio.sleep(2)

    # 切断
    await asyncio.gather(
        serve_controller.disconnect(),
        receive_controller.disconnect()
    )


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


async def run_duet_mode(serve_controller: CubeController, receive_controller: CubeController):
    """重奏モード: 指定秒数遅れで追従演奏"""
    print("\n🎶 重奏モードを開始します")
    
    DELAY_SECONDS = input_delay_seconds()
    print(f"✅ 遅延時間: {DELAY_SECONDS}秒")
    
    # 接続
    await serve_controller.connect()
    await receive_controller.connect()

    # ボタン通知ハンドラを登録
    button_pressed = asyncio.Event()
    
    def button_handler(payload: bytearray):
        if len(payload) >= 2 and payload[0] == 0x01:
            if payload[1] == 0x80:
                print("🔘 ボタンが押されました！終了します...")
                button_pressed.set()
    
    await serve_controller.cube.api.button.register_notification_handler(button_handler)

    # LED設定（初期状態）
    await asyncio.gather(
        serve_controller.set_indicator(),
        receive_controller.set_indicator()
    )

    # ====================
    # Phase 1: 初期位置合わせ
    # ====================
    print("\n📍 Phase 1: recive_toioをserve_toioの位置に移動")
    pos = await serve_controller.sensing.get_position()
    if pos:
        await receive_controller.action.move_position(x=pos.x, y=pos.y, angle=pos.angle, speed=100)
    await asyncio.sleep(3)

    # 緑LED = 準備完了
    await asyncio.gather(
        serve_controller.set_indicator(color=Color(0, 255, 0)),
        receive_controller.set_indicator(color=Color(0, 255, 0))
    )
    print("✅ 初期位置合わせ完了")
    await asyncio.sleep(1)

    # ====================
    # Phase 2: 重奏モード開始
    # ====================
    print("\n🎶 Phase 2: 重奏モード")
    print(f"  serve_toioを手で動かしてください")
    print(f"  recive_toioが{DELAY_SECONDS}秒遅れで追従します")
    print("  LEDボタンを押すと終了")
    
    # LED設定
    await serve_controller.set_indicator(color=Color(0, 100, 255))  # 青 = メイン
    await receive_controller.set_indicator(color=Color(255, 100, 0))  # オレンジ = フォロー

    # 両方のtoioで音を鳴らす
    serve_sound = SynthesizerSound()
    receive_sound = SynthesizerSound()
    serve_sound.start()
    receive_sound.start()

    # 記録用のリングバッファ（2秒分のフレームを保持）
    recorder = MotionRecorder()
    recorder.start_recording()
    
    # 磁石検知状態
    serve_magnet_was_detected = False
    
    RECORD_INTERVAL = 0.02  # 記録間隔（秒）= 50Hz
    
    # 再生用の変数
    loop = asyncio.get_event_loop()
    playback_running = True
    
    # 再生閾値
    PLAYBACK_POSITION_THRESHOLD = 8
    PLAYBACK_ANGLE_THRESHOLD = 15
    last_sent_x, last_sent_y, last_sent_angle = None, None, None
    
    def should_move(target_x: int, target_y: int, target_angle: int) -> bool:
        nonlocal last_sent_x, last_sent_y, last_sent_angle
        if last_sent_x is None:
            return True
        dx = abs(target_x - last_sent_x)
        dy = abs(target_y - last_sent_y)
        dangle = abs(target_angle - last_sent_angle)
        if dangle > 180:
            dangle = 360 - dangle
        return dx > PLAYBACK_POSITION_THRESHOLD or dy > PLAYBACK_POSITION_THRESHOLD or dangle > PLAYBACK_ANGLE_THRESHOLD
    
    start_time = loop.time()
    
    while not button_pressed.is_set():
        current_time = loop.time() - start_time
        
        # serve_toioの位置を取得・記録
        pos = await serve_controller.sensing.get_position()
        magnet_detected = await serve_controller.sensing.check_magnet_below()
        
        if pos:
            recorder.record_frame(x=pos.x, y=pos.y, angle=pos.angle, magnet_detected=magnet_detected)
            # serve_toioの音を更新
            serve_sound.update_position(pos.x, pos.y)
        
        # 磁石検知で表示（状態変化時のみ）
        if magnet_detected and not serve_magnet_was_detected:
            print(f"🧲 serve_toio 磁石検出！")
            await serve_controller.set_indicator(color=Color(255, 0, 0))
        elif not magnet_detected and serve_magnet_was_detected:
            await serve_controller.set_indicator(color=Color(0, 100, 255))
        serve_magnet_was_detected = magnet_detected
        
        # 2秒遅れでrecive_toioを動かす
        frames = recorder.get_frames()
        if frames and current_time >= DELAY_SECONDS:
            target_time = current_time - DELAY_SECONDS
            
            # target_timeに最も近いフレームを探す
            target_frame = None
            for frame in frames:
                if frame.timestamp <= target_time:
                    target_frame = frame
                else:
                    break
            
            if target_frame and should_move(target_frame.x, target_frame.y, target_frame.angle):
                await receive_controller.action.move_position(
                    x=target_frame.x, y=target_frame.y, 
                    angle=target_frame.angle, speed=target_frame.speed
                )
                last_sent_x, last_sent_y, last_sent_angle = target_frame.x, target_frame.y, target_frame.angle
                # recive_toioの音を更新（目標位置で）
                receive_sound.update_position(target_frame.x, target_frame.y)
        
        await asyncio.sleep(RECORD_INTERVAL)
    
    # 音声を停止
    serve_sound.stop()
    receive_sound.stop()
    recorder.stop_recording()

    # ====================
    # 完了
    # ====================
    print("\n✅ 重奏モード終了！")
    
    await asyncio.gather(
        serve_controller.set_indicator(color=Color(0, 255, 0)),
        receive_controller.set_indicator(color=Color(0, 255, 0))
    )

    await asyncio.sleep(2)

    await asyncio.gather(
        serve_controller.disconnect(),
        receive_controller.disconnect()
    )


if __name__ == "__main__":
    asyncio.run(main())
