"""Release regressions; no network or model download."""
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import test_batch4 as fixtures
from validate import analysis_warnings, inspect_file
from build_report import create_report

REPO = Path(__file__).resolve().parents[1]

class ReleaseTests(unittest.TestCase):
    setUp = fixtures.Batch4Tests.setUp
    tearDown = fixtures.Batch4Tests.tearDown
    freshness = fixtures.Batch4Tests.freshness

    def test_short_warning_boundary(self):
        data = {'video_id':'v','segments':[
            {'start':0,'end':6,'label':'skip'},
            {'start':6,'end':24,'label':'must'},
            {'start':24,'end':179,'label':'normal'}]}
        for duration in (85.2, 179.999):
            self.assertEqual(analysis_warnings(data, {'v':duration}), [])
        for duration in (180, 600):
            self.assertEqual(len(analysis_warnings(data, {'v':duration})), 1)
        data['segments'][1]['label']='skip'
        self.assertEqual(analysis_warnings(data, {'v':180}), [])

    def test_multi_file_warning_dedup_in_both_orders(self):
        self.freshness(True)
        for files in ([*self.paths, self.data/'library.json'], [self.data/'library.json', *self.paths]):
            result = subprocess.run([sys.executable,str(REPO/'scripts/validate.py'),*map(str,files)],
                                    capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count('WARNING：'), 2, result.stdout)
            self.assertNotIn(str(self.root), result.stdout)
            self.assertIn('0 个错误，2 个警告',result.stdout)

    def test_builder_warning_dedup_relative_paths(self):
        self.freshness(True)
        output = io.StringIO()
        with redirect_stderr(output):
            create_report(self.root)
        self.assertEqual(output.getvalue().count('WARNING '), 2)
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertIn('analysis/',output.getvalue())

    def test_analysis_and_library_warning_identity(self):
        self.freshness(True)
        single = inspect_file(self.paths[0])[1]
        library = inspect_file(self.data/'library.json')[1]
        self.assertEqual(single[0], next(w for w in library if self.paths[0].name in w))

    def test_same_filename_in_different_media_is_not_deduplicated(self):
        self.freshness(True)
        other = self.root/'other'/'.studylens'
        shutil.copytree(self.data,other)
        files = [self.data/'library.json', other/'library.json']
        result = subprocess.run([sys.executable,str(REPO/'scripts/validate.py'),*map(str,files)],
                                capture_output=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.count('WARNING：'),4,result.stdout)

    def test_optional_local_whisper(self):
        model = os.environ.get('STUDYLENS_TEST_MODEL')
        if not model or not Path(model).is_dir() or not shutil.which('ffmpeg'):
            self.skipTest('requires STUDYLENS_TEST_MODEL local directory and ffmpeg; no download')
        media = self.root/'model-check'; media.mkdir()
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=s=160x120:d=1',
                        '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264',
                        '-c:a','aac','-shortest',str(media/'sample.mp4')], check=True)
        for script,args in [('scan.py',[]),('transcribe.py',['--model',model,'--local-files-only','--device','cpu'])]:
            result=subprocess.run([sys.executable,str(REPO/'scripts'/script),str(media),*args],
                                  capture_output=True,encoding='utf-8',env=dict(os.environ,HF_HUB_OFFLINE='1'))
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
