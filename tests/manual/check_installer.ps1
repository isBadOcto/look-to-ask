# Real current-user installer test. Never overwrite an existing installation.
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version = '0.4.6',
    [ValidatePattern('^[a-z0-9-]{1,32}$')][string]$Attempt = 'initial'
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$checkName = "install-check-$Version"
if ($Attempt -ne 'initial') { $checkName += "-$Attempt" }
$checkRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot ".venv/$checkName"))
$installTarget = [IO.Path]::GetFullPath((Join-Path $checkRoot 'program'))
$registryTarget = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\LookToAsk'
$shortcutsTarget = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Look to Ask'
$installerPath = Join-Path $projectRoot "dist/LookToAsk-$Version-Setup.exe"
if (Test-Path $checkRoot) { throw 'Use a fresh check directory; nothing was overwritten.' }
if ((Test-Path $registryTarget) -or (Test-Path $shortcutsTarget) -or
    (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs/Look to Ask'))) {
    throw 'Existing installation/shortcuts detected; automated installation test skipped.'
}
if (-not $installTarget.StartsWith($checkRoot + [IO.Path]::DirectorySeparatorChar)) {
    throw 'Unsafe installation target.'
}
New-Item -ItemType Directory -Path $checkRoot | Out-Null
$installProcess = Start-Process -FilePath $installerPath -ArgumentList @('/S', "/D=$installTarget") -WindowStyle Hidden -Wait -PassThru
if ($installProcess.ExitCode -ne 0) { throw "Installer exit: $($installProcess.ExitCode)" }
$installedExecutable = Join-Path $installTarget 'LookToAsk.exe'
$registeredLocation = (Get-ItemProperty -LiteralPath $registryTarget).InstallLocation
if ($registeredLocation -ne $installTarget -or -not (Test-Path $installedExecutable)) {
    throw 'Installed files/registry location do not match the verified target.'
}
if (-not (Test-Path (Join-Path $shortcutsTarget 'Look to Ask.lnk')) -or
    -not (Test-Path (Join-Path $shortcutsTarget 'Uninstall.lnk'))) {
    throw 'Start menu shortcuts missing.'
}
& (Join-Path $projectRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'check_frozen.py') $installedExecutable (Join-Path $checkRoot 'checks')
if ($LASTEXITCODE -ne 0) { throw 'Installed program check failed; inspect check reports.' }
$preservedSettings = Join-Path $checkRoot 'checks/local-data/LookToAsk/settings.json'
New-Item -ItemType Directory -Force -Path (Split-Path $preservedSettings) | Out-Null
[IO.File]::WriteAllText($preservedSettings, '{"api_model":"INERT-INSTALL-TEST"}')
# Validate the resolved recursive-removal target again immediately before uninstalling.
$resolvedTarget = (Resolve-Path -LiteralPath $installTarget).Path
if ($resolvedTarget -ne $installTarget -or
    -not $resolvedTarget.StartsWith($checkRoot + [IO.Path]::DirectorySeparatorChar)) {
    throw 'Unsafe uninstallation target.'
}
$uninstallProcess = Start-Process -FilePath (Join-Path $resolvedTarget 'Uninstall.exe') -ArgumentList '/S' -WindowStyle Hidden -Wait -PassThru
if ($uninstallProcess.ExitCode -ne 0) { throw "Uninstaller exit: $($uninstallProcess.ExitCode)" }
# NSIS starts a temporary child uninstaller; wait for that child's cleanup too.
$deadline = (Get-Date).AddSeconds(120)
while ((Test-Path $installTarget) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 250 }
if ((Test-Path $installTarget) -or (Test-Path $registryTarget) -or (Test-Path $shortcutsTarget)) {
    throw 'Uninstallation did not remove application files/registry/shortcuts.'
}
if (-not (Test-Path $preservedSettings)) { throw 'Uninstall removed local test settings.' }
[IO.File]::WriteAllText((Join-Path $checkRoot 'installer-result.txt'), 'INSTALL_UNINSTALL_OK; installed frozen checks passed; settings preserved; no hardware or external AI.')
Write-Output 'INSTALL_UNINSTALL_OK (real installer, installed program, shortcuts, uninstaller; test settings preserved)'
