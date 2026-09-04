$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    Remove-Item Env:MUD_UPDATE_SNAPSHOTS -ErrorAction SilentlyContinue

    Write-Host "=== Deterministic contract snapshots ===" -ForegroundColor Cyan
    python -m unittest `
        tests.singles.test_headless_server `
        tests.singles.test_headless_server_policy_snapshots `
        tests.singles.test_transport_parity_snapshots `
        -v
    if ($LASTEXITCODE -ne 0) {
        throw "Snapshot checks failed with exit code $LASTEXITCODE"
    }

    Write-Host "`n=== Policy regression tests ===" -ForegroundColor Cyan
    python -m unittest `
        tests.singles.test_readonly_policy `
        tests.singles.test_no_combat_policy `
        tests.singles.test_system_providers `
        tests.singles.test_feature_profile `
        tests.singles.test_plugin_provider_integration `
        tests.singles.test_mod_manifest_validator `
        tests.singles.test_ws_session_resume `
        tests.singles.test_audit_operator_command `
        tests.singles.test_fixture_boot_smoke `
        -v
    if ($LASTEXITCODE -ne 0) {
        throw "Policy regression checks failed with exit code $LASTEXITCODE"
    }

    Write-Host "`n=== Toolkit data integrity validation ===" -ForegroundColor Cyan
    python -m unittest `
        tests.singles.test_data_integrity_validator `
        -v
    if ($LASTEXITCODE -ne 0) {
        throw "Toolkit data integrity checks failed with exit code $LASTEXITCODE"
    }

    Write-Host "`nAll checks passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
