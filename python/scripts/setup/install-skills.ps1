# Install .skill packages from skills\ to .gemini\skills\
# Copies to a temp .zip then uses Expand-Archive to bypass extension restriction

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..\..")).Path
$SkillsDir   = Join-Path $ProjectRoot "skills"
$DestDir     = Join-Path $ProjectRoot ".gemini\skills"

if (-not (Test-Path $DestDir)) {
    New-Item -ItemType Directory -Path $DestDir | Out-Null
}

Get-ChildItem -Path $SkillsDir -Filter "*.skill" | Sort-Object Name | ForEach-Object {
    $skillName = $_.BaseName
    $skillDest = Join-Path $DestDir $skillName
    $tmpZip    = Join-Path $env:TEMP "$skillName.zip"

    if (-not (Test-Path $skillDest)) {
        New-Item -ItemType Directory -Path $skillDest | Out-Null
    }

    Copy-Item -Path $_.FullName -Destination $tmpZip -Force
    Expand-Archive -Path $tmpZip -DestinationPath $skillDest -Force 2>$null
    Remove-Item $tmpZip

    Write-Host "  Installed: $skillName"
}
