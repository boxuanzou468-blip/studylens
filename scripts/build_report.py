"""Validate all input JSON and build a self-contained offline HTML report."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
from common import inside, read_json, run_cli
from validate import inspect_file

TEMPLATE = Path(__file__).resolve().parents[1] / 'templates' / 'report.html'
DATA_TOKEN = '__STUDYLENS_DATA__'


def embedded_json(data):
    return (json.dumps(data, ensure_ascii=False, allow_nan=False)
            .replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
            .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def create_report(folder, data_dir=None, output=None):
    root = Path(folder).expanduser().resolve()
    data_dir = Path(data_dir).resolve() if data_dir else root / '.studylens'
    output = Path(output).resolve() if output else root / 'studylens-report.html'
    if output.suffix.lower() != '.html':
        raise ValueError('报告输出必须使用 .html 扩展名')
    if not root.is_dir():
        raise ValueError(f'影片文件夹不存在: {root}')
    manifest = data_dir / 'manifest.json'
    analysis_dir = data_dir / 'analysis'
    files = [(data_dir / 'profile.json', 'profile'),
             *((p, 'video_analysis') for p in sorted(analysis_dir.glob('*.json'))),
             (data_dir / 'library.json', 'library')]
    errors, warnings = [], []
    for path, kind in files:
        problems, notes = inspect_file(path, kind, manifest, analysis_dir)
        errors.extend(f'{path}：{problem}' for problem in problems)
        warnings.extend(notes)
    errors = list(dict.fromkeys(errors))
    if errors:
        for error in errors:
            print(f'ERROR {error}', file=sys.stderr)
        raise ValueError(f'校验失败，共 {len(errors)} 个错误；未写入报告')
    for warning in dict.fromkeys(warnings):
        print(f'WARNING {warning}', file=sys.stderr)
    videos = read_json(manifest)['videos']
    analyses = {data['video_id']: data for data in (read_json(p) for p in sorted(analysis_dir.glob('*.json')))}
    rows = []
    for video in videos:
        relative = video.get('path')
        if (not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative or
                PurePosixPath(relative).is_absolute() or any(p in ('..', '.') for p in relative.split('/'))):
            raise ValueError(f'影片路径必须是素材目录内的相对路径: {relative!r}')
        source = inside(root, relative)
        media_relative = Path(os.path.relpath(source, output.parent)).as_posix()
        rows.append({'id': video['id'], 'path': media_relative,
                     'filename': video.get('filename', PurePosixPath(relative).name),
                     'duration_sec': video['duration_sec'], **analyses[video['id']]})
    payload = {'profile': read_json(data_dir / 'profile.json'),
               'library': read_json(data_dir / 'library.json'), 'videos': rows}
    template = TEMPLATE.read_text(encoding='utf-8')
    if template.count(DATA_TOKEN) != 1:
        raise ValueError('报告模板必须包含且仅包含一个数据占位符')
    page = template.replace(DATA_TOKEN, embedded_json(payload))
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=output.name + '.', suffix='.tmp', dir=output.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(page)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f'PASS 已校验 {len(rows)} 份影片分析，报告: {output}')
    return output


def main():
    parser = argparse.ArgumentParser(description='先校验 profile、所有分析、library，再生成单文件离线报告。')
    parser.add_argument('folder', type=Path, help='影片文件夹；报告默认输出在此处')
    parser.add_argument('--data-dir', type=Path, help='默认 <影片文件夹>/.studylens；示例可指定 examples/')
    parser.add_argument('--output', type=Path, help='可选 .html 路径；影片路径会相对报告重新计算')
    args = parser.parse_args()
    create_report(args.folder, args.data_dir, args.output)


if __name__ == '__main__':
    sys.exit(run_cli(main))
