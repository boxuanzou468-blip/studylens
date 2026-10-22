param([Parameter(Mandatory=$true)][string]$OutputFolder)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $OutputFolder -Force | Out-Null
function Invoke-FFmpeg([string[]]$FfmpegArgs) {
    & ffmpeg @FfmpegArgs
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed: $LASTEXITCODE" }
}
foreach ($name in @('中文字幕', '英文字幕', '样式字幕')) {
    Invoke-FFmpeg @('-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=navy:s=640x360:r=10:d=8','-c:v','libx264','-pix_fmt','yuv420p',(Join-Path $OutputFolder "$name.mp4"))
}
@'
1
00:00:00,000 --> 00:00:03,000
第一节：认识学习目标。

2
00:00:03,000 --> 00:00:08,000
第二节：整理知识点，并安排复习。
'@ | Set-Content -LiteralPath (Join-Path $OutputFolder '中文字幕.srt') -Encoding utf8
@'
WEBVTT

intro
00:00.000 --> 00:03.000 align:start
Set a learning goal.

00:03.000 --> 00:08.000
Review with a clear plan.
'@ | Set-Content -LiteralPath (Join-Path $OutputFolder '英文字幕.vtt') -Encoding utf8
@'
[Script Info]
ScriptType: v4.00+
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:03.00,Default,,0,0,0,,{\b1}建立目录
Dialogue: 0,0:00:03.00,0:00:08.00,Default,,0,0,0,,标注重点\N保留时间戳
'@ | Set-Content -LiteralPath (Join-Path $OutputFolder '样式字幕.ass') -Encoding utf8
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voice = $synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'zh-CN' } | Select-Object -First 1
    if (-not $voice) { throw '没有中文 TTS 声音，无法制作中文转录素材' }
    $synth.SelectVoice($voice.VoiceInfo.Name)
    $synth.Rate = -1
    $wav = Join-Path $OutputFolder '中文语音.wav'
    $synth.SetOutputToWaveFile($wav)
    $text = '大家好，今天我们学习如何制定有效的学习计划。首先，要明确自己最想掌握的知识，把一个大目标拆成几个小目标。比如学习电子表格，可以先认识单元格，再练习公式，最后制作图表。第二，要安排适合自己的学习时间，每天坚持二十分钟，比周末一次学习几个小时更容易保持。第三，学习过程中要记录关键知识点，遇到不懂的地方先写下来，再寻找具体例子。第四，看完一段课程以后，尝试用自己的话解释刚才的内容，并完成一个小练习。最后，每周回顾一次学习记录，检查已经掌握了什么，还有哪些问题需要继续练习。今天的重点是明确目标，分步练习，及时复习。希望大家都能找到适合自己的学习方法。'
    $text | Set-Content -LiteralPath (Join-Path $OutputFolder '中文语音-原文.txt') -Encoding utf8
    $synth.Speak($text)
} finally { $synth.Dispose() }
Invoke-FFmpeg @('-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=darkgreen:s=640x360:r=10','-i',$wav,'-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',(Join-Path $OutputFolder '中文语音无字幕.mp4'))
Write-Output "测试素材已生成: $OutputFolder"
