"""Print validated deterministic stats JSON, never ask an agent to do arithmetic."""
import argparse
import json
from pathlib import Path
import sys
from common import compute_library_stats, run_cli
from validate import load_analyses, load_durations


def calculate(folder, data_dir=None):
    data_dir = Path(data_dir).resolve() if data_dir else Path(folder).expanduser().resolve() / '.studylens'
    errors = []
    durations = load_durations(data_dir / 'manifest.json', errors)
    analyses, valid = load_analyses(data_dir / 'analysis', durations, errors)
    if errors or not valid:
        for error in dict.fromkeys(errors):
            print(f'ERROR {error}', file=sys.stderr)
        raise ValueError('分析不完整或不合法，未输出统计；请先修复并验证每支影片')
    stats = compute_library_stats(durations, analyses)
    if stats['saved_sec'] < 0:
        raise ValueError('建议时长超过影片总时长，请检查分析是否存在容差内的重复覆盖')
    return stats


def main():
    parser = argparse.ArgumentParser(description='读取 manifest 与所有 analysis，输出可直接用作 library.stats 的 JSON。')
    parser.add_argument('folder', type=Path, help='影片文件夹')
    parser.add_argument('--data-dir', type=Path, help='默认 <folder>/.studylens；虚构示例可指定 examples/')
    args = parser.parse_args()
    print(json.dumps(calculate(args.folder, args.data_dir), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    sys.exit(run_cli(main))
