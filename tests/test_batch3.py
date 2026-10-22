"""Review regressions plus report build validation and inert JSON security."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from common import read_json, write_json
from validate import analysis_warnings, inspect_file, library_errors, validate_file
from build_report import create_report, embedded_json
import chunk
from transcribe import input_identity


class Batch3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='StudyLens-第三批-')
        self.root = Path(self.temp.name)
        self.data = self.root / '.studylens'
        self.data.mkdir()
        for name in ('profile.json', 'manifest.json', 'library.json', 'analysis'):
            source = REPO / 'examples' / name
            if source.is_dir():
                shutil.copytree(source, self.data / name)
            else:
                shutil.copy2(source, self.data / name)
        self.library = read_json(self.data / 'library.json')
        self.durations = {v['id']: v['duration_sec'] for v in read_json(self.data / 'manifest.json')['videos']}
        self.analyses = {read_json(p)['video_id']: read_json(p) for p in (self.data/'analysis').glob('*.json')}

    def tearDown(self):
        self.temp.cleanup()

    def test_learning_path_rejects_skip_and_duplicates_topic_index_allows_skip(self):
        v = next(iter(self.analyses))
        self.library['learning_path'] += [{'video_id': v, 'segment_index': 3, 'reason': 'wrong'},
                                          self.library['learning_path'][0].copy()]
        errors = library_errors(self.library, self.durations, self.analyses)
        self.assertTrue(any('skip 段落' in e for e in errors))
        self.assertTrue(any('重复引用' in e for e in errors))
        original = read_json(self.data/'library.json')
        original['topic_index']['片尾'] = [{'video_id': v, 'segment_index': 3}]
        self.assertEqual(library_errors(original, self.durations, self.analyses), [])

    def test_warning_rules_and_exceptions(self):
        self.assertEqual(len(analysis_warnings({'video_id': 'v', 'segments': [{'start':0,'end':700,'label':'normal'}]}, {'v':700})), 2)
        segments = [{'start':0,'end':5,'label':'normal'}, {'start':5,'end':10,'label':'must'},
                    {'start':10,'end':12,'label':'skip'}, {'start':12,'end':15,'label':'normal'}]
        warnings = analysis_warnings({'video_id':'v','segments':segments}, {'v':180})
        self.assertEqual(len(warnings), 1)
        self.assertIn('segments[1]', warnings[0])
        self.assertEqual(analysis_warnings({'video_id':'v','segments':[{'start':0,'end':480,'label':'normal'}]}, {'v':480}), [])

    def test_warning_cli_exits_zero_and_reports_separately(self):
        video_id = next(iter(self.analyses))
        data = deepcopy(self.analyses[video_id])
        data['segments'] = [data['segments'][0]]
        data['segments'][0]['end'] = 700
        manifest = read_json(self.data/'manifest.json')
        next(v for v in manifest['videos'] if v['id']==video_id)['duration_sec'] = 700
        write_json(self.data/'manifest.json', manifest)
        path = self.data/'analysis'/(video_id+'.json')
        write_json(path, data)
        errors, warnings = inspect_file(path)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 2)
        result = subprocess.run([sys.executable,str(REPO/'scripts'/'validate.py'),str(path)], capture_output=True,encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('PASS（2 个警告）', result.stdout)

    def test_no_speech_example_all_skip_empty_path_passes(self):
        example = REPO/'examples'/'no-speech'
        for path in [example/'profile.json', *sorted((example/'analysis').glob('*.json')), example/'library.json']:
            self.assertEqual(validate_file(path), [], str(path))
        self.assertEqual(read_json(example/'library.json')['learning_path'], [])
        self.assertTrue(list((example/'analysis').glob('*.json')))

    def test_nonempty_learning_content_cannot_have_empty_path(self):
        self.library['learning_path'] = []
        self.assertTrue(any('不能为空' in e for e in library_errors(self.library,self.durations,self.analyses)))

    def test_chunk_header_reports_exact_duration(self):
        video = {'id':'v','path':'demo.mp4','duration_sec':1234.567891, 'has_audio':False,
                 'fingerprint':{'size':0,'mtime_ns':0},'subtitle':None,'subtitle_fingerprint':None}
        write_json(self.data/'transcripts'/'v.json', {'status':'complete','video_id':'v','duration_sec':video['duration_sec'],
                   'source':'no_audio','segments':[],'input_identity':input_identity(video)})
        output = io.StringIO()
        with patch.object(chunk,'load_manifest',return_value=(self.root,{'videos':[video]})), \
                patch.object(sys,'argv',['chunk.py',str(self.root),'--video-id','v']),redirect_stdout(output):
            chunk.main()
        self.assertIn('时长 1234.567891 秒（最后一段 end 请填此值）',output.getvalue())

    def test_invalid_input_refuses_write_and_preserves_old_report(self):
        output = self.root/'studylens-report.html'
        output.write_text('previous report',encoding='utf-8')
        write_json(self.data/'profile.json',{'goals':[]})
        self.library['learning_path'][0]['segment_index'] = 99
        write_json(self.data/'library.json',self.library)
        captured = io.StringIO()
        with redirect_stderr(captured),self.assertRaises(ValueError):
            create_report(self.root)
        self.assertIn('goals', captured.getvalue())
        self.assertIn('越界', captured.getvalue())
        self.assertEqual(output.read_text(encoding='utf-8'),'previous report')

    def test_embedded_json_is_inert_and_round_trips(self):
        malicious = '</script><img src=x onerror=alert(1)>'
        value = embedded_json({'title':malicious,'text':'< & > \u2028'})
        self.assertNotIn('<',value)
        self.assertNotIn('</script>',value)
        self.assertEqual(json.loads(value)['title'],malicious)
        video_id = next(iter(self.analyses))
        path = self.data/'analysis'/(video_id+'.json')
        analysis = read_json(path);analysis['title']=malicious;write_json(path,analysis)
        output = create_report(self.root)
        class Inspector(HTMLParser):
            def __init__(self):
                super().__init__();self.scripts=[];self.images=0
            def handle_starttag(self,tag,attrs):
                if tag=='script':self.scripts.append(dict(attrs))
                if tag=='img':self.images+=1
        parsed = Inspector();parsed.feed(output.read_text(encoding='utf-8'))
        self.assertEqual(len(parsed.scripts),2)
        self.assertEqual(parsed.images,0)
        self.assertEqual(parsed.scripts[0]['type'],'application/json')

    def test_manifest_path_escape_refused(self):
        manifest = read_json(self.data/'manifest.json');manifest['videos'][0]['path']='../outside.mp4'
        write_json(self.data/'manifest.json',manifest)
        with self.assertRaisesRegex(ValueError,'相对路径'):
            create_report(self.root)
        self.assertFalse((self.root/'studylens-report.html').exists())

    def test_custom_report_location_recomputes_relative_media_paths(self):
        output = create_report(self.root,output=self.root/'reports'/'view.html')
        text = output.read_text(encoding='utf-8')
        payload = json.loads(text.split('<script id="studylens-data" type="application/json">')[1].split('</script>')[0])
        self.assertTrue(payload['videos'][0]['path'].startswith('../'))

    def test_builder_help(self):
        result = subprocess.run([sys.executable,str(REPO/'scripts'/'build_report.py'),'--help'],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main(verbosity=2)
