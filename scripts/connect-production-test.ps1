# Run interactively to authorize a one-time smoke test on the production domain.
$ErrorActionPreference = 'Stop'
$radarRoot = Split-Path -Parent $PSScriptRoot
$radarLocal = Join-Path $radarRoot '.local'
New-Item -ItemType Directory -Path $radarLocal -Force | Out-Null
$radarPassword = Read-Host 'Existing AI Radar administrator password (hidden)' -AsSecureString
if ($radarPassword.Length -eq 0) { throw 'No password entered.' }
$radarPassword | ConvertFrom-SecureString | Set-Content -LiteralPath (Join-Path $radarLocal 'production-smoke.dpapi') -Encoding ascii
Write-Host 'Saved the one-time test credential using Windows DPAPI.'
