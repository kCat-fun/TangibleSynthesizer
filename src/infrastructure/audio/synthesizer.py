"""シンセサイザー音生成モジュール"""
import threading
from typing import Optional
import numpy as np
import pyaudio


class SynthesizerSound:
    """
    pyaudioを使用したシンセサイザー音生成クラス
    Y座標: 周波数 (261.626Hz ~ 1975.533Hz)
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
