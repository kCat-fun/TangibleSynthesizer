# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

toioロボットキューブを使った音楽プログラム。複数のtoio（最大3台）をBluetooth接続し、位置に応じたリアルタイム音声合成と動きの記録・再生を行う。

## Development Commands

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Run the application (CUI)
python src/main.py

# Run the application (GUI)
python src/main_gui.py

# Run tests
pytest .
```

## Modes

### Mode 1: ループシーケンサモード（DTM風）
- 各toioのボタンを押すと0.5秒後に記録開始（赤LED）
- toioを手で動かして音を作成
- もう一度ボタンを押すと記録終了、待機（黄LED）
- 待機中にボタンを押すとループ再生開始（緑LED）
- 再生中にボタンを押すと一時停止（黄LED）
- 一時停止中にボタンを押すと再記録
- 複数toioが独立してループ再生（タイミング同期なし）
- 各toioに異なる波形が割り当てられる:
  - toio1: サイン波（位置に応じて常時発音）
  - toio2: のこぎり波（位置に応じて常時発音）
  - toio3: 矩形波（磁石検知時のみ0.1秒間発音）
- 終了時に記録データをJSONファイルに自動保存
- 'q' + Enter で終了

### Mode 2: 重奏モード
- serve_toioを手で動かすと、recive_toioが指定秒数（デフォルト2秒）遅れで追従
- 両方のtoioで位置に応じた音が鳴る
- ボタンを押すと終了

### Mode 3: 動作確認モード
- 1台のtoioを使用して各機能をテスト
- 座標取得（リアルタイム表示）
- 磁石検知（リアルタイム表示）
- 座標移動（入力した座標へ移動）

### Mode 4: 保存データ再生モード
- 過去に保存した記録データを選択して再生
- 各toioが記録通りに動き、音を再生
- 'q' + Enter で終了

## State Transitions (Mode 1)

```
IDLE → (ボタン) → RECORDING → (ボタン) → WAITING → (ボタン) → PLAYING
                                                              ↓
                                              (ボタン) ← PAUSED ← (ボタン)
                                                   ↓
                                              RECORDING
```

## Architecture

Clean Architecture に基づく構造:

```
src/
├── main.py                           # CUIエントリーポイント（モード選択のみ）
├── main_gui.py                       # GUIエントリーポイント（tkinter）
├── gui/                              # GUI層（tkinter）
│   ├── app.py                        # ToioMusicApp（メインウィンドウ、フレーム管理）
│   ├── async_bridge.py               # AsyncBridge（asyncio-tkinter統合）
│   ├── widgets/                      # 再利用可能なウィジェット
│   │   ├── log_panel.py              # LogPanel（ログ表示）
│   │   └── status_bar.py             # StatusBar（ステータスバー）
│   └── frames/                       # モード別GUI画面
│       ├── mode_select_frame.py      # モード選択画面
│       ├── loop_sequencer_frame.py   # ループシーケンサ画面
│       ├── duet_frame.py             # 重奏モード画面
│       ├── debug_frame.py            # 動作確認画面
│       └── playback_frame.py         # 保存データ再生画面
├── infrastructure/                   # 外部サービス層
│   ├── toio/                         # toio BLE通信
│   │   ├── cube_controller.py        # 接続管理、LED制御
│   │   ├── cube_action.py            # モーター制御、移動コマンド
│   │   └── cube_sensing.py           # 位置・磁気センサー読み取り
│   └── audio/                        # 音声合成
│       ├── synthesizer.py            # SynthesizerSound（位置→周波数/音量、波形タイプ対応）
│       └── countdown.py              # CountdownSound（カウントダウン音）
├── domain/                           # ビジネスロジック層
│   ├── recording/                    # 動き記録
│   │   ├── frame.py                  # RecordedFrame（1フレームのデータ）
│   │   └── recorder.py               # MotionRecorder（記録管理）
│   └── looper/                       # ループ制御
│       ├── state.py                  # ToioLoopState（IDLE/RECORDING/WAITING/PLAYING/PAUSED）
│       └── toio_looper.py            # ToioLooper（各toioのループ管理）
└── usecase/                          # ユースケース層（CUI/GUI両対応）
    ├── loop_sequencer.py             # LoopSequencerMode（DTM風モード）
    ├── duet_mode.py                  # DuetMode（重奏モード）
    ├── debug_mode.py                 # DebugMode（動作確認モード）
    ├── playback_mode.py              # PlaybackMode（保存データ再生モード）
    └── ui.py                         # CUI用UI関数、toioアドレス設定

data/
└── recordings/                       # 記録データ保存先（JSON形式）
```

## Key Technical Details

- **Async-first**: asyncioでBLE通信を非同期処理
- **Threading**: 音声合成は専用スレッドで実行（SynthesizerSound）
- **Recording rate**: 50Hz（0.02秒間隔）で位置記録、閾値ベースのフィルタリング
- **Audio mapping**: Y座標→周波数(261Hz〜988Hz、C4〜B5)、X座標→音量
- **Wave types**: サイン波(SINE)、のこぎり波(SAWTOOTH)、矩形波(SQUARE)
- **Magnet trigger**: toio3は磁石検知の立ち上がりエッジで0.1秒間だけ音を発生
- **Position detection**: 位置検出できない間は音をミュート、記録時間を補正
- **Data persistence**: 終了時に記録データをJSON形式で自動保存

## JSON Recording Format

```json
{
  "created_at": "2024-01-01T12:00:00",
  "toio_count": 3,
  "toios": [
    {
      "index": 0,
      "name": "toio_1",
      "wave_type": "sine",
      "frames": [
        {"x": 100, "y": 200, "angle": 0, "timestamp": 0.0, "speed": 100}
      ]
    }
  ]
}
```

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
