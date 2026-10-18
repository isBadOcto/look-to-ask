# Optional local NVIDIA runtime. Does not change the driver, system PATH or app settings.
param([string]$Python = (Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'))
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Supply -Python with a Python executable that has pip. The app remains usable on CPU.'
}
if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is required on Windows.' }
$gpuParent = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'LookToAsk'))
$gpuTarget = [IO.Path]::GetFullPath((Join-Path $gpuParent 'gpu'))
if (-not $gpuTarget.StartsWith($gpuParent + [IO.Path]::DirectorySeparatorChar)) {
    throw 'Unexpected GPU runtime destination.'
}
New-Item -ItemType Directory -Path $gpuTarget -Force | Out-Null
& $Python -m pip install --only-binary=:all: --no-deps --upgrade --target $gpuTarget `
    'nvidia-cublas-cu12==12.8.4.1' 'nvidia-cudnn-cu12==9.10.2.21' 'nvidia-cuda-runtime-cu12==12.8.90'
if ($LASTEXITCODE -ne 0) { throw 'GPU runtime installation failed; CPU fallback remains available.' }
Write-Output 'NVIDIA_RUNTIME_INSTALLED. Restart Look to Ask and prepare the speech model; verify GPU in its status.'
