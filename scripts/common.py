"""Shared UTF-8, atomic JSON and media helpers (no AI calls)."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.wmv', '.flv', '.mpeg', '.mpg'}
SUBTITLE_EXTENSIONS = ('.srt', '.vtt', '.ass')


def setup_console():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')


def read_json(path):
    with Path(path).open(encoding='utf-8-sig') as handle:
        return json.load(handle)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def fingerprint(path):
    stat = Path(path).stat()
    return {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def compute_library_stats(durations, analyses):
    """Deterministic durations, shared by the CLI and final semantic validation."""
    total = math.fsum(durations.values())
    recommended = math.fsum(
        (segment['end'] - segment['start']) / (segment['speed'] if segment['label'] == 'speed' else 1)
        for video_id in durations for segment in analyses[video_id]['segments']
        if segment['label'] != 'skip'
    )
    saved = total - recommended
    if abs(saved) < 1e-9:
        saved = 0.0
    return {'total_sec': total, 'recommended_sec': recommended, 'saved_sec': saved}


def video_id(relative_path):
    return hashlib.sha256(relative_path.encode('utf-8')).hexdigest()[:16]


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'路径超出影片文件夹: {relative}')
    return path


def probe(path):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                                 '-of', 'json', str(path)], capture_output=True,
                                encoding='utf-8', errors='replace', check=True, timeout=60)
    except FileNotFoundError as exc:
        raise ValueError('找不到 ffprobe，请安装 ffmpeg 并加入 PATH。') from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f'无法读取影片 {path.name}: {exc.stderr.strip()}') from exc
    data = json.loads(result.stdout)
    if not any(s.get('codec_type') == 'video' for s in data.get('streams', [])):
        raise ValueError(f'{path.name} 没有视频流')
    duration = float(data.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f'{path.name} 没有有效时长')
    return duration, any(s.get('codec_type') == 'audio' for s in data['streams'])


def load_manifest(folder):
    root = Path(folder).expanduser().resolve()
    manifest = read_json(root / '.studylens' / 'manifest.json')
    if manifest.get('version') != 1 or not isinstance(manifest.get('videos'), list):
        raise ValueError('不支持的 manifest 格式，请重新运行 scan.py')
    ids = set()
    for video in manifest['videos']:
        if video['id'] != video_id(video['path']) or video['id'] in ids:
            raise ValueError('manifest id 无效或重复，请重新扫描')
        ids.add(video['id'])
        path = inside(root, video['path'])
        if fingerprint(path) != video['fingerprint']:
            raise ValueError(f'影片已变更，请重新扫描: {video["path"]}')
        if video.get('subtitle'):
            subtitle = inside(root, video['subtitle'])
            if fingerprint(subtitle) != video['subtitle_fingerprint']:
                raise ValueError(f'字幕已变更，请重新扫描: {video["subtitle"]}')
    return root, manifest


def run_cli(main):
    setup_console()
    try:
        return main() or 0
    except KeyboardInterrupt:
        print('已中断；已完成文件保留，可重新执行续跑。', file=sys.stderr)
        return 130
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f'错误: {exc}', file=sys.stderr)
        return 1
