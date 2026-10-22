"""Scan local videos into a portable manifest."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from common import VIDEO_EXTENSIONS, SUBTITLE_EXTENSIONS, fingerprint, probe, run_cli, video_id, write_json


def scan(root, recursive=True):
    videos, errors = [], []
    paths = root.rglob('*') if recursive else root.iterdir()
    for path in sorted(paths, key=lambda p: p.as_posix().casefold()):
        relative = path.relative_to(root)
        if any(part.startswith('.') or part == '__pycache__' for part in relative.parts):
            continue
        if path.suffix.lower() not in VIDEO_EXTENSIONS or not path.is_file():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            errors.append(f'跳过外部链接: {relative}')
            continue
        try:
            duration, audio = probe(path)
            siblings = {p.name.casefold(): p for p in path.parent.iterdir() if p.is_file()}
            subtitle = next((siblings.get((path.stem + ext).casefold())
                             for ext in SUBTITLE_EXTENSIONS
                             if (path.stem + ext).casefold() in siblings), None)
            if subtitle and (subtitle.is_symlink() or not subtitle.resolve().is_relative_to(root)):
                raise ValueError(f'字幕不能是外部链接: {subtitle.name}')
            rel = relative.as_posix()
            videos.append({'id': video_id(rel), 'path': rel, 'filename': path.name,
                           'duration_sec': duration, 'has_audio': audio,
                           'fingerprint': fingerprint(path),
                           'subtitle': subtitle.relative_to(root).as_posix() if subtitle else None,
                           'subtitle_fingerprint': fingerprint(subtitle) if subtitle else None})
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    return {'version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
            'videos': videos, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description='扫描影片，写入影片文件夹下 .studylens/manifest.json；默认递归。')
    parser.add_argument('folder', type=Path)
    parser.add_argument('--no-recursive', action='store_true', help='仅扫描顶层')
    args = parser.parse_args()
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f'文件夹不存在: {root}')
    manifest = scan(root, not args.no_recursive)
    destination = root / '.studylens' / 'manifest.json'
    write_json(destination, manifest)
    for item in manifest['videos']:
        print(f'{item["id"]} | {item["duration_sec"]:.3f}s | {item["path"]} | 字幕: {item["subtitle"] or "无"}', flush=True)
    for error in manifest['errors']:
        print(f'错误: {error}', file=sys.stderr)
    print(f'共 {len(manifest["videos"])} 支影片；manifest: {destination}')
    return 1 if manifest['errors'] else 0


if __name__ == '__main__':
    sys.exit(run_cli(main))
