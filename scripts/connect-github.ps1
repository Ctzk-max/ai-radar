# Run interactively in this checkout. The token is stored with Windows DPAPI.
$ErrorActionPreference = 'Stop'
$radarRoot = Split-Path -Parent $PSScriptRoot
$radarLocal = Join-Path $radarRoot '.local'
New-Item -ItemType Directory -Path $radarLocal -Force | Out-Null
$radarToken = Read-Host 'GitHub fine-grained token for Ctzk-max/ai-radar (hidden)' -AsSecureString
if ($radarToken.Length -lt 20) { throw 'The token was too short.' }
$radarToken | ConvertFrom-SecureString | Set-Content -LiteralPath (Join-Path $radarLocal 'github-token.dpapi') -Encoding ascii
Write-Host 'Saved the encrypted credential in this checkout.'
