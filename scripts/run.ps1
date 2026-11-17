param([string]$Pdf = '', [switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Run .\scripts\setup.ps1 first.' }
$launchArguments = @('-m', 'voiceleaf')
if ($SmokeTest) { $launchArguments += '--smoke-test' }
if ($Pdf) { $launchArguments += $Pdf }
& $venvPython @launchArguments
exit $LASTEXITCODE

