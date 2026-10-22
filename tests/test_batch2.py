"""Regressions for Claude review fixes, compact context and semantic validation."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from common import read_json, write_json
from chunk import build_chunks, clock
from transcribe import LocalWhisper, cache_key, normalize_segments, parse_subtitle
from validate import analysis_errors, library_errors, schema_errors, validate_file


class ReviewFixTests(unittest.TestCase):
    def test_zero_and_backward_times_keep_all_text(self):
        items = [{'start': 1, 'end': 1, 'text': '嗯'}, {'start': 1, 'end': 3, 'text': '好'},
                 {'start': 0.5, 'end': 0.3, 'text': '时间倒退'}, {'start': 10, 'end': 10, 'text': '片尾'}]
        output = io.StringIO()
        with redirect_stderr(output):
            result = normalize_segments(items, 10)
        self.assertEqual(''.join(x['text'] for x in result).replace(' ', ''), '嗯好时间倒退片尾')
        self.assertIn('修正 3 段', output.getvalue())
        self.assertEqual(items[0]['end'], 1)  # does not mutate caller data
        self.assertEqual(result[0]['end'], 1.1)
        self.assertEqual(result[2]['start'], 1)

    def test_single_zero_at_end_and_zero_near_end(self):
        for start in [9.95, 10, 10.1]:
            with self.subTest(start=start), redirect_stderr(io.StringIO()):
                result = normalize_segments([{'start': start, 'end': start, 'text': '保留'}], 10)
                self.assertEqual(result[0]['text'], '保留')
                self.assertGreater(result[0]['end'], result[0]['start'])
                self.assertLessEqual(result[0]['end'], 10)

    def test_large_duration_overrun_still_rejected(self):
        with self.assertRaises(ValueError):
            normalize_segments([{'start': 9, 'end': 10.26, 'text': '越界'}], 10)

    def test_auto_encoding_and_explicit_override(self):
        text = '1\n00:00:00,000 --> 00:00:02,000\n中文自动解码\n'
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / '字幕.srt'
            for encoding in ['utf-8', 'utf-8-sig', 'utf-16', 'utf-16-be', 'gb18030']:
                with self.subTest(encoding=encoding):
                    raw = text.encode(encoding)
                    if encoding == 'utf-16-be':
                        raw = b'\xfe\xff' + raw
                    path.write_bytes(raw)
                    self.assertEqual(parse_subtitle(path)[0]['text'], '中文自动解码')
            with self.assertRaises(ValueError):
                parse_subtitle(path, 'utf-8')
            path.write_bytes(b'\x81')
            with self.assertRaises(ValueError):
                parse_subtitle(path)

    def test_compact_chunks_over_80_percent_and_no_text_loss(self):
        text = '这是典型中文字幕内容。'
        segments = [{'start': i * 3, 'end': (i+1) * 3, 'text': text} for i in range(200)]
        chunks = build_chunks(segments)
        ratio = sum(c['content_chars'] for c in chunks) / sum(len(c['text']) for c in chunks)
        # Exclude inserted spaces when measuring substantive content as well.
        substantive = len(text) * 200 / sum(len(c['text']) for c in chunks)
        self.assertGreaterEqual(substantive, 0.8)
        self.assertGreaterEqual(ratio, 0.8)
        actual = ''.join(re.sub(r'^\[[^\]]+\] ', '', line) for c in chunks for line in c['text'].splitlines()).replace(' ', '')
        self.assertEqual(actual, text * 200)
        self.assertTrue(all(len(c['text']) <= 6000 for c in chunks))
        self.assertEqual((chunks[0]['start'], chunks[-1]['end']), (0, 600))
        self.assertEqual(clock(3750.9), '1:02:30')
        self.assertEqual(clock(9.9), '00:09')

    def test_progress_throttling_and_vad_prompt_forwarding(self):
        args = argparse.Namespace(language='zh', beam_size=5, no_vad=False,
                                  initial_prompt='使用简体中文和标点。')
        engine = LocalWhisper(args)
        # 1500 segments over two hours must not produce 1500 progress lines.
        iterator = (SimpleNamespace(start=i*4.8, end=(i+1)*4.8, text='内容') for i in range(1500))
        engine.model = Mock()
        engine.model.transcribe.return_value = (iterator, SimpleNamespace(language='zh'))
        output = io.StringIO()
        with redirect_stdout(output):
            result, _, _ = engine.consume(Path('fake.mp4'), 7200)
        self.assertEqual(len(result), 1500)
        self.assertLessEqual(output.getvalue().count('转录进度'), 20)
        self.assertIn('转录开始', output.getvalue())
        self.assertIn('转录完成', output.getvalue())
        self.assertTrue(engine.model.transcribe.call_args.kwargs['vad_filter'])
        self.assertEqual(engine.model.transcribe.call_args.kwargs['initial_prompt'], args.initial_prompt)
        args.no_vad = True
        engine.model.transcribe.return_value = (iter([]), SimpleNamespace(language='zh'))
        with redirect_stdout(io.StringIO()):
            engine.consume(Path('fake.mp4'), 85)
        self.assertFalse(engine.model.transcribe.call_args.kwargs['vad_filter'])

    def test_device_and_compute_not_in_parameter_key(self):
        video = {'fingerprint': {'size': 10, 'mtime_ns': 1}, 'duration_sec': 10,
                 'has_audio': True, 'subtitle': None, 'subtitle_fingerprint': None}
        args = argparse.Namespace(model='small', language='zh', beam_size=5, device='cpu', compute_type='int8')
        first = cache_key(video, args)
        args.device, args.compute_type = 'cuda', 'float16'
        self.assertEqual(first, cache_key(video, args))

    def test_download_and_gpu_hints_are_present(self):
        result = subprocess.run([sys.executable, str(REPO / 'scripts' / 'check_env.py')], capture_output=True, encoding='utf-8')
        self.assertIn('HF_ENDPOINT=https://hf-mirror.com', result.stdout)
        self.assertIn('https://github.com/SYSTRAN/faster-whisper#gpu', result.stdout)


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = REPO / 'examples'
        cls.manifest = read_json(cls.example / 'manifest.json')
        cls.durations = {v['id']: v['duration_sec'] for v in cls.manifest['videos']}
        cls.analyses = {read_json(p)['video_id']: read_json(p) for p in (cls.example / 'analysis').glob('*.json')}
        cls.analysis = next(iter(cls.analyses.values()))

    def test_all_positive_examples(self):
        paths = [self.example / 'profile.json', self.example / 'library.json', *(self.example / 'analysis').glob('*.json')]
        for path in paths:
            with self.subTest(path=path.name):
                self.assertEqual(validate_file(path), [])

    def test_examples_cover_all_labels(self):
        self.assertEqual({s['label'] for a in self.analyses.values() for s in a['segments']}, {'must', 'normal', 'speed', 'skip'})

    def test_all_negative_examples_report_multiple_errors(self):
        for path in (self.example / 'invalid').glob('*.json'):
            with self.subTest(path=path.name):
                self.assertGreaterEqual(len(validate_file(path)), 2)

    def test_exact_start_and_tolerance_edges(self):
        item = deepcopy(self.analysis)
        item['segments'][0]['start'] = 0.01
        self.assertTrue(any('必须是 0' in e for e in analysis_errors(item, self.durations)))
        item = deepcopy(self.analysis)
        item['segments'][1]['start'] += 0.5
        item['segments'][-1]['end'] -= 1
        self.assertEqual(analysis_errors(item, self.durations), [])
        item['segments'][1]['start'] += 0.001
        item['segments'][-1]['end'] -= 0.001
        errors = analysis_errors(item, self.durations)
        self.assertTrue(any('空隙' in e for e in errors))
        self.assertTrue(any('片尾' in e for e in errors))

    def test_overlap_overrun_and_reverse_all_reported(self):
        item = deepcopy(self.analysis)
        item['segments'][1]['start'] -= 3
        item['segments'][2]['end'] = item['segments'][2]['start']
        item['segments'][-1]['end'] += 0.1
        errors = analysis_errors(item, self.durations)
        self.assertTrue(any('重叠 3 秒' in e for e in errors))
        self.assertTrue(any('零长' in e for e in errors))
        self.assertTrue(any('超出' in e for e in errors))

    def test_schema_relevance_labels_speed_and_numeric_types(self):
        item = deepcopy(self.analysis)
        item['relevance'] = 90.5
        item['segments'][0]['speed'] = 2
        item['segments'][1]['label'] = 'invalid'
        item['segments'][2]['speed'] = 3
        item['segments'][3]['start'] = True
        errors = schema_errors(item, 'video_analysis')
        self.assertGreaterEqual(len(errors), 5)
        for value in ['0', float('nan'), float('inf')]:
            item['segments'][0]['start'] = value
            self.assertTrue(schema_errors(item, 'video_analysis'))

    def test_speed_required(self):
        item = deepcopy(self.analysis)
        speed = next(s for s in item['segments'] if s['label'] == 'speed')
        speed.pop('speed')
        self.assertTrue(any('speed' in e for e in schema_errors(item, 'video_analysis')))

    def test_library_references_and_stats_recomputed(self):
        item = read_json(self.example / 'library.json')
        item['learning_path'][0]['video_id'] = 'missing'
        item['learning_path'][1]['segment_index'] = 99
        item['stats'] = {'total_sec': 600, 'recommended_sec': 400, 'saved_sec': 200}
        errors = library_errors(item, self.durations, self.analyses)
        self.assertTrue(any('不在 manifest' in e for e in errors))
        self.assertTrue(any('索引从 0' in e for e in errors))
        self.assertTrue(any('recommended_sec' in e and '重算' in e for e in errors))

    def test_missing_and_duplicate_analysis_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_json(root / 'manifest.json', self.manifest)
            write_json(root / 'library.json', read_json(self.example / 'library.json'))
            (root / 'analysis').mkdir()
            write_json(root / 'analysis' / 'a.json', self.analysis)
            write_json(root / 'analysis' / 'b.json', self.analysis)
            errors = validate_file(root / 'library.json')
            self.assertTrue(any('重复分析' in e for e in errors))
            self.assertTrue(any('缺少分析' in e for e in errors))

    def test_cli_processes_all_files_after_bad_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'profile.json'
            path.write_text('{broken', encoding='utf-8')
            result = subprocess.run([sys.executable, str(REPO / 'scripts' / 'validate.py'), str(path),
                                     str(self.example / 'invalid' / 'profile-invalid.json')], capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout.count('FAIL '), 2)
            self.assertIn('goals', result.stdout)

    def test_null_scalar_and_malformed_segment_roots_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'profile.json'
            for value in [None, [], 10, True, 'not an object']:
                with self.subTest(value=value):
                    write_json(path, value)
                    self.assertTrue(validate_file(path))
            path = Path(temp) / 'analysis.json'
            write_json(path, {'video_id': [], 'segments': [None, 'bad', {'start': True, 'end': []}]})
            self.assertGreater(len(validate_file(path, manifest=self.example / 'manifest.json')), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
