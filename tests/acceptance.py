"""Reproduce batch-one checks using generated fixtures, writing evidence outside repo."""
import argparse
from difflib import SequenceMatcher
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from common import read_json, run_cli, write_json
from transcribe import check_segments, parse_subtitle


def main():
    parser = argparse.ArgumentParser(description='第一批验收：需要 create_fixtures.ps1 制作的素材和可用本地模型。')
    parser.add_argument('folder', type=Path)
    parser.add_argument('--model', required=True, help='现有本地 small/tiny 模型目录')
    parser.add_argument('--force-first', action='store_true', help='首轮强制重做，第二轮必须全部跳过')
    args = parser.parse_args()
    media = args.folder.resolve()
    logs = media / '.studylens' / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    commands = []

    def run(label, *arguments):
        command = [sys.executable, *map(str, arguments)]
        print(f'RUN {label}', flush=True)
        result = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace', env=env)
        output = result.stdout + result.stderr
        (logs / f'{label}.log').write_text(output, encoding='utf-8')
        commands.append({'label': label, 'argv': command, 'exit_code': result.returncode})
        print(output, end='', flush=True)
        if result.returncode:
            raise ValueError(f'{label} 失败，详见 {logs / (label + ".log")}')
        return output

    run('environment', REPO / 'scripts' / 'check_env.py')
    run('unittest', '-m', 'unittest', 'discover', '-s', REPO / 'tests', '-v')
    run('scan', REPO / 'scripts' / 'scan.py', media)
    command = [REPO / 'scripts' / 'transcribe.py', media, '--model', args.model,
               '--language', 'zh', '--local-files-only']
    first = run('transcribe-first-final', *command, *(['--force'] if args.force_first else []))
    manifest = read_json(media / '.studylens' / 'manifest.json')
    if len(manifest['videos']) != 4:
        raise ValueError('验收目录应只包含四支生成的测试影片')
    transcripts = media / '.studylens' / 'transcripts'
    before = {v['id']: (transcripts / (v['id'] + '.json')).stat().st_mtime_ns for v in manifest['videos']}
    second = run('transcribe-resume', *command)
    if second.count('SKIP 已完成') != 4:
        raise ValueError('第二轮没有全部跳过')
    voice_result = None
    summary = []
    for video in manifest['videos']:
        path = transcripts / (video['id'] + '.json')
        if path.stat().st_mtime_ns != before[video['id']]:
            raise ValueError('续跑重写了缓存文件')
        data = read_json(path)
        check_segments(data['segments'], video['duration_sec'])
        if video['subtitle']:
            if data['source'] != 'subtitle' or data['segments'] != parse_subtitle(media / video['subtitle']):
                raise ValueError('字幕转换结果不一致')
        else:
            if data['source'] != 'whisper' or not data['segments']:
                raise ValueError('真实语音没有通过 Whisper 转录')
            voice_result = data
            run('chunk-index', REPO / 'scripts' / 'chunk.py', media, '--video-id', video['id'])
            run('chunk-text', REPO / 'scripts' / 'chunk.py', media, '--video-id', video['id'], '--chunk', '1')
            run('chunk-small', REPO / 'scripts' / 'chunk.py', media, '--video-id', video['id'], '--max-chars', '128')
        summary.append({'filename': video['filename'], 'duration_sec': video['duration_sec'],
                        'source': data['source'], 'segment_count': len(data['segments'])})
    expected = (media / '中文语音-原文.txt').read_text(encoding='utf-8-sig')
    normalize = lambda s: re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', s).lower()
    recognized = ''.join(s['text'] for s in voice_result['segments'])
    ratio = SequenceMatcher(None, normalize(expected), normalize(recognized), autojunk=False).ratio()
    if ratio < 0.6:
        raise ValueError(f'TTS 转录与原文差异过大: {ratio:.3f}')
    result = {'status': 'passed', 'videos': summary, 'resume_skipped': 4,
              'cache_mtimes_unchanged': True, 'tts_character_similarity': round(ratio, 4),
              'similarity_note': '规范化字符序列相似度，仅为合成语音样本的粗略核验，不是课程识别准确率。',
              'actual_whisper_device': voice_result['device'], 'commands': commands}
    run('pip-check', '-m', 'pip', 'check')
    # Include pip-check in the recorded command list.
    write_json(logs / 'acceptance-summary.json', result)
    print(f'PASS 四支素材、真实语音转录、续跑、分块；TTS 字符相似度 {ratio:.2%}')


if __name__ == '__main__':
    sys.exit(run_cli(main))
