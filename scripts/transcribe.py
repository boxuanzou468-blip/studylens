"""Convert sidecar subtitles or transcribe locally with resumable per-video output."""
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys
from common import fingerprint, inside, load_manifest, read_json, run_cli, write_json

ENGINE_VERSION = 1
DOWNLOAD_HELP = ('模型下载失败时可手动设置 HF_ENDPOINT=https://hf-mirror.com 后重试，'
                 '或使用 --model <本地文件夹> --local-files-only；镜像为第三方，不会自动启用。')


def timestamp(value):
    parts = value.strip().replace(',', '.').split(':')
    if len(parts) not in (2, 3):
        raise ValueError(f'无效时间戳: {value}')
    nums = [float(part) for part in parts]
    if any(not math.isfinite(n) or n < 0 for n in nums) or nums[-1] >= 60 or nums[-2] >= 60:
        raise ValueError(f'无效时间戳: {value}')
    return nums[-1] + nums[-2] * 60 + (nums[0] * 3600 if len(nums) == 3 else 0)


def clean_text(text, ass=False):
    if ass:
        text = re.sub(r'\{[^}]*\}', '', text)
        return text.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ').strip()
    text = re.sub(r'<[^>]*>', '', text)
    return html.unescape(text).strip()


def read_subtitle(path, encoding):
    raw = path.read_bytes()
    encodings = [encoding] if encoding else ['utf-8-sig'] + (['utf-16'] if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else []) + ['gb18030']
    for candidate in encodings:
        try:
            return raw.decode(candidate).lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
        except (UnicodeError, LookupError):
            continue
    raise ValueError(f'字幕无法按 {", ".join(encodings)} 解码: {path.name}；可用 --subtitle-encoding 强制指定')


def parse_subtitle(path, encoding=None):
    content = read_subtitle(path, encoding)
    segments = []
    if path.suffix.lower() == '.ass':
        in_events, fields = False, None
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('['):
                in_events = line.casefold() == '[events]'
            elif in_events and line.casefold().startswith('format:'):
                fields = [field.strip().lower() for field in line.split(':', 1)[1].split(',')]
                if not {'start', 'end', 'text'}.issubset(fields) or fields[-1] != 'text':
                    raise ValueError('ASS Events Format 需要 Start、End，并以 Text 结尾')
            elif in_events and line.casefold().startswith('dialogue:'):
                if not fields:
                    raise ValueError('ASS Dialogue 之前缺少 Format')
                values = line.split(':', 1)[1].lstrip().split(',', len(fields) - 1)
                if len(values) != len(fields):
                    raise ValueError(f'ASS Dialogue 字段数错误: {line}')
                item = dict(zip(fields, values))
                text = clean_text(item['text'], ass=True)
                if text:
                    segments.append({'start': timestamp(item['start']), 'end': timestamp(item['end']), 'text': text})
    else:
        if path.suffix.lower() == '.vtt' and not content.startswith('WEBVTT'):
            raise ValueError('VTT 缺少 WEBVTT 文件头')
        for block in re.split(r'\n[ \t]*\n', content.strip()):
            lines = block.splitlines()
            if lines and (lines[0].startswith(('WEBVTT', 'NOTE', 'STYLE', 'REGION'))):
                continue
            timing = next((i for i, line in enumerate(lines) if '-->' in line), None)
            if timing is None:
                if block.strip():
                    raise ValueError(f'字幕块缺少时间戳: {block[:100]}')
                continue
            match = re.fullmatch(r'\s*(\S+)\s+-->\s+(\S+)(?:\s+.*)?', lines[timing])
            if not match:
                raise ValueError(f'字幕时间行格式错误: {lines[timing]}')
            text = clean_text('\n'.join(lines[timing + 1:]))
            if text:
                segments.append({'start': timestamp(match[1]), 'end': timestamp(match[2]), 'text': text})
    if not segments:
        raise ValueError(f'字幕没有可读文本: {path.name}；请修复字幕，或移走字幕以使用 Whisper')
    return segments


def check_segments(segments, duration):
    if not isinstance(segments, list):
        raise ValueError('segments 必须为数组')
    previous = -1
    for segment in segments:
        start, end, text = segment['start'], segment['end'], segment['text']
        if (isinstance(start, bool) or isinstance(end, bool) or
                not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or
                not math.isfinite(start) or not math.isfinite(end) or
                start < previous or start < 0 or end <= start or end > duration or
                not isinstance(text, str) or not text.strip()):
            raise ValueError(f'无效转录段落: {segment}')
        previous = start


def normalize_segments(segments, duration):
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('影片时长必须是有限正数')
    result, fixed = [], 0
    for original in segments:
        segment = dict(original)
        start, end = segment['start'], segment['end']
        if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in (start, end)):
            raise ValueError(f'非有限或非数字时间: {segment}')
        # Container/audio durations can differ by a few frames; larger mismatch is an error.
        if max(start, end) > duration + 0.25:
            raise ValueError(f'字幕/转录超出影片时长 {duration:.3f}s: start={start}, end={end}')
        start = min(duration, max(0, start, result[-1]['start'] if result else 0))
        end = min(duration, max(0, end))
        if end <= start:
            if start < duration:
                end = min(duration, start + 0.1)
            elif result:
                result[-1]['text'] += ' ' + segment['text']
                result[-1]['end'] = duration
                fixed += 1
                continue
            else:
                start, end = max(0, duration - 0.1), duration
        segment.update(start=start, end=end)
        if start != original['start'] or end != original['end']:
            fixed += 1
        result.append(segment)
    check_segments(result, duration)
    if fixed:
        print(f'警告：修正 {fixed} 段异常时间，文字已保留。', file=sys.stderr, flush=True)
    return result


def input_identity(video):
    return {'version': ENGINE_VERSION, 'video': video['fingerprint'],
             'duration_sec': video['duration_sec'], 'has_audio': video['has_audio'],
             'subtitle': video['subtitle'], 'subtitle_fingerprint': video['subtitle_fingerprint']}


def cache_key(video, args):
    value = input_identity(video)
    if video['subtitle']:
        value['encoding'] = args.subtitle_encoding
    elif video['has_audio']:
        value.update(model=args.model, language=args.language, beam_size=args.beam_size,
                     vad=not getattr(args, 'no_vad', False), initial_prompt=getattr(args, 'initial_prompt', None))
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def cached(path, key, video):
    try:
        data = read_json(path)
        if (data['version'] != ENGINE_VERSION or
                data['video_id'] != video['id'] or data['duration_sec'] != video['duration_sec'] or
                data['status'] != 'complete' or data.get('input_identity') != input_identity(video)):
            return False
        expected_source = 'subtitle' if video['subtitle'] else ('whisper' if video['has_audio'] else 'no_audio')
        if data.get('source') != expected_source or (expected_source == 'subtitle' and not data['segments']):
            return False
        check_segments(data['segments'], video['duration_sec'])
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


class LocalWhisper:
    def __init__(self, args):
        self.args, self.model, self.device = args, None, None

    def load(self, device):
        from faster_whisper import WhisperModel
        compute = self.args.compute_type or ('float16' if device == 'cuda' else 'int8')
        print(f'加载本地模型: {self.args.model}, device={device}, compute_type={compute}', flush=True)
        self.model = WhisperModel(self.args.model, device=device, compute_type=compute,
                                 download_root=str(self.args.model_dir) if self.args.model_dir else None,
                                 local_files_only=self.args.local_files_only)
        self.device = device

    def transcribe(self, path, duration):
        try:
            import ctranslate2
            if self.model is None:
                device = self.args.device
                if device == 'auto':
                    try:
                        device = 'cuda' if ctranslate2.get_cuda_device_count() else 'cpu'
                    except Exception:
                        device = 'cpu'
                self.device = device
                self.load(device)
            return self.consume(path, duration)
        except Exception as exc:
            gpu_error = any(word in str(exc).lower() for word in
                            ('cuda', 'cudnn', 'cublas', 'out of memory', 'gpu', 'driver'))
            if self.args.device == 'auto' and self.device == 'cuda' and gpu_error:
                print(f'GPU 无法运行，重试 CPU: {exc}', file=sys.stderr, flush=True)
                try:
                    self.model = None
                    self.load('cpu')
                    return self.consume(path, duration)
                except Exception as fallback:
                    raise ValueError(f'CPU 转录失败: {fallback}；{DOWNLOAD_HELP}') from fallback
            raise ValueError(f'本地 Whisper 转录失败: {exc}；检查依赖或用 --device cpu。{DOWNLOAD_HELP}') from exc

    def consume(self, path, duration):
        print(f'  转录开始：{duration:.1f}s，VAD={not self.args.no_vad}', flush=True)
        iterator, info = self.model.transcribe(str(path), language=self.args.language,
                                               beam_size=self.args.beam_size, vad_filter=not self.args.no_vad,
                                               initial_prompt=self.args.initial_prompt)
        segments, last_report = [], 0.0
        interval = max(duration * 0.05, 30.0)
        for segment in iterator:
            if segment.text.strip():
                segments.append({'start': segment.start, 'end': segment.end, 'text': segment.text.strip()})
            position = min(duration, max(0, segment.end))
            if position - last_report >= interval and position < duration:
                print(f'  转录进度 {position / duration:.0%} ({position:.1f}/{duration:.1f}s)', flush=True)
                last_report = position
        print(f'  转录完成：{len(segments)} 段，影片 {duration:.1f}s', flush=True)
        return normalize_segments(segments, duration), info.language, self.device


def main():
    parser = argparse.ArgumentParser(description='字幕优先；无字幕用本地 Whisper；逐影片原子写入，支持续跑。')
    parser.add_argument('folder', type=Path)
    parser.add_argument('--model', default='small', help='Whisper 模型名或本地模型目录；默认 small')
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    parser.add_argument('--compute-type', help='默认 CUDA float16 / CPU int8')
    parser.add_argument('--language', help='如 zh；不填则自动识别')
    parser.add_argument('--beam-size', type=int, default=5)
    parser.add_argument('--model-dir', type=Path, help='模型缓存位置；默认使用库的缓存目录')
    parser.add_argument('--local-files-only', action='store_true', help='仅使用已有模型，不联网下载')
    parser.add_argument('--subtitle-encoding', help='强制字幕编码；默认自动尝试 UTF-8、带 BOM 的 UTF-16、GB18030')
    parser.add_argument('--no-vad', action='store_true', help='关闭默认启用的静音过滤')
    parser.add_argument('--initial-prompt', help='可选的 Whisper 语言/标点提示；默认不带')
    parser.add_argument('--force', action='store_true', help='强制重做已完成的影片')
    parser.add_argument('--video-id', help='只处理指定影片')
    args = parser.parse_args()
    if args.beam_size < 1:
        parser.error('--beam-size 必须大于 0')
    root, manifest = load_manifest(args.folder)
    videos = [v for v in manifest['videos'] if not args.video_id or v['id'] == args.video_id]
    if args.video_id and not videos:
        raise ValueError(f'找不到 video-id: {args.video_id}')
    engine, failures, completed, skipped = LocalWhisper(args), 0, 0, 0
    for index, video in enumerate(videos, 1):
        print(f'[{index}/{len(videos)}] {video["path"]}', flush=True)
        output = root / '.studylens' / 'transcripts' / (video['id'] + '.json')
        key = cache_key(video, args)
        if not args.force and cached(output, key, video):
            previous = read_json(output)
            message = '参数与上次不同，若要重做请加 --force' if previous.get('cache_key') != key else '输入未变化'
            print(f'  SKIP 已完成；{message}', flush=True)
            skipped += 1
            continue
        try:
            language, device = None, None
            if video['subtitle']:
                source = 'subtitle'
                segments = normalize_segments(parse_subtitle(inside(root, video['subtitle']), args.subtitle_encoding), video['duration_sec'])
            elif not video['has_audio']:
                source, segments = 'no_audio', []
                print('  无字幕且无音轨，保存空逐字稿；AI 不能据此判断画面内容。', flush=True)
            else:
                source = 'whisper'
                segments, language, device = engine.transcribe(inside(root, video['path']), video['duration_sec'])
            # Refuse to publish if inputs changed while a long transcription was running.
            if fingerprint(inside(root, video['path'])) != video['fingerprint']:
                raise ValueError('转录期间影片发生变化，请重新扫描')
            if video['subtitle'] and fingerprint(inside(root, video['subtitle'])) != video['subtitle_fingerprint']:
                raise ValueError('转换期间字幕发生变化，请重新扫描')
            write_json(output, {'version': ENGINE_VERSION, 'status': 'complete', 'video_id': video['id'],
                                'duration_sec': video['duration_sec'], 'source': source,
                                'subtitle_path': video['subtitle'], 'language': language, 'device': device,
                                'model': args.model if source == 'whisper' else None,
                                'cache_key': key, 'input_identity': input_identity(video), 'segments': segments})
            print(f'  DONE {source}: {len(segments)} 段 → {output}', flush=True)
            completed += 1
        except Exception as exc:
            failures += 1
            print(f'  FAIL {video["path"]}: {exc}', file=sys.stderr, flush=True)
    print(f'完成 {completed}，跳过 {skipped}，失败 {failures}', flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(run_cli(main))
