# Create or refresh the project's reproducible Python test environment.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1 -SkipInstall
#
# The project supports Python 3.12.  Selecting it here rather than trusting
# PATH prevents a second installed Python from producing misleading test
# failures because it has a different set of wheels.

[CmdletBinding()]
param(
    # Create/validate the virtual environment without downloading packages.
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$lockFile = Join-Path $projectRoot "server\requirements.lock"

function Get-PythonMinorVersion {
    param([string]$Exe, [string[]]$Arguments = @())

    $version = & $Exe @Arguments -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect Python interpreter '$Exe'."
    }
    return ($version | Select-Object -First 1).Trim()
}

if (Test-Path -LiteralPath $venvPython) {
    $minorVersion = Get-PythonMinorVersion -Exe $venvPython
    if ($minorVersion -ne "3.12") {
        throw ".venv uses Python $minorVersion, but this project requires 3.12. Remove only '$projectRoot\.venv' and run bootstrap.ps1 again."
    }
}
else {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "Python 3.12 was not found. Install it from python.org, then run bootstrap.ps1 again."
    }

    $minorVersion = Get-PythonMinorVersion -Exe "py" -Arguments @("-3.12")
    if ($minorVersion -ne "3.12") {
        throw "The Windows Python launcher did not resolve Python 3.12. Install Python 3.12, then run bootstrap.ps1 again."
    }

    Write-Host "Creating .venv with Python 3.12..."
    & py -3.12 -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        throw "Failed to create the project virtual environment."
    }
}

if (-not (Test-Path -LiteralPath $lockFile)) {
    throw "Missing dependency lock file: $lockFile"
}

if ($SkipInstall) {
    Write-Host "Validated .venv (Python 3.12). Dependencies were not installed."
    exit 0
}

Write-Host "Installing locked development dependencies..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Could not upgrade pip in .venv."
}
& $venvPython -m pip install -r $lockFile
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the locked development dependencies."
}

Write-Host ""
Write-Host "Ready: $venvPython"
Write-Host "Run tests with: powershell -ExecutionPolicy Bypass -File run_tests.ps1"
Write-Host "Run content checks with: powershell -ExecutionPolicy Bypass -File run_content_checks.ps1"
