"""Authored test analyses plus isolated real media copies for browser acceptance."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from common import write_json
from scan import scan
from build_report import create_report

XSS = '</script><img src=x onerror=alert(1)>'


def silent_analysis(video_id, duration):
    return {'video_id': video_id, 'title': '无语音演示：需要人工查看画面',
            'summary': '影片没有可供分析的语音文本。此记录不推测画面中的知识内容。',
            'topics': ['无语音'], 'relevance': 0,
            'segments': [{'start': 0, 'end': duration, 'title': '无语音内容',
                          'summary': '没有可读的语音或字幕。请根据实际画面自行判断是否需要观看。',
                          'keypoints': ['无法依据语音文本判断内容'], 'label': 'skip', 'reason': '無語音內容，無法判斷'}]}


def profile(folder):
    return {'video_folder': str(folder), 'goals': ['制定可执行的学习计划', '掌握复习与主动回忆的方法'],
            'level': 'basic', 'language': 'zh-CN'}


def summary_library(manifest, analyses):
    total = sum(v['duration_sec'] for v in manifest['videos'])
    recommended, path, topics = 0, [], {}
    for video in manifest['videos']:
        analysis = analyses[video['id']]
        for i, segment in enumerate(analysis['segments']):
            ref = {'video_id': video['id'], 'segment_index': i}
            for topic in analysis['topics']:
                topics.setdefault(topic, []).append(ref.copy())
            if segment['label'] != 'skip':
                path.append({**ref, 'reason': segment['reason']})
                recommended += (segment['end']-segment['start'])/(segment['speed'] if segment['label']=='speed' else 1)
    return {'learning_path': path, 'topic_index': topics,
            'stats': {'total_sec': total, 'recommended_sec': recommended, 'saved_sec': total-recommended}}


def main():
    parser = argparse.ArgumentParser(description='仅在专用测试目录准备第三批素材、分析与报告。')
    parser.add_argument('folder', type=Path, help='第一批测试素材目录')
    args = parser.parse_args()
    media = args.folder.resolve()
    # This standalone example is fictional metadata; no actual video is asserted.
    example = REPO / 'examples' / 'no-speech'
    video_id = hashlib.sha256(b'silent-example.mp4').hexdigest()[:16]
    video = {'id': video_id, 'path': 'silent-example.mp4', 'filename': 'silent-example.mp4',
             'duration_sec': 60, 'has_audio': False, 'fingerprint': {'size': 0, 'mtime_ns': 0},
             'subtitle': None, 'subtitle_fingerprint': None}
    manifest = {'version': 1, 'videos': [video], 'errors': []}
    analysis = silent_analysis(video_id, 60)
    write_json(example / 'manifest.json', manifest)
    write_json(example / 'profile.json', profile('.'))
    write_json(example / 'analysis' / (video_id+'.json'), analysis)
    write_json(example / 'library.json', summary_library(manifest, {video_id: analysis}))
    root = media / '.studylens' / 'batch3-real'
    root.mkdir(parents=True, exist_ok=True)
    for source in media.iterdir():
        if source.is_file() and source.suffix.lower() in ('.mp4', '.srt', '.vtt', '.ass'):
            shutil.copy2(source, root / source.name)
    special = root / '路径 空格#100%' / '中文 #100%.mp4'
    special.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(media / '中文字幕.mp4', special)
    shutil.copy2(media / '中文字幕.srt', special.with_suffix('.srt'))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(media/'中文字幕.mp4'),
                    '-c:v', 'ffv1', str(root/'浏览器不支持.avi')], check=True)
    manifest = scan(root)
    if manifest['errors']:
        raise ValueError(manifest['errors'])
    data = root / '.studylens'
    write_json(data/'manifest.json', manifest)
    write_json(data/'profile.json', profile(root))
    analyses = {}
    for v in manifest['videos']:
        if v['filename'] == '中文语音无字幕.mp4':
            # Human/AI-authored from the previously inspected timestamped transcript.
            segments = [
                {'start': 0, 'end': 24, 'title': '把目标拆成可完成的小任务', 'label': 'must',
                 'summary': '先明确最想掌握的知识，再把大目标拆成小目标。电子表格示例从单元格、公式逐步到图表。',
                 'keypoints': ['明确学习目标', '将任务分步执行'], 'reason': '直接对应制定可执行学习计划的目标。'},
                {'start': 24, 'end': 47, 'title': '安排时间并记录疑问', 'label': 'normal',
                 'summary': '每天预留固定学习时间，并在学习过程中记录重点。遇到不懂的地方先记下来，再寻找具体例子。',
                 'keypoints': ['固定时间持续学习', '记录疑问并寻找例子'], 'reason': '补充学习计划落地所需的时间与笔记方法。'},
                {'start': 47, 'end': 79, 'title': '主动回忆与每周复盘', 'label': 'speed', 'speed': 1.75,
                 'summary': '看完课程后用自己的话解释内容，并完成小练习。每周检查已掌握的知识和待练习的问题。',
                 'keypoints': ['闭卷解释内容', '通过练习与复盘调整任务'], 'reason': '测试用户已有基础，用一点七五倍速复习此方法。'},
                {'start': 79, 'end': v['duration_sec'], 'title': '片尾静音', 'label': 'skip',
                 'summary': '语音在此之前已结束。剩余部分没有新的语音知识点。',
                 'keypoints': ['片尾无新语音内容'], 'reason': '只包含片尾静音，可以跳过。'}]
            analysis = {'video_id': v['id'], 'title': '学习计划：从目标到复盘', 'summary': '用具体例子讲解目标拆解、时间安排和每周复盘。适合快速建立学习计划。',
                        'topics': ['学习目标', '复盘'], 'relevance': 98, 'segments': segments}
        elif v['filename'].endswith('.avi'):
            analysis = silent_analysis(v['id'], v['duration_sec'])
            analysis['title'] = '无语音格式兼容性测试'
        else:
            title = XSS if v['path'].startswith('路径 ') else {'中文字幕.mp4': '认识学习目标与复习', '样式字幕.mp4': '建立目录与标注重点', '英文字幕.mp4': '用英文复习学习计划'}[v['filename']]
            analysis = {'video_id': v['id'], 'title': title, 'summary': '测试字幕介绍学习目标或知识整理。该短片用于核验报告跳转和标签展示。',
                        'topics': ['学习目标'], 'relevance': 85,
                        'segments': [{'start': 0, 'end': v['duration_sec'], 'title': '学习目标与整理方法',
                                      'summary': '字幕提供学习目标与复习提示。可用这个短片快速回顾基本步骤。',
                                      'keypoints': ['明确目标', '记录并复习知识'], 'label': 'normal', 'reason': '提供学习计划的基础背景。'}]}
        analyses[v['id']] = analysis
        write_json(data/'analysis'/(v['id']+'.json'), analysis)
    write_json(data/'library.json', summary_library(manifest, analyses))
    create_report(root)
    create_report(REPO/'examples', REPO/'examples')
    write_json(media/'.studylens'/'logs'/'batch3'/'fixture-paths.json', {
        'real_root': str(root), 'real_report': str(root/'studylens-report.html'),
        'example_report': str(REPO/'examples'/'studylens-report.html'),
        'voice_id': next(v['id'] for v in manifest['videos'] if v['filename']=='中文语音无字幕.mp4'),
        'special_id': next(v['id'] for v in manifest['videos'] if v['path'].startswith('路径 ')),
        'unsupported_id': next(v['id'] for v in manifest['videos'] if v['filename'].endswith('.avi')),
        'no_speech_example': str(example)})


if __name__ == '__main__':
    main()
