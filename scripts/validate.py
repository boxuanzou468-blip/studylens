"""Offline schema and cross-file validation with all actionable errors per run."""
import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import sys
from common import compute_library_stats, read_json, run_cli

try:
    from jsonschema import Draft202012Validator, validators
except ImportError:
    print('错误：缺少 jsonschema，请用当前 Python 执行 -m pip install -r requirements.txt', file=sys.stderr)
    sys.exit(1)

SCHEMAS = Path(__file__).resolve().parents[1] / 'schema'
MISSING = object()


def number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def index_number(value):
    return number(value) and value >= 0 and (type(value) is int or value.is_integer())


FiniteValidator = validators.extend(Draft202012Validator, type_checker=
    Draft202012Validator.TYPE_CHECKER.redefine('number', lambda checker, value: number(value)))


def location(parts):
    result = ''
    for part in parts:
        if isinstance(part, int):
            result += f'[{part}]'
        elif str(part).isidentifier():
            result += ('.' if result else '') + str(part)
        else:
            result += '[' + json.dumps(part, ensure_ascii=False) + ']'
    return result or '$'


@lru_cache(maxsize=3)
def validator(kind):
    schema = read_json(SCHEMAS / f'{kind}.schema.json')
    Draft202012Validator.check_schema(schema)
    return FiniteValidator(schema)


def schema_errors(data, kind):
    result = []
    for error in sorted(validator(kind).iter_errors(data), key=lambda e: str(list(e.absolute_path))):
        where = location(error.absolute_path)
        if error.validator == 'required':
            missing = [name for name in error.validator_value if name not in error.instance]
            message = '缺少必填字段：' + '、'.join(missing)
        elif error.validator == 'type':
            message = f'必须是 {error.validator_value}（number 必须有限，不能使用布尔值或数字字符串）'
        elif error.validator == 'enum':
            message = f'值 {error.instance!r} 不合法，允许值：{error.validator_value}'
        elif error.validator in ('minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum'):
            operator = {'minimum': '≥', 'maximum': '≤', 'exclusiveMinimum': '>', 'exclusiveMaximum': '<'}[error.validator]
            message = f'值 {error.instance!r} 必须 {operator} {error.validator_value}'
        elif error.validator == 'not':
            message = '仅 label="speed" 时允许 speed 字段；请删除此 speed 字段'
        elif error.validator == 'pattern':
            message = '必须包含非空白文字'
        elif error.validator == 'minItems':
            message = f'数组至少需要 {error.validator_value} 项'
        elif error.validator == 'minProperties':
            message = f'对象至少需要 {error.validator_value} 项'
        elif error.validator == 'uniqueItems':
            message = '数组存在重复项，请去重'
        elif error.validator == 'additionalProperties':
            message = '存在未定义字段：' + error.message
        else:
            message = error.message
        result.append(f'{where}：{message}')
    return list(dict.fromkeys(result))


def analysis_errors(data, durations):
    errors = []
    if not isinstance(data, dict):
        return errors
    video_id = data.get('video_id')
    duration = durations.get(video_id) if isinstance(video_id, str) else None
    if isinstance(video_id, str) and duration is None:
        errors.append(f'video_id {video_id!r} 不在 manifest 中，请使用已扫描的影片 id')
    segments = data.get('segments')
    if not isinstance(segments, list):
        return errors
    for i, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        start, end = segment.get('start'), segment.get('end')
        if i == 0 and number(start) and start != 0:
            errors.append(f'segments[0].start ({start}) 必须是 0，请覆盖影片开头')
        if number(start) and number(end) and end <= start:
            errors.append(f'segments[{i}].end ({end}) 必须大于 start ({start})，段落不能为零长或倒退')
        if duration is not None and number(end) and end > duration:
            errors.append(f'segments[{i}].end ({end}) 超出影片时长 duration_sec ({duration})，请缩短段落')
        if i + 1 < len(segments) and isinstance(segments[i + 1], dict):
            following = segments[i + 1].get('start')
            if number(end) and number(following) and abs(following - end) > 0.5 + 1e-9:
                difference = following - end
                detail = f'中间有 {difference:g} 秒空隙，请延长 segments[{i}] 或提前 segments[{i+1}]' if difference > 0 else f'重叠 {-difference:g} 秒，请缩短 segments[{i}] 或推迟 segments[{i+1}]'
                errors.append(f'segments[{i}].end ({end}) ≠ segments[{i+1}].start ({following})：{detail}（容差 0.5 秒）')
        if i == len(segments) - 1 and duration is not None and number(end) and abs(end - duration) > 1 + 1e-9:
            errors.append(f'segments[{i}].end ({end}) 必须等于影片时长 duration_sec ({duration})，请覆盖片尾（容差 1 秒）')
    return errors


def load_data(path, errors):
    try:
        return read_json(path)
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f'{path}：无法读取 JSON：{exc}')
        return MISSING


def load_durations(path, errors):
    data = load_data(path, errors)
    if data is MISSING:
        return {}
    if not isinstance(data, dict) or not isinstance(data.get('videos'), list):
        errors.append(f'{path}：manifest 必须含 videos 数组')
        return {}
    durations = {}
    for i, video in enumerate(data['videos']):
        if not isinstance(video, dict):
            errors.append(f'{path}：videos[{i}] 必须是对象')
            continue
        video_id, duration = video.get('id'), video.get('duration_sec')
        if not isinstance(video_id, str) or not video_id.strip():
            errors.append(f'{path}：videos[{i}].id 必须是非空字符串')
            continue
        if video_id in durations:
            errors.append(f'{path}：videos[{i}].id {video_id!r} 重复')
            continue
        if not number(duration) or duration <= 0:
            errors.append(f'{path}：videos[{i}].duration_sec 必须是有限正数')
            continue
        durations[video_id] = duration
    if not data['videos']:
        errors.append(f'{path}：videos 不能为空')
    return durations


def load_analyses(directory, durations, errors):
    analyses, all_valid = {}, True
    if not directory.is_dir():
        errors.append(f'{directory}：分析目录不存在，请先逐支完成分析')
        return analyses, False
    for path in sorted(directory.glob('*.json')):
        data = load_data(path, errors)
        if data is MISSING:
            all_valid = False
            continue
        issues = schema_errors(data, 'video_analysis') + analysis_errors(data, durations)
        errors.extend(f'{path}：{issue}' for issue in issues)
        all_valid = all_valid and not issues
        video_id = data.get('video_id') if isinstance(data, dict) else None
        if isinstance(video_id, str):
            if video_id in analyses:
                errors.append(f'{path}：video_id {video_id!r} 存在重复分析文件')
                all_valid = False
            else:
                analyses[video_id] = data
    for video_id in durations:
        if video_id not in analyses:
            errors.append(f'{directory}：影片 {video_id!r} 缺少分析，无法完整校验 library')
            all_valid = False
    return analyses, all_valid


def library_errors(data, durations, analyses, check_stats=True):
    errors = []
    if not isinstance(data, dict):
        return errors
    references = []
    learning_seen = set()
    path = data.get('learning_path')
    if isinstance(path, list):
        references.extend((f'learning_path[{i}]', ref) for i, ref in enumerate(path))
    topics = data.get('topic_index')
    if isinstance(topics, dict):
        for topic, refs in topics.items():
            if isinstance(refs, list):
                references.extend((f'topic_index[{json.dumps(topic, ensure_ascii=False)}][{i}]', ref) for i, ref in enumerate(refs))
    for where, ref in references:
        if not isinstance(ref, dict):
            continue
        video_id, index = ref.get('video_id'), ref.get('segment_index')
        if not isinstance(video_id, str):
            continue
        if video_id not in durations:
            errors.append(f'{where}.video_id ({video_id!r}) 不在 manifest 中')
        analysis = analyses.get(video_id)
        if not analysis:
            errors.append(f'{where}.video_id ({video_id!r}) 没有对应分析文件')
            continue
        segments = analysis.get('segments')
        if index_number(index) and isinstance(segments, list) and index >= len(segments):
            errors.append(f'{where}.segment_index ({index}) 越界；影片 {video_id!r} 只有 {len(segments)} 段，索引从 0 开始')
        elif index_number(index) and isinstance(segments, list) and where.startswith('learning_path'):
            key = (video_id, int(index))
            if key in learning_seen:
                errors.append(f'{where} 重复引用影片 {video_id!r} 的段落 {int(index)}，请删除重复项')
            learning_seen.add(key)
            segment = segments[int(index)]
            if isinstance(segment, dict) and segment.get('label') == 'skip':
                errors.append(f'{where} 引用了 skip 段落，不应列入推荐学习路径，请移除此引用')
    if path == [] and any(isinstance(s, dict) and s.get('label') != 'skip'
                          for a in analyses.values() if isinstance(a, dict) and isinstance(a.get('segments'), list)
                          for s in a['segments']):
        errors.append('learning_path 不能为空：存在可学习的非 skip 段落；只有全部可跳过时才允许空路径')
    stats = data.get('stats')
    if isinstance(stats, dict):
        total, recommended, saved = (stats.get(key) for key in ('total_sec', 'recommended_sec', 'saved_sec'))
        if all(number(n) for n in (total, recommended, saved)):
            if abs((total - recommended) - saved) > 0.01 + 1e-9:
                errors.append(f'stats.saved_sec ({saved}) ≠ total_sec - recommended_sec ({total - recommended:g})')
            if recommended > total:
                errors.append(f'stats.recommended_sec ({recommended}) 不能超过 total_sec ({total})')
        if check_stats and durations:
            for key, expected in compute_library_stats(durations, analyses).items():
                actual = stats.get(key)
                if number(actual) and abs(actual - expected) > 0.01 + 1e-9:
                    errors.append(f'stats.{key} ({actual}) 与全部分析重算结果 ({expected:g}) 不符（容差 0.01 秒）')
    return errors


def detect_kind(data, path):
    if isinstance(data, dict):
        if 'segments' in data or 'video_id' in data:
            return 'video_analysis'
        if 'learning_path' in data or 'topic_index' in data or 'stats' in data:
            return 'library'
        if 'goals' in data or 'level' in data or 'video_folder' in data:
            return 'profile'
    if 'profile' in path.stem:
        return 'profile'
    if 'library' in path.stem:
        return 'library'
    if 'analysis' in path.stem or path.parent.name == 'analysis':
        return 'video_analysis'
    raise ValueError('无法推断类型，请传 --kind profile|video_analysis|library')


def infer_manifest(path):
    for parent in path.parents:
        for candidate in (parent / 'manifest.json', parent / '.studylens' / 'manifest.json'):
            if candidate.is_file():
                return candidate
    return path.parent / 'manifest.json'


def validate_file(path, kind='auto', manifest=None, analysis_dir=None):
    path = Path(path).resolve()
    errors = []
    data = load_data(path, errors)
    if data is MISSING:
        return errors
    try:
        kind = detect_kind(data, path) if kind == 'auto' else kind
    except ValueError as exc:
        return [str(exc)]
    errors.extend(schema_errors(data, kind))
    if kind != 'profile':
        manifest = Path(manifest).resolve() if manifest else infer_manifest(path)
        before = len(errors)
        durations = load_durations(manifest, errors)
        metadata_valid = len(errors) == before
        if kind == 'video_analysis':
            errors.extend(analysis_errors(data, durations))
        else:
            directory = Path(analysis_dir).resolve() if analysis_dir else manifest.parent / 'analysis'
            analyses, all_valid = load_analyses(directory, durations, errors)
            errors.extend(library_errors(data, durations, analyses, metadata_valid and all_valid))
    return list(dict.fromkeys(errors))


def analysis_warnings(data, durations):
    if not isinstance(data, dict) or not isinstance(data.get('segments'), list):
        return []
    segments, warnings = data['segments'], []
    video_id = data.get('video_id')
    duration = durations.get(video_id) if isinstance(video_id, str) else None
    for i, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        start, end = segment.get('start'), segment.get('end')
        if not number(start) or not number(end) or end <= start:
            continue
        length = end - start
        if length > 480:
            warnings.append(f'segments[{i}] 长达 {length:g} 秒（超过 8 分钟），建议按知识点细分')
        if duration is not None and duration >= 180 and length < 20 and segment.get('label') != 'skip' and 0 < i < len(segments) - 1:
            warnings.append(f'segments[{i}] 只有 {length:g} 秒（短于 20 秒），建议合并相邻内容')
    if duration and duration > 600 and len(segments) == 1:
        warnings.append(f'影片 {duration:g} 秒（超过 10 分钟）只有 1 段，建议重新分段')
    return warnings


def freshness_warning(profile_path, analysis_path):
    """Conservative mtime heuristic; does not claim to detect semantic changes."""
    try:
        if profile_path.stat().st_mtime_ns > analysis_path.stat().st_mtime_ns:
            return '学习目标可能已更新，分析可能过期；若要依新目标重新标注请重跑分析'
    except OSError:
        pass  # Missing inputs are separately reported as validation errors.
    return None


def display_path(path, manifest=None):
    path = Path(path).resolve()
    root = Path(manifest).resolve().parent if manifest else infer_manifest(path).parent
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def inspect_file(path, kind='auto', manifest=None, analysis_dir=None):
    """Return errors and non-fatal warnings; validate_file retains its old API."""
    errors = validate_file(path, kind, manifest, analysis_dir)
    path = Path(path).resolve()
    ignored, warnings = [], []
    data = load_data(path, ignored)
    if data is MISSING:
        return errors, warnings
    try:
        kind = detect_kind(data, path) if kind == 'auto' else kind
    except ValueError:
        return errors, warnings
    if kind == 'profile':
        return errors, warnings
    manifest = Path(manifest).resolve() if manifest else infer_manifest(path)
    durations = load_durations(manifest, ignored)
    if kind == 'video_analysis':
        warnings.extend(f'{display_path(path, manifest)}：{w}' for w in analysis_warnings(data, durations))
        stale = freshness_warning(manifest.parent / 'profile.json', path)
        if stale:
            warnings.append(f'{display_path(path, manifest)}：{stale}')
    else:
        directory = Path(analysis_dir).resolve() if analysis_dir else manifest.parent / 'analysis'
        for analysis_path in sorted(directory.glob('*.json')):
            item = load_data(analysis_path, ignored)
            warnings.extend(f'{display_path(analysis_path, manifest)}：{w}' for w in analysis_warnings(item, durations))
            stale = freshness_warning(manifest.parent / 'profile.json', analysis_path)
            if stale:
                warnings.append(f'{display_path(analysis_path, manifest)}：{stale}')
    return errors, list(dict.fromkeys(warnings))


def main():
    parser = argparse.ArgumentParser(description='离线检查 profile、影片分析或 library；列出所有字段、时间及引用错误。')
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--kind', choices=['auto', 'profile', 'video_analysis', 'library'], default='auto')
    parser.add_argument('--manifest', type=Path, help='时长/id 来源；默认从文件所在目录向上寻找 manifest.json')
    parser.add_argument('--analysis-dir', type=Path, help='library 引用的分析目录；默认 manifest 同级 analysis/')
    args = parser.parse_args()
    total, warning_count = 0, 0
    seen_warnings = set()
    for path in args.files:
        try:
            errors, warnings = inspect_file(path, args.kind, args.manifest, args.analysis_dir)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors = [f'无法完成校验：{exc}']
            warnings = []
        warning_root = (Path(args.manifest).resolve() if args.manifest else infer_manifest(Path(path).resolve())).parent
        warnings = [w for w in warnings if (warning_root, w) not in seen_warnings]
        seen_warnings.update((warning_root, w) for w in warnings)
        shown = display_path(path, args.manifest)
        if errors:
            print(f'FAIL {shown}：{len(errors)} 个错误')
            for error in errors:
                print(f'  - {error}')
        else:
            print(f'PASS（{len(warnings)} 个警告） {shown}' if warnings else f'PASS {shown}')
        for warning in warnings:
            print(f'  WARNING：{warning}')
        total += len(errors)
        warning_count += len(warnings)
    print(f'共检查 {len(args.files)} 个文件，{total} 个错误，{warning_count} 个警告')
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(run_cli(main))
