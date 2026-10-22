"""First-batch regressions; standard-library unittest, no model downloads."""
import argparse
import math
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import types

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from common import inside, load_manifest, read_json, write_json
from scan import scan
from transcribe import LocalWhisper, cache_key, cached, check_segments, input_identity, normalize_segments, parse_subtitle, timestamp
from chunk import make_chunks


class SubtitleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='StudyLens-中文-')
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def parse(self, suffix, text, encoding='utf-8-sig'):
        path = self.root / ('中文字幕' + suffix)
        path.write_text(text, encoding=encoding)
        return parse_subtitle(path, encoding)

    def test_srt_multiline_bom_and_markup(self):
        result = self.parse('.srt', '1\n00:00:01,200 --> 00:00:03,400\n<b>第一行</b>\n第二行 &amp; 示例\n')
        self.assertEqual(result, [{'start': 1.2, 'end': 3.4, 'text': '第一行\n第二行 & 示例'}])

    def test_vtt_notes_settings_and_id(self):
        result = self.parse('.vtt', 'WEBVTT\n\nNOTE 忽略说明\n这不是字幕\n\nid1\n00:01.000 --> 00:03.000 align:start\n<v 讲师>知识点</v>\n')
        self.assertEqual(result[0]['text'], '知识点')
        self.assertEqual(result[0]['end'], 3)

    def test_ass_fields_comma_and_newline(self):
        result = self.parse('.ass', '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.20,0:00:04.50,Default,,0,0,0,,{\\b1}中文,逗号\\N第二行\n')
        self.assertEqual(result[0]['text'], '中文,逗号\n第二行')

    def test_legacy_encoding_explicit(self):
        result = self.parse('.srt', '1\n00:00:00,000 --> 00:00:01,000\n中文\n', 'gb18030')
        self.assertEqual(result[0]['text'], '中文')

    def test_bad_subtitles_rejected(self):
        for suffix, text in [('.srt', 'bad content'), ('.vtt', 'missing header'), ('.ass', '[Events]\nDialogue: bad')]:
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                self.parse(suffix, text)

    def test_bad_times_rejected(self):
        for value in ['NaN:00', '-1:02', '00:61', '0:60:00', 'oops']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                timestamp(value)

    def test_segment_bounds_and_finite(self):
        for start, end in [(2, 1), (-1, 1), (0, 11), (0, math.inf), (math.nan, 1), (True, 1)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                check_segments([{'start': start, 'end': end, 'text': '内容'}], 10)

    def test_duration_rounding_only(self):
        self.assertEqual(normalize_segments([{'start': 0, 'end': 10.1, 'text': '内容'}], 10)[0]['end'], 10)
        with self.assertRaises(ValueError):
            normalize_segments([{'start': 0, 'end': 12, 'text': '内容'}], 10)

    def test_chunks_bound_and_text_preservation(self):
        text = '这是完整句子。' * 3000
        chunks = make_chunks([{'start': 0, 'end': 100, 'text': text}], 6000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 6000 for chunk in chunks))
        restored = ''.join(line.split('] ', 1)[1] for chunk in chunks for line in chunk.splitlines())
        self.assertEqual(restored, text)

    def test_atomic_json_and_traversal(self):
        path = self.root / '工作' / 'data.json'
        write_json(path, {'标题': '中文'})
        self.assertEqual(read_json(path), {'标题': '中文'})
        self.assertFalse(list(path.parent.glob('*.tmp')))
        with self.assertRaises(ValueError):
            inside(self.root, '../outside.mp4')

    def test_cache_corruption_and_parameter_changes(self):
        video = {'id': 'test', 'fingerprint': {'size': 1, 'mtime_ns': 2}, 'duration_sec': 10,
                 'has_audio': True, 'subtitle': None, 'subtitle_fingerprint': None}
        args = argparse.Namespace(model='tiny', language='zh', device='cpu', compute_type=None,
                                  beam_size=5, subtitle_encoding='utf-8-sig')
        key = cache_key(video, args)
        path = self.root / 'cache.json'
        data = {'version': 1, 'cache_key': key, 'video_id': 'test', 'duration_sec': 10,
                'status': 'complete', 'source': 'whisper', 'input_identity': input_identity(video),
                'segments': [{'start': 0, 'end': 5, 'text': '中文'}]}
        write_json(path, data)
        self.assertTrue(cached(path, key, video))
        args.model = 'small'
        self.assertTrue(cached(path, cache_key(video, args), video))
        data['segments'][0]['end'] = 20
        write_json(path, data)
        self.assertFalse(cached(path, key, video))
        path.write_text('{broken', encoding='utf-8')
        self.assertFalse(cached(path, key, video))

    def test_scan_stable_ids_subtitle_precedence_and_changed_input(self):
        for name in ['甲.mp4', '乙.MP4', '.hidden/忽略.mp4']:
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'fake video')
        (self.root / '甲.srt').write_text('字幕', encoding='utf-8')
        (self.root / '甲.vtt').write_text('字幕', encoding='utf-8')
        with patch('scan.probe', return_value=(10, True)):
            data = scan(self.root)
            again = scan(self.root)
        self.assertEqual(len(data['videos']), 2)
        self.assertEqual([v['id'] for v in data['videos']], [v['id'] for v in again['videos']])
        self.assertEqual(next(v for v in data['videos'] if v['filename'] == '甲.mp4')['subtitle'], '甲.srt')
        write_json(self.root / '.studylens' / 'manifest.json', data)
        load_manifest(self.root)
        (self.root / '甲.mp4').write_bytes(b'changed video')
        with self.assertRaises(ValueError):
            load_manifest(self.root)

    def test_scan_resolves_noncanonical_root(self):
        (self.root / '入口').mkdir()
        (self.root / '课程.mp4').write_bytes(b'fake video')
        (self.root / '课程.srt').write_text('字幕', encoding='utf-8')
        alias = self.root / '入口' / '..'
        with patch('scan.probe', return_value=(10, True)):
            result = scan(alias)
            canonical = scan(self.root.resolve())
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['videos']), 1)
        self.assertEqual(result['videos'], canonical['videos'])
        self.assertEqual(result['videos'][0]['subtitle'], '课程.srt')

    def test_cli_help(self):
        for name in ['check_env.py', 'scan.py', 'transcribe.py', 'chunk.py']:
            with self.subTest(script=name):
                result = subprocess.run([sys.executable, str(SCRIPTS / name), '--help'], capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_auto_gpu_failure_falls_back_to_cpu(self):
        engine = LocalWhisper(argparse.Namespace(device='auto'))
        attempts = []
        def load(device):
            attempts.append(device)
            if device == 'cuda':
                raise RuntimeError('cublas64_12.dll CUDA library missing')
            engine.device = device
        with patch.dict(sys.modules, {'ctranslate2': types.SimpleNamespace(get_cuda_device_count=lambda: 1)}), \
                patch.object(engine, 'load', side_effect=load), \
                patch.object(engine, 'consume', return_value=([], 'zh', 'cpu')):
            self.assertEqual(engine.transcribe(Path('fake.mp4'), 10), ([], 'zh', 'cpu'))
        self.assertEqual(attempts, ['cuda', 'cpu'])

    def test_model_download_error_is_not_misreported_as_gpu_error(self):
        engine = LocalWhisper(argparse.Namespace(device='auto'))
        with patch.dict(sys.modules, {'ctranslate2': types.SimpleNamespace(get_cuda_device_count=lambda: 1)}), \
                patch.object(engine, 'load', side_effect=RuntimeError('SSL connection failed')) as load:
            with self.assertRaises(ValueError):
                engine.transcribe(Path('fake.mp4'), 10)
        self.assertEqual(load.call_count, 1)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires ffmpeg and ffprobe')
    def test_real_subtitle_pipeline_resume_and_stale_chunk(self):
        # Uses real ffprobe/ffmpeg and CLI subprocesses; no Whisper download.
        video = self.root / '真实中文字幕.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                        'color=c=black:s=160x120:r=5:d=2', '-c:v', 'libx264', str(video)], check=True)
        subtitle = video.with_suffix('.srt')
        subtitle.write_text('1\n00:00:00,000 --> 00:00:02,000\n真实字幕文本\n', encoding='utf-8')
        def cli(script, *args, expected=0):
            result = subprocess.run([sys.executable, str(SCRIPTS / script), str(self.root), *args],
                                    capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            return result.stdout
        cli('scan.py')
        cli('transcribe.py', '--local-files-only')
        item = read_json(self.root / '.studylens' / 'manifest.json')['videos'][0]
        output = self.root / '.studylens' / 'transcripts' / (item['id'] + '.json')
        before = output.stat().st_mtime_ns
        self.assertIn('SKIP', cli('transcribe.py', '--local-files-only'))
        self.assertEqual(output.stat().st_mtime_ns, before)
        self.assertIn('真实字幕文本', cli('chunk.py', '--video-id', item['id'], '--chunk', '1'))
        output.write_text('{broken', encoding='utf-8')
        self.assertIn('DONE', cli('transcribe.py', '--local-files-only'))
        subtitle.write_text('1\n00:00:00,000 --> 00:00:02,000\n字幕已更新且长度变更\n', encoding='utf-8')
        cli('scan.py')
        cli('chunk.py', '--video-id', item['id'], expected=1)
        self.assertIn('DONE', cli('transcribe.py', '--local-files-only'))
        subtitle.unlink()
        cli('scan.py')
        self.assertIn('no_audio', cli('transcribe.py', '--local-files-only'))
        self.assertEqual(read_json(output)['segments'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
