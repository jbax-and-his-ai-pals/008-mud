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

# --- Content-set JSON integrity ---------------------------------------------
# This needs PyYAML (declared in server/requirements.txt). Probe for it up front
# so a missing dependency reads as a setup problem rather than a content error.
# `cmd /c` keeps the probe's stderr from tripping the script-wide
# $ErrorActionPreference = "Stop".
#
# `server/data` used to be the target here; it was removed in ce625bd when
# content moved to content_sets/, leaving these steps pointing at a directory
# that no longer exists.
cmd /c "python -c ""import yaml"" 2>nul"
$hasYaml = ($LASTEXITCODE -eq 0)

if ($hasYaml) {
    Invoke-Step "Validate content-set JSON integrity" {
        python toolkit/data_integrity_validator.py content_sets/fantasy_frontier/data
    }
}
else {
    Write-Host "SKIP: Validate content-set JSON integrity - PyYAML not installed (pip install -r server/requirements.txt)"
}

Invoke-Step "Validate mod manifest compatibility" {
    python toolkit/mod_manifest_validator.py --roots server/mods mods
}

# --- Content-set gates -------------------------------------------------------
# These gates exist because the defects they now catch all shipped silently:
#   * five Portbridge rooms -- including the only quest giver for an entire
#     campaign -- with no way in,
#   * a mage set whose members do not exist anywhere in the repository,
#   * content ids hardcoded in engine code.
# Each gate tracks acknowledged gaps in an explicit allowlist, so a NEW instance
# of the same class of mistake fails the build.
$contentSets = @("fantasy_frontier", "modern_capsule", "night_shift")

foreach ($cs in $contentSets) {
    Invoke-Step "Validate content set: $cs" {
        python toolkit/content_set_validator.py "content_sets/$cs"
    }
}

foreach ($cs in $contentSets) {
    Invoke-Step "Validate content-set reference integrity: $cs" {
        python toolkit/reference_integrity_validator.py "content_sets/$cs/data"
    }
    Invoke-Step "Audit stale content-set references: $cs" {
        python toolkit/stale_reference_audit.py "content_sets/$cs/data" --output "tmp/stale_audit_$cs.txt"
    }
}

Invoke-Step "Validate engine content-neutrality" {
    python toolkit/content_neutrality_validator.py content_sets/fantasy_frontier
}

# --- Legacy editor-fixture steps --------------------------------------------
# These validate a fixture produced by toolkit/fixture_refresh.py. The recorded
# fixture path is absolute and may point at a different checkout (the committed
# LATEST_REFRESH.json points at C:\python\old\restart), so its absence here is
# not a content failure -- report it and move on. If the target does exist, the
# checks run and gate as before.
if (Test-Path "server/data_fixtures/LATEST_REFRESH.json") {
    $refresh = Get-Content "server/data_fixtures/LATEST_REFRESH.json" | ConvertFrom-Json
    $fixtureTarget = [string]$refresh.fixture_selected_target

    if ([string]::IsNullOrWhiteSpace($fixtureTarget)) {
        Write-Host "SKIP: refreshed fixture checks - LATEST_REFRESH.json has no fixture_selected_target"
    }
    elseif (-not (Test-Path $fixtureTarget)) {
        Write-Host "SKIP: refreshed fixture checks - recorded fixture target is not on this machine:"
        Write-Host "      $fixtureTarget"
        Write-Host "      (regenerate with toolkit/fixture_refresh.py to validate a local fixture)"
    }
    else {
        Invoke-Step "Validate latest refreshed fixture JSON integrity" {
            python toolkit/data_integrity_validator.py "$fixtureTarget"
        }
        Invoke-Step "Validate latest refreshed fixture reference integrity" {
            python toolkit/reference_integrity_validator.py "$fixtureTarget"
        }
        Invoke-Step "Audit stale latest refreshed fixture references" {
            python toolkit/stale_reference_audit.py "$fixtureTarget" --output tmp/stale_audit_fixture_selected.txt
        }
    }
}

Write-Host "All content checks passed."
