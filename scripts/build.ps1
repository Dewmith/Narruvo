param(
    [string]$ReleaseTag = '',
    [string]$InnoCompiler = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Create .venv with Python 3.12 x64 and install -e '.[dev,build]' first."
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'The build requires Windows.' }
& $venvPython -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) and sys.maxsize > 2**32 else 1)'
if ($LASTEXITCODE -ne 0) { throw 'The build requires Windows and Python 3.12 x64.' }
$pythonBase = & $venvPython -c 'import sys; print(sys.base_prefix)'
if ($LASTEXITCODE -ne 0) { throw 'Could not locate the Python runtime.' }

if (-not $InnoCompiler) {
    $compilerCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($compilerCommand) { $InnoCompiler = $compilerCommand.Source }
    foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if ($InnoCompiler) { break }
        if ($base) {
            $candidate = Join-Path $base 'Inno Setup 6\ISCC.exe'
            if (Test-Path -LiteralPath $candidate) { $InnoCompiler = $candidate }
        }
    }
}
if (-not $InnoCompiler -or -not (Test-Path -LiteralPath $InnoCompiler)) {
    throw 'Install Inno Setup 6, or pass -InnoCompiler C:\path\to\ISCC.exe. GitHub windows-2022 runners include it.'
}

$originalPath = $env:PATH
Push-Location -LiteralPath $projectRoot
try {
    # Native dependency discovery must not collect unrelated Qt/ICU/OpenSSL DLLs
    # from tools elsewhere on the developer's PATH.
    $env:PATH = @((Split-Path -Parent $venvPython), $pythonBase, (Join-Path $pythonBase 'DLLs'), (Join-Path $env:SystemRoot 'System32'), $env:SystemRoot) -join ';'
    $metadataArguments = @('scripts\package_metadata.py')
    if ($ReleaseTag) { $metadataArguments += @('--release-tag', $ReleaseTag) }
    $metadataJson = & $venvPython @metadataArguments
    if ($LASTEXITCODE -ne 0) { throw 'Package version validation failed.' }
    $metadata = $metadataJson | ConvertFrom-Json
    & $venvPython -m PyInstaller --noconfirm --clean --workpath build\pyinstaller --distpath dist packaging\narruvo.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed. Install the pinned build tools with pip install -e ".[dev,build]".' }

    $bundle = Join-Path $projectRoot 'dist\Narruvo'
    $unexpected = @(Get-ChildItem -LiteralPath $bundle -File -Recurse | Where-Object {
        $_.Extension -in @('.onnx', '.pdf', '.wav', '.sqlite3', '.log') -or $_.Name -like 'voices*.bin'
    })
    if ($unexpected.Count) { throw "Private/generated files must not be packaged: $($unexpected.FullName -join ', ')" }

    $outputDirectory = Join-Path $projectRoot 'dist\release'
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    & $InnoCompiler "/DAppVersion=$($metadata.version)" "/DWindowsVersion=$($metadata.windows_version)" "/DBundleDir=$bundle" "/DInstallerOutputDir=$outputDirectory" packaging\narruvo.iss
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
    $installer = Join-Path $outputDirectory $metadata.installer_name
    & (Join-Path $PSScriptRoot 'verify_installer.ps1') -InstallerPath $installer -BundleExe (Join-Path $bundle 'Narruvo.exe')
    $hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    [System.IO.File]::WriteAllText("$installer.sha256", "$hash  $($metadata.installer_name)`n", [System.Text.Encoding]::ASCII)
    Write-Host "Verified installer: $installer"
    Write-Host "SHA-256: $hash"
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
