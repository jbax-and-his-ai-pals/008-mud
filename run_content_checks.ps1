Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    Write-Host "==> $Name"
    $global:LASTEXITCODE = 0
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($Name) with exit code $LASTEXITCODE"
    }
    Write-Host "OK: $Name"
}

Invoke-Step "Validate client theme packs" {
    python toolkit/pack_tool.py validate client/themes
}

Invoke-Step "Validate starter theme packs (strict)" {
    python toolkit/pack_tool.py validate toolkit/starter_packs --strict
}

Invoke-Step "Validate server data JSON integrity" {
    python toolkit/data_integrity_validator.py server/data
}

Invoke-Step "Validate server data reference integrity" {
    python toolkit/reference_integrity_validator.py server/data
}

Invoke-Step "Audit stale server data references" {
    python toolkit/stale_reference_audit.py server/data --output tmp/stale_audit_server_data.txt
}

Invoke-Step "Validate mod manifest compatibility" {
    python toolkit/mod_manifest_validator.py --roots server/mods mods
}

if (Test-Path "server/data_fixtures/LATEST_REFRESH.json") {
    Invoke-Step "Validate latest refreshed fixture JSON integrity (if present)" {
        $m = Get-Content "server/data_fixtures/LATEST_REFRESH.json" | ConvertFrom-Json
        $p = [string]$m.fixture_selected_target
        if ([string]::IsNullOrWhiteSpace($p) -or -not (Test-Path $p)) {
            throw "LATEST_REFRESH.json exists but fixture_selected_target is missing or invalid."
        }
        python toolkit/data_integrity_validator.py "$p"
    }
    Invoke-Step "Validate latest refreshed fixture reference integrity (if present)" {
        $m = Get-Content "server/data_fixtures/LATEST_REFRESH.json" | ConvertFrom-Json
        $p = [string]$m.fixture_selected_target
        python toolkit/reference_integrity_validator.py "$p"
    }
    Invoke-Step "Audit stale latest refreshed fixture references (if present)" {
        $m = Get-Content "server/data_fixtures/LATEST_REFRESH.json" | ConvertFrom-Json
        $p = [string]$m.fixture_selected_target
        python toolkit/stale_reference_audit.py "$p" --output tmp/stale_audit_fixture_selected.txt
    }
}

Write-Host "All content checks passed."
