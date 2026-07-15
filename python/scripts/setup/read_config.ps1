param([string]$Section, [string]$Key)
$configPath = Join-Path $PSScriptRoot '..\..\..\config.toml'
if (-not (Test-Path $configPath)) {
    Write-Error "config.toml not found at $configPath. Copy config.toml.template to config.toml."
    exit 1
}
$inSection = $false
foreach ($line in [IO.File]::ReadAllLines($configPath)) {
    $line = $line.Trim()
    if ($line -eq "[$Section]") { $inSection = $true }
    elseif ($line -match '^\[') { $inSection = $false }
    elseif ($inSection -and $line -match "^$Key\s*=\s*`"(.+)`"") {
        Write-Output $Matches[1]
        exit 0
    }
}
Write-Error "Key '$Key' not found in section '[$Section]' of config.toml"
exit 1
