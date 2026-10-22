"""Profile freshness and deterministic stats regressions."""
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from common import compute_library_stats, read_json, write_json
from validate import inspect_file, validate_file
from library_stats import calculate
from build_report import create_report


class Batch4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='StudyLens-第四批-')
        self.root = Path(self.temp.name)
        self.data = self.root / '.studylens'
        self.data.mkdir()
        for name in ('profile.json','manifest.json','library.json','analysis'):
            source = REPO/'examples'/name
            if source.is_dir():
                shutil.copytree(source,self.data/name)
            else:
                shutil.copy2(source,self.data/name)
        self.paths = sorted((self.data/'analysis').glob('*.json'))

    def tearDown(self):
        self.temp.cleanup()

    def freshness(self,newer):
        for path in self.paths:
            os.utime(path,ns=(2_000_000_000,2_000_000_000))
        value = 3_000_000_000 if newer else 1_000_000_000
        os.utime(self.data/'profile.json',ns=(value,value))

    def test_fresh_profile_warns_for_analysis_and_library_not_error(self):
        self.freshness(True)
        errors, warnings = inspect_file(self.paths[0])
        self.assertEqual(errors,[])
        self.assertTrue(any('学习目标可能已更新' in w and ('analysis/' + self.paths[0].name) in w for w in warnings))
        errors, warnings = inspect_file(self.data/'library.json')
        self.assertEqual(errors,[])
        self.assertEqual(sum('可能过期' in w for w in warnings),2)

    def test_older_profile_does_not_warn(self):
        self.freshness(False)
        self.assertEqual(inspect_file(self.paths[0]),([],[]))

    def test_freshness_warning_is_nonfatal_in_builder_and_cli(self):
        self.freshness(True)
        log = io.StringIO()
        with redirect_stderr(log):
            output = create_report(self.root)
        self.assertTrue(output.is_file())
        self.assertIn('若要依新目标重新标注请重跑分析',log.getvalue())
        result = subprocess.run([sys.executable,str(REPO/'scripts'/'validate.py'),str(self.paths[0])],capture_output=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS（1 个警告）',result.stdout)
        self.assertEqual(validate_file(self.paths[0]),[])

    def test_stats_match_all_four_labels_and_final_validation(self):
        self.assertEqual(calculate(self.root),{'total_sec':600,'recommended_sec':390,'saved_sec':210})
        library = read_json(self.data/'library.json')
        library['stats'] = calculate(self.root)
        write_json(self.data/'library.json',library)
        self.assertEqual(validate_file(self.data/'library.json'),[])

    def test_stats_cli_only_json_and_not_dependent_on_cwd(self):
        result = subprocess.run([sys.executable,str(REPO/'scripts'/'library_stats.py'),str(self.root)],cwd=self.root,capture_output=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['recommended_sec'],390)

    def test_invalid_or_incomplete_analysis_never_prints_partial_stats(self):
        self.paths[0].unlink()
        result = subprocess.run([sys.executable,str(REPO/'scripts'/'library_stats.py'),str(self.root)],capture_output=True,encoding='utf-8')
        self.assertEqual(result.returncode,1)
        self.assertEqual(result.stdout,'')
        self.assertIn('缺少分析',result.stderr)

    def test_no_speech_statistics(self):
        self.assertEqual(calculate(REPO/'examples'/'no-speech',data_dir=REPO/'examples'/'no-speech'),
                         {'total_sec':60,'recommended_sec':0,'saved_sec':60})

    def test_decimal_speed_statistics(self):
        values = compute_library_stats({'v':10.5},{'v':{'segments':[
            {'start':0,'end':2.5,'label':'must'},
            {'start':2.5,'end':5.5,'label':'normal'},
            {'start':5.5,'end':9,'label':'speed','speed':1.75},
            {'start':9,'end':10.5,'label':'skip'}]}})
        self.assertEqual(values,{'total_sec':10.5,'recommended_sec':7.5,'saved_sec':3})


if __name__=='__main__':
    unittest.main(verbosity=2)
