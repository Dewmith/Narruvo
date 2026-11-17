param(
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [string]$BundleExe = '',
    [int]$TimeoutSeconds = 120
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$installer = (Resolve-Path -LiteralPath $InstallerPath).Path
if ($BundleExe) { $BundleExe = (Resolve-Path -LiteralPath $BundleExe).Path }
$verificationRoot = Join-Path $projectRoot ('.artifacts\package-verification\' + [guid]::NewGuid().ToString('N'))
$installDirectory = Join-Path $verificationRoot 'installed app'
$dataDirectory = Join-Path $verificationRoot 'user data'
New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
$sentinel = Join-Path $dataDirectory 'preserve-user-data.txt'
[System.IO.File]::WriteAllText($sentinel, 'VoiceLeaf uninstall must preserve user data.')
$savedEnvironment = @{}
foreach ($name in @('VOICELEAF_DATA_DIR', 'QT_QPA_PLATFORM', 'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'PATH', 'TEMP', 'TMP')) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

function Invoke-VerifiedProcess {
    param([string]$Executable, [string[]]$ProcessArguments)
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $Executable
    $start.Arguments = $ProcessArguments -join ' '
    $start.WorkingDirectory = $verificationRoot
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $process = [System.Diagnostics.Process]::Start($start)
    try {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            & (Join-Path $env:SystemRoot 'System32\taskkill.exe') /PID $process.Id /T /F | Out-Null
            throw "Process timed out: $Executable $($ProcessArguments -join ' ')"
        }
        if ($process.ExitCode -ne 0) {
            throw "Process exited with code $($process.ExitCode): $Executable $($ProcessArguments -join ' ')"
        }
    } finally {
        $process.Dispose()
    }
}

function Test-Executable {
    param([string]$Executable)
    Invoke-VerifiedProcess $Executable @('--verify-package')
    Invoke-VerifiedProcess $Executable @('--smoke-test')
}

$uninstaller = Join-Path $installDirectory 'unins000.exe'
$uninstalled = $false
try {
    $env:VOICELEAF_DATA_DIR = $dataDirectory
    $env:QT_QPA_PLATFORM = 'offscreen'
    foreach ($name in @('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    # No Python, eSpeak, or development-tool directories may rescue missing DLLs.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $temporaryDirectory = Join-Path $verificationRoot 'temp'
    New-Item -ItemType Directory -Path $temporaryDirectory -Force | Out-Null
    $env:TEMP = $temporaryDirectory
    $env:TMP = $temporaryDirectory
    if ($BundleExe) { Test-Executable $BundleExe }
    Invoke-VerifiedProcess $installer @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/NOICONS', '/CURRENTUSER', '/VERIFYINSTALL=1', "/DIR=`"$installDirectory`"", "/LOG=`"$(Join-Path $verificationRoot 'install.log')`"")
    $installedExe = Join-Path $installDirectory 'VoiceLeaf.exe'
    if (-not (Test-Path -LiteralPath $installedExe)) { throw 'Installer did not create VoiceLeaf.exe.' }
    Test-Executable $installedExe
    $preserved = @(Get-ChildItem -LiteralPath $dataDirectory -File -Recurse | Get-FileHash -Algorithm SHA256)
    Invoke-VerifiedProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$(Join-Path $verificationRoot 'uninstall.log')`"")
    $uninstalled = $true
    if (Test-Path -LiteralPath $installedExe) { throw 'Uninstall did not remove the application executable.' }
    foreach ($file in $preserved) {
        if (-not (Test-Path -LiteralPath $file.Path) -or (Get-FileHash -LiteralPath $file.Path -Algorithm SHA256).Hash -ne $file.Hash) {
            throw "Uninstall changed user data: $($file.Path)"
        }
    }
    Write-Host "Installer, frozen workers, launch, and uninstall verified. Logs: $verificationRoot"
} catch {
    Get-ChildItem -LiteralPath $verificationRoot -Filter '*.log' -File -Recurse | ForEach-Object {
        Write-Host "Diagnostic log: $($_.FullName)"
        Get-Content -LiteralPath $_.FullName -Tail 60 | Write-Host
    }
    throw
} finally {
    if (-not $uninstalled -and (Test-Path -LiteralPath $uninstaller)) {
        # /VERIFYINSTALL disables normal registration and shortcuts, so cleanup
        # cannot unregister a user's separately installed copy of VoiceLeaf.
        try { Invoke-VerifiedProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') }
        catch { Write-Warning "Verification install cleanup failed: $_" }
    }
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
    }
}
