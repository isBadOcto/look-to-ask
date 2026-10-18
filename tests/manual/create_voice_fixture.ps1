# 本地合成的测试音频；只在 tests/fixtures 中生成，不录麦克风，不用于运行时回退。
$ErrorActionPreference = 'Stop'
$fixtureDirectory = Join-Path $PSScriptRoot '../fixtures'
New-Item -ItemType Directory -Force $fixtureDirectory | Out-Null
$fixturePath = Join-Path $fixtureDirectory 'local-voice-zh.wav'
$fixtureVoice = New-Object -ComObject SAPI.SpVoice
$fixtureTokens = $fixtureVoice.GetVoices()
$fixtureFound = $false
for ($fixtureIndex = 0; $fixtureIndex -lt $fixtureTokens.Count; $fixtureIndex++) {
    if ($fixtureTokens.Item($fixtureIndex).GetDescription() -match 'Huihui') {
        $fixtureVoice.Voice = $fixtureTokens.Item($fixtureIndex)
        $fixtureFound = $true
        break
    }
}
if (-not $fixtureFound) { throw '需要 Windows 中文 Huihui SAPI 语音；此测试不安装或回退伪造音频。' }
$fixtureStream = New-Object -ComObject SAPI.SpFileStream
$fixtureStream.Format.Type = 22 # 22.05 kHz, mono, PCM16
$fixtureStream.Open($fixturePath, 3, $false)
try {
    $fixtureVoice.AudioOutputStream = $fixtureStream
    $fixtureVoice.Speak('这个是什么意思？为什么这里会报错？') | Out-Null
} finally {
    $fixtureStream.Close()
}
Write-Output 'SYNTHETIC_TEST_FIXTURE_CREATED (no microphone; ignored WAV under tests/fixtures)'
