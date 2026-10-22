"""Check dependencies without installing or downloading anything."""
import argparse
import importlib
import platform
import shutil
import sys
from common import run_cli
from transcribe import DOWNLOAD_HELP


def main():
    parser = argparse.ArgumentParser(description='检查 Python ≥3.10、ffmpeg/ffprobe、faster-whisper 和 jsonschema。')
    parser.parse_args()
    print(DOWNLOAD_HELP)
    print('GPU 运行库说明：https://github.com/SYSTRAN/faster-whisper#gpu （不会自动安装）')
    missing = []
    print(f'Python {platform.python_version()}: {sys.executable}')
    if sys.version_info < (3, 10):
        missing.append('安装 Python 3.10 或更新版本：https://www.python.org/downloads/')
    for executable in ('ffmpeg', 'ffprobe'):
        found = shutil.which(executable)
        print(f'{executable}: {found or "缺少"}')
        if not found:
            manager = {'Windows': 'winget install --id Gyan.FFmpeg -e',
                       'Darwin': 'brew install ffmpeg'}.get(platform.system(), 'sudo apt-get install ffmpeg')
            missing.append(f'{manager} （安装后确保 ffmpeg 和 ffprobe 在 PATH 中）')
    for name, package in (('faster_whisper', 'faster-whisper'), ('jsonschema', 'jsonschema')):
        try:
            importlib.import_module(name)
            print(f'{package}: 可导入')
        except Exception as exc:
            print(f'{package}: 缺少或无法导入 ({exc})')
            missing.append(f'"{sys.executable}" -m pip install "{package}"')
    try:
        import av
        print(f'PyAV: {av.__version__}')
        if not 11 <= int(av.__version__.split('.')[0]) < 17:
            missing.append(f'"{sys.executable}" -m pip install "av>=11,<17"')
    except Exception as exc:
        print(f'PyAV 无法导入: {exc}')
        missing.append(f'"{sys.executable}" -m pip install "av>=11,<17"')
    try:
        import ctranslate2
        print(f'可见 CUDA 设备: {ctranslate2.get_cuda_device_count()} （实际运行还需要兼容 CUDA/cuDNN）')
    except Exception as exc:
        print(f'CUDA 检测不可用: {exc}；可使用 CPU')
    if missing:
        print('\n修复指令（PowerShell 中在引号包裹的程序路径前加 &）：')
        for command in dict.fromkeys(missing):
            print(f'  {command}')
        return 1
    print('环境检查通过；模型首次使用可能需要联网下载，未验证 GPU 实际推理。')
    return 0


if __name__ == '__main__':
    sys.exit(run_cli(main))
