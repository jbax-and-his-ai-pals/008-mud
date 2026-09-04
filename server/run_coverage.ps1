Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Runs the full unittest suite (tests/singles + tests/batch + tests/current)
# under coverage.py and produces a combined terminal + HTML report.
#
# Usage:
#   cd server
#   .\run_coverage.ps1

Push-Location $PSScriptRoot
try {
    $python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        # Fall back to whatever "python" resolves to on PATH.
        $python = "python"
    }

    Get-ChildItem -Path . -Filter ".coverage.*" -Force -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Remove-Item ".coverage" -Force -ErrorAction SilentlyContinue

    $roots = @("tests/singles", "tests/batch", "tests/current")
    foreach ($root in $roots) {
        Write-Host "==> coverage run: $root" -ForegroundColor Cyan
        & $python -m coverage run -m unittest discover -s $root -p "test_*.py" -t .
        if ($LASTEXITCODE -ne 0) {
            throw "Test run failed under coverage for $root"
        }
    }

    Write-Host "`n==> combining coverage data" -ForegroundColor Cyan
    & $python -m coverage combine
    if ($LASTEXITCODE -ne 0) {
        throw "coverage combine failed"
    }

    Write-Host "`n==> coverage report (engine + toolkit)" -ForegroundColor Cyan
    & $python -m coverage report -m
    if ($LASTEXITCODE -ne 0) {
        throw "coverage report failed"
    }

    & $python -m coverage html
    Write-Host "`nHTML report: coverage_html/index.html" -ForegroundColor Green
}
finally {
    Pop-Location
}
