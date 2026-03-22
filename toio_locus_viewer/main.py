#!/usr/bin/env python3
"""
toio軌跡視覚化プログラム
3台のtoioの移動軌跡をA4比率の長方形内に描画します。
"""

import json
import sys
import argparse
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

# A4比率 (210mm x 297mm)
A4_RATIO = 297 / 210  # 約1.414

# toioプレイマットの座標範囲
PLAYMAT_X_MIN = 103
PLAYMAT_X_MAX = 241
PLAYMAT_Y_MIN = 149
PLAYMAT_Y_MAX = 351

# 各toioの色
COLORS = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6']


def load_json_file(filepath: str) -> dict:
    """JSONファイルを読み込む"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def select_file_gui() -> str:
    """GUIでファイルを選択"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()  # メインウィンドウを非表示
        
        filepath = filedialog.askopenfilename(
            title="toio軌跡JSONファイルを選択",
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*")
            ]
        )
        root.destroy()
        return filepath
    except ImportError:
        print("警告: tkinterが利用できません。コマンドライン引数でファイルを指定してください。")
        return None


def normalize_coordinates(frames: list, mat_width: float, mat_height: float) -> tuple:
    """座標をA4長方形内に正規化"""
    if not frames:
        return [], []
    
    x_coords = [f['x'] for f in frames]
    y_coords = [f['y'] for f in frames]
    
    # プレイマット座標を正規化（Y軸はマット上で下が正なので反転）
    x_norm = [(x - PLAYMAT_X_MIN) / (PLAYMAT_X_MAX - PLAYMAT_X_MIN) * mat_width for x in x_coords]
    y_norm = [(PLAYMAT_Y_MAX - y) / (PLAYMAT_Y_MAX - PLAYMAT_Y_MIN) * mat_height for y in y_coords]
    
    return x_norm, y_norm


def visualize_trajectories(data: dict, output_path: str = None):
    """軌跡を視覚化"""
    toios = data.get('toios', [])
    toio_count = len(toios)
    
    if toio_count == 0:
        print("エラー: toioデータが見つかりません。")
        return
    
    # A4比率の長方形サイズ
    rect_width = 1.0
    rect_height = A4_RATIO
    
    # 図のサイズ設定（3つ横並び + 余白）
    fig_width = 12
    fig_height = fig_width / 3 * A4_RATIO + 1
    
    fig, axes = plt.subplots(1, 3, figsize=(fig_width, fig_height))
    
    for idx in range(3):
        ax = axes[idx]
        
        # A4比率の長方形を描画
        rect = patches.Rectangle(
            (0, 0), rect_width, rect_height,
            linewidth=2, edgecolor='#333333', facecolor='#F8F9FA'
        )
        ax.add_patch(rect)
        
        if idx < toio_count:
            toio = toios[idx]
            frames = toio.get('frames', [])
            name = toio.get('name', f'toio_{idx+1}')
            wave_type = toio.get('wave_type', 'unknown')
            color = COLORS[idx % len(COLORS)]
            
            # 座標を正規化
            x_coords, y_coords = normalize_coordinates(frames, rect_width, rect_height)
            
            if x_coords and y_coords:
                # 軌跡を描画
                ax.plot(x_coords, y_coords, color=color, linewidth=2, alpha=0.8, label='trajectory')
                
                # 開始点と終了点をマーク
                ax.scatter(x_coords[0], y_coords[0], color=color, s=100, marker='o', 
                          zorder=5, edgecolor='white', linewidth=2, label='start')
                ax.scatter(x_coords[-1], y_coords[-1], color=color, s=100, marker='s', 
                          zorder=5, edgecolor='white', linewidth=2, label='end')
                
                # 進行方向を示す矢印（中間点に配置）
                if len(x_coords) > 2:
                    for i in range(0, len(x_coords)-1, max(1, len(x_coords)//5)):
                        dx = x_coords[min(i+1, len(x_coords)-1)] - x_coords[i]
                        dy = y_coords[min(i+1, len(y_coords)-1)] - y_coords[i]
                        if abs(dx) > 0.001 or abs(dy) > 0.001:
                            ax.annotate('', xy=(x_coords[i]+dx*0.5, y_coords[i]+dy*0.5),
                                       xytext=(x_coords[i], y_coords[i]),
                                       arrowprops=dict(arrowstyle='->', color=color, lw=1.5))
            
            # タイトルと情報
            ax.set_title(f'{name}\n({wave_type})', fontsize=18, fontweight='bold', color=color)
            
            # フレーム数と時間情報
            if frames:
                duration = frames[-1]['timestamp'] - frames[0]['timestamp']
                info_text = f'frames: {len(frames)}\nduration: {duration:.2f}s'
                ax.text(0.02, rect_height - 0.05, info_text, fontsize=8, 
                       verticalalignment='top', fontfamily='monospace',
                       bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        else:
            # データがない場合
            ax.set_title(f'toio_{idx+1}\n(no data)', fontsize=11, color='#999999')
            ax.text(rect_width/2, rect_height/2, 'No Data', fontsize=16, 
                   ha='center', va='center', color='#CCCCCC')
        
        # 軸の設定
        ax.set_xlim(-0.05, rect_width + 0.05)
        ax.set_ylim(-0.05, rect_height + 0.05)
        ax.set_aspect('equal')
        ax.axis('off')
    
    plt.tight_layout()
    
    # 保存または表示
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"Saved: {output_path}")
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description='toio Trajectory Visualizer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python toio_trajectory_visualizer.py                    # GUI file selection
  python toio_trajectory_visualizer.py trajectory.json    # Specify file
  python toio_trajectory_visualizer.py data.json -o out.png  # Save as image
        '''
    )
    parser.add_argument('filepath', nargs='?', help='JSON file path (GUI selection if omitted)')
    parser.add_argument('-o', '--output', help='Output image file path (display on screen if omitted)')
    
    args = parser.parse_args()
    
    # ファイルパスの取得
    filepath = args.filepath
    if not filepath:
        filepath = select_file_gui()
        if not filepath:
            print("No file selected.")
            sys.exit(1)
    
    # JSONファイルの読み込み
    try:
        data = load_json_file(filepath)
        print(f"Loaded: {filepath}")
        print(f"toio count: {data.get('toio_count', 'N/A')}")
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: JSON parse failed: {e}")
        sys.exit(1)
    
    # 視覚化
    visualize_trajectories(data, args.output)


if __name__ == '__main__':
    main()