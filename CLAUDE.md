# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

toioロボットキューブを使った音楽プログラム。複数のtoio（最大3台）をBluetooth接続し、位置に応じたリアルタイム音声合成と動きの記録・再生を行う。

## Development Commands

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Run the application
python src/main.py

# Run tests
pytest .
```

## Modes

### Mode 1: ループシーケンサモード（DTM風）
- 各toioのボタンを押して記録開始（赤LED）
- toioを手で動かして音を作成
- もう一度ボタンを押すと記録終了、2秒後にループ再生開始（緑LED）
- 再生中にボタンを押すと一時停止（黄LED）
- 一時停止中にボタンを押すと再記録
- 複数toioが独立してループ再生
- 'q' + Enter で終了

### Mode 2: 重奏モード
- serve_toioを手で動かすと、recive_toioが指定秒数（デフォルト2秒）遅れで追従
- 両方のtoioで位置に応じた音が鳴る
- ボタンを押すと終了

## Architecture

Clean Architecture に基づく構造:

```
src/
├── main.py                           # エントリーポイント（モード選択のみ）
├── infrastructure/                   # 外部サービス層
│   ├── toio/                         # toio BLE通信
│   │   ├── cube_controller.py        # 接続管理、LED制御
│   │   ├── cube_action.py            # モーター制御、移動コマンド
│   │   └── cube_sensing.py           # 位置・磁気センサー読み取り
│   └── audio/                        # 音声合成
│       ├── synthesizer.py            # SynthesizerSound（位置→周波数/音量）
│       └── countdown.py              # CountdownSound（カウントダウン音）
├── domain/                           # ビジネスロジック層
│   ├── recording/                    # 動き記録
│   │   ├── frame.py                  # RecordedFrame（1フレームのデータ）
│   │   └── recorder.py               # MotionRecorder（記録管理）
│   └── looper/                       # ループ制御
│       ├── state.py                  # ToioLoopState（状態Enum）
│       └── toio_looper.py            # ToioLooper（各toioのループ管理）
└── usecase/                          # ユースケース層
    ├── loop_sequencer.py             # LoopSequencerMode（DTM風モード）
    ├── duet_mode.py                  # DuetMode（重奏モード）
    └── ui.py                         # UI関数、toioアドレス設定
```

## Key Technical Details

- **Async-first**: asyncioでBLE通信を非同期処理
- **Threading**: 音声合成は専用スレッドで実行（SynthesizerSound）
- **Recording rate**: 50Hz（0.02秒間隔）で位置記録、閾値ベースのフィルタリング
- **Audio mapping**: Y座標→周波数(261Hz〜1975Hz)、X座標→音量
- **Position detection**: 位置検出できない間は音をミュート、記録時間を補正

## Dependencies

- toio (robotics library)
- numpy
- pyaudio (audio synthesis)

## Hardware Requirements

最大3台のtoioキューブ。MACアドレスは `src/usecase/ui.py` の `TOIO_ADDRESSES` で設定:
```python
TOIO_ADDRESSES = [
    "e0:20:07:f8:6a:82",  # toio 1
    "e2:b2:40:be:b2:73",  # toio 2
    "ff:7e:ed:ba:75:86",  # toio 3
]
```
