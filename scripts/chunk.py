"""Compact timestamped transcript blocks; no summaries, judgments or text loss."""
import argparse
import math
from pathlib import Path
import re
import sys
from common import load_manifest, read_json, run_cli
from transcribe import check_segments, input_identity


def clock(seconds):
    seconds = max(0, math.floor(seconds))
    if seconds >= 3600:
        return f'{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}'
    return f'{seconds // 60:02}:{seconds % 60:02}'


def grouped_lines(segments):
    group = None
    for segment in segments:
        text = segment['text'].replace('\n', ' ')
        if group is None:
            group = {'start': segment['start'], 'end': segment['end'], 'text': text}
        else:
            group['text'] += ' ' + text
            group['end'] = max(group['end'], segment['end'])
        span = group['end'] - group['start']
        # Avoid a timestamp for every short sentence. Aim at 20–30s of speech.
        if span >= 30 or (span >= 20 and re.search(r'[。！？.!?][”"\']?$', text)):
            yield group
            group = None
    if group:
        yield group


def build_chunks(segments, max_chars=6000):
    if max_chars < 128:
        raise ValueError('max_chars 至少 128')
    chunks, current = [], None
    for group in grouped_lines(segments):
        prefix = f'[{clock(group["start"])}] '
        room = max_chars - len(prefix) - 1
        text = group['text']
        while text:
            if len(text) > room:
                matches = list(re.finditer(r'[。！？.!?；;]', text[:room]))
                cut = matches[-1].end() if matches else room
            else:
                cut = len(text)
            line = prefix + text[:cut] + '\n'
            content_size = len(text[:cut])
            text = text[cut:]
            if current and len(current['text']) + len(line) > max_chars:
                chunks.append(current)
                current = None
            if current is None:
                current = {'start': group['start'], 'end': group['end'], 'text': '', 'content_chars': 0}
            current['text'] += line
            current['end'] = max(current['end'], group['end'])
            current['content_chars'] += content_size
    if current:
        chunks.append(current)
    return chunks


def make_chunks(segments, max_chars=6000):
    return [chunk['text'] for chunk in build_chunks(segments, max_chars)]


def main():
    parser = argparse.ArgumentParser(description='单影片紧凑分块，默认最多 6000 字符；约 20～30 秒一行，仅标开始时间。')
    parser.add_argument('folder', type=Path)
    parser.add_argument('--video-id', required=True)
    parser.add_argument('--max-chars', type=int, default=6000)
    parser.add_argument('--chunk', type=int, help='第 N 块，从 1 开始；不填只列块目录及时间范围')
    args = parser.parse_args()
    if args.max_chars < 128:
        parser.error('--max-chars 至少 128')
    root, manifest = load_manifest(args.folder)
    video = next((v for v in manifest['videos'] if v['id'] == args.video_id), None)
    if not video:
        raise ValueError('找不到 video-id，请查看 manifest.json')
    data = read_json(root / '.studylens' / 'transcripts' / (video['id'] + '.json'))
    if data.get('status') != 'complete' or data.get('video_id') != video['id'] or data.get('duration_sec') != video['duration_sec']:
        raise ValueError('逐字稿未完成或与影片不一致，请先转录')
    if data.get('input_identity') != input_identity(video):
        raise ValueError('逐字稿输入已过期，请重新运行 transcribe.py')
    check_segments(data['segments'], video['duration_sec'])
    chunks = build_chunks(data['segments'], args.max_chars)
    print(f'影片: {video["path"]} | {len(chunks)} 块 | 来源: {data["source"]}')
    print(f'时长 {video["duration_sec"]} 秒（最后一段 end 请填此值）')
    if args.chunk is not None:
        if not 1 <= args.chunk <= len(chunks):
            raise ValueError(f'--chunk 超出范围 1..{len(chunks)}')
        print(chunks[args.chunk - 1]['text'], end='')
    else:
        for index, chunk in enumerate(chunks, 1):
            ratio = chunk['content_chars'] / len(chunk['text'])
            print(f'块 {index}: {clock(chunk["start"])}–{clock(chunk["end"])} | {len(chunk["text"])} 字符 | 内容 {ratio:.0%}')
        if not chunks:
            print('逐字稿为空：无音轨或模型未识别到语音；不得凭空补写内容。')
        print('用 --chunk N 逐块读取；合并仅用于阅读，精确起止与静音间隙请查原逐字稿。超长行拆块沿用原组时间范围。')


if __name__ == '__main__':
    sys.exit(run_cli(main))
