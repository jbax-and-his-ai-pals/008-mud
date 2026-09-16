# Windows launcher for run_tests.py.
#
# The test logic lives in run_tests.py so it behaves identically on Linux, macOS
# and Windows. This wrapper exists only to solve the Windows-specific problem:
# several Pythons installed side by side, and `python` meaning whichever one is
# first on PATH. It uses the committed Python-3.12 project virtual environment.
#
# Why that matters here: on this machine the three runtime dependencies were
# installed for Python 3.12 while the shell was running 3.14. Three test modules
# failed to import, a pygame stub stood in for the real library, and the suite
# reported 40 "failures" that were not defects.
#
#   powershell -ExecutionPolicy Bypass -File run_tests.ps1
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1  # first checkout
#   powershell -ExecutionPolicy Bypass -File run_tests.ps1 -Suite singles
#   powershell -ExecutionPolicy Bypass -File run_tests.ps1 -Target tests.singles.test_p4_progression
#   powershell -ExecutionPolicy Bypass -File run_tests.ps1 -Interpreter "py -3.14"   # see the dep gate
#
# On Linux/macOS:  python3 run_tests.py --help

[CmdletBinding()]
param(
    [ValidateSet("all", "singles", "batch", "current")]
    [string]$Suite = "all",

    # Force a specific interpreter, e.g. "py -3.14" or "python3.12".
    [string]$Interpreter = "",

    # Dotted module names or file paths passed straight to unittest.
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Target
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-PythonQuietly {
    <#
        Run a native command and return $true when it exits 0.

        Two Windows PowerShell traps this avoids: a native command's stderr
        becomes an ErrorRecord, and with $ErrorActionPreference = "Stop" that
        *terminates the script* -- so probing for an absent Python version used
        to kill the wrapper instead of moving to the next candidate. `2>$null`
        alone did not prevent it.
    #>
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
$runner = Join-Path $PSScriptRoot "run_tests.py"

$runnerArgs = @($runner)
if ($Target -and $Target.Count -gt 0) {
    foreach ($item in $Target) { $runnerArgs += @("--target", $item) }
}
else {
    $runnerArgs += @("--suite", $Suite)
}

& $python.Exe @($python.Args + $runnerArgs)
exit $LASTEXITCODE
