"""カウントダウン音生成モジュール"""
from typing import Optional
import numpy as np
import pyaudio


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
