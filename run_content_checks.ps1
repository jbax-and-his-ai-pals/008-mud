# Windows launcher for run_content_checks.py.
#
# The gates live in run_content_checks.py so they behave identically on Linux,
# macOS and Windows. This wrapper exists only to solve the Windows-specific
# problem: several Pythons installed side by side, and `python` meaning whichever
# one is first on PATH. It uses the committed Python-3.12 project virtual
# environment, then hands over.
#
# These steps used to call bare `python`, which meant that on a machine with both
# 3.12 and 3.14 the gates ran under 3.14 -- which has no pygame wheel -- and
# every one of them died inside an import with `No module named 'pygame'`. That
# reads like broken content and is actually a broken interpreter choice.
#
#   powershell -ExecutionPolicy Bypass -File run_content_checks.ps1
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1  # first checkout
#
# On Linux/macOS:  python3 run_content_checks.py

[CmdletBinding()]
param(
    # Force a specific interpreter, e.g. "py -3.14".
    [string]$Interpreter = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-PythonQuietly {
    param([string]$Exe, [string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Exe @Arguments 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

function Resolve-ProjectPython {
    if ($Interpreter) {
        $parts = $Interpreter.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)
        $exe = $parts[0]
        $exeArgs = @($parts[1..($parts.Count - 1)])
        if (-not (Test-PythonQuietly -Exe $exe -Arguments ($exeArgs + @("-c", "import sys")))) {
            throw "Interpreter '$Interpreter' does not run."
        }
        return [pscustomobject]@{ Exe = $exe; Args = $exeArgs }
    }
    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        if (-not (Test-PythonQuietly -Exe $venvPython -Arguments @("-c", "import sys; assert sys.version_info[:2] == (3, 12)"))) {
            throw "The project .venv is not a usable Python 3.12 environment. Remove only '.venv' and run bootstrap.ps1 again."
        }
        return [pscustomobject]@{ Exe = $venvPython; Args = @() }
    }
    throw "No project .venv found. Run 'powershell -ExecutionPolicy Bypass -File bootstrap.ps1' first, or pass -Interpreter explicitly for diagnostics."
}

$python = Resolve-ProjectPython
& $python.Exe @($python.Args + @((Join-Path $PSScriptRoot "run_content_checks.py")))
exit $LASTEXITCODE
