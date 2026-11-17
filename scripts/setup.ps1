param([string]$Python = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$candidates = [System.Collections.Generic.List[string]]::new()
if ($Python) {
    $candidates.Add($Python)
} else {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $launcherResult = & py -3.12 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $launcherResult) { $candidates.Add([string]$launcherResult) }
    }
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) { $candidates.Add($pythonCommand.Source) }
    $managedRoot = Join-Path $env:APPDATA 'uv\python'
    if (Test-Path -LiteralPath $managedRoot) {
        Get-ChildItem -LiteralPath $managedRoot -Directory -Filter 'cpython-3.12.*-windows-x86_64-none' |
            Sort-Object Name -Descending | ForEach-Object { $candidates.Add((Join-Path $_.FullName 'python.exe')) }
    }
    $candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'))
}
$selectedPython = $null
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
        & $candidate -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) and sys.maxsize > 2**32 else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { $selectedPython = $candidate; break }
    }
}
if (-not $selectedPython) { throw 'Python 3.12 x64 is required. Install it, or pass -Python C:\path\to\python.exe.' }
Write-Host "Using $selectedPython"
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $selectedPython -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $venvPython -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'The existing .venv uses a different Python. Rename it and run setup again.' }
Push-Location -LiteralPath $projectRoot
try {
    & $venvPython -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your network and the pip error above.' }
} finally { Pop-Location }
Write-Host 'Setup complete. Run .\scripts\run.ps1. The app offers an explicit model download on first launch.'

