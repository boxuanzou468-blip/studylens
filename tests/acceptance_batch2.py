"""Second-batch reproducible evidence; generated media stays outside the repository."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from common import read_json, run_cli, write_json
from chunk import build_chunks
from transcribe import LocalWhisper, normalize_segments


def main():
    parser = argparse.ArgumentParser(description='第二批完整验收：需已有第一批素材和本地 Whisper 模型。')
    parser.add_argument('folder', type=Path)
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    media = args.folder.resolve()
    logs = media / '.studylens' / 'logs' / 'batch2'
    logs.mkdir(parents=True, exist_ok=True)
    commands = []
    env = dict(os.environ, PYTHONIOENCODING='utf-8')

    def run(label, *arguments, expected=0):
        command = [sys.executable, *map(str, arguments)]
        print('RUN ' + label, flush=True)
        result = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace', env=env)
        output = result.stdout + result.stderr
        (logs / f'{label}.log').write_text(output, encoding='utf-8')
        commands.append({'label': label, 'argv': command, 'exit_code': result.returncode, 'expected_exit_code': expected})
        print(output, end='', flush=True)
        if result.returncode != expected:
            raise ValueError(f'{label} 退出码 {result.returncode}，预期 {expected}')
        return output

    run('environment', REPO / 'scripts' / 'check_env.py')
    run('unittest', '-m', 'unittest', 'discover', '-s', REPO / 'tests', '-v')
    manifest = read_json(media / '.studylens' / 'manifest.json')
    transcript_paths = [media / '.studylens' / 'transcripts' / (v['id'] + '.json') for v in manifest['videos']]

    def mtimes():
        return {p.name: p.stat().st_mtime_ns for p in transcript_paths}

    before = mtimes()
    reused = run('reuse-existing', REPO / 'scripts' / 'transcribe.py', media,
                 '--model', args.model, '--language', 'zh', '--local-files-only')
    if reused.count('SKIP 已完成') != 4 or mtimes() != before:
        raise ValueError('已有转录未被原样复用')
    run('transcribe-vad', REPO / 'scripts' / 'transcribe.py', media, '--model', args.model,
        '--language', 'zh', '--local-files-only', '--initial-prompt', '以下是普通话的句子，使用简体中文和标点。', '--force')
    before = mtimes()
    resumed = run('reuse-changed-parameters', REPO / 'scripts' / 'transcribe.py', media,
                  '--device', 'cpu', '--compute-type', 'int8', '--no-vad', '--beam-size', '1', '--local-files-only')
    if (resumed.count('SKIP 已完成') != 4 or mtimes() != before or
            '参数与上次不同，若要重做请加 --force' not in resumed or '加载本地模型' in resumed):
        raise ValueError('参数变化没有按要求复用并提示')
    voice = next(v for v in manifest['videos'] if v['subtitle'] is None and v['has_audio'])
    voice_data = read_json(media / '.studylens' / 'transcripts' / (voice['id'] + '.json'))
    if voice_data['source'] != 'whisper' or not voice_data['segments']:
        raise ValueError('真实 VAD 转录没有文本')
    run('chunk-index', REPO / 'scripts' / 'chunk.py', media, '--video-id', voice['id'])
    run('chunk-text', REPO / 'scripts' / 'chunk.py', media, '--video-id', voice['id'], '--chunk', '1')
    examples = REPO / 'examples'
    positive = [examples / 'profile.json', *sorted((examples / 'analysis').glob('*.json')), examples / 'library.json']
    negative = sorted((examples / 'invalid').glob('*.json'))
    run('validate-positive', REPO / 'scripts' / 'validate.py', *positive)
    failures = run('validate-negative', REPO / 'scripts' / 'validate.py', *negative, expected=1)
    if failures.count('FAIL ') != len(negative):
        raise ValueError('反例没有全部报错')
    typical = '这是典型中文字幕内容。'
    compact = build_chunks([{'start': i*3, 'end': (i+1)*3, 'text': typical} for i in range(200)])
    ratio = len(typical) * 200 / sum(len(c['text']) for c in compact)
    if ratio < 0.8:
        raise ValueError('典型字幕正文占比未达到 80%')
    log = io.StringIO()
    with redirect_stderr(log):
        repaired = normalize_segments([{'start': 1, 'end': 1, 'text': '嗯'},
                                       {'start': 1, 'end': 3, 'text': '好'},
                                       {'start': 0.5, 'end': 1, 'text': '倒退'}], 10)
    (logs / 'repair.log').write_text(log.getvalue(), encoding='utf-8')
    engine = LocalWhisper(argparse.Namespace(language='zh', beam_size=5, no_vad=False, initial_prompt=None))
    engine.model = Mock()
    engine.model.transcribe.return_value = ((SimpleNamespace(start=i*4.8, end=(i+1)*4.8, text='内容') for i in range(1500)), SimpleNamespace(language='zh'))
    progress = io.StringIO()
    with redirect_stdout(progress):
        engine.consume(Path('synthetic-progress-only.mp4'), 7200)
    (logs / 'progress-simulation.log').write_text(progress.getvalue(), encoding='utf-8')
    run('pip-check', '-m', 'pip', 'check')
    for name in ('scan.py', 'transcribe.py', 'chunk.py', 'check_env.py', 'validate.py'):
        run('help-' + Path(name).stem, REPO / 'scripts' / name, '--help')
    result = {'status': 'passed', 'positive_files': len(positive), 'negative_files': len(negative),
              'resume_skipped': 4, 'cache_mtimes_unchanged': True, 'changed_parameter_warning': True,
              'actual_whisper_device': voice_data['device'], 'actual_vad_transcript_segments': len(voice_data['segments']),
              'typical_200_cues_substantive_ratio': round(ratio, 4),
              'progress_lines_for_1500_segments': progress.getvalue().count('转录进度'),
              'repair_example': repaired, 'commands': commands}
    write_json(logs / 'acceptance-summary.json', result)
    print(f'PASS 第二批：正例 {len(positive)}，反例 {len(negative)}；正文占比 {ratio:.2%}；进度 {result["progress_lines_for_1500_segments"]} 行')


if __name__ == '__main__':
    sys.exit(run_cli(main))
