# setup_wt_font.ps1
# Configures Windows Terminal default font for Japanese text rendering.
# Called from start-agent(Windows).bat when WT_SESSION is set (running inside Windows Terminal).
# Only modifies settings.json when no font is already configured in defaults.

$ErrorActionPreference = 'SilentlyContinue'

try {

# ── Locate Windows Terminal settings.json ─────────────────────────────
$candidates = @(
    "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json",
    "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json",
    "$env:LOCALAPPDATA\Microsoft\Windows Terminal\settings.json"
)
$wtSettings = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $wtSettings) { exit 0 }

# ── Detect best available CJK-friendly font ───────────────────────────
$fontsDir = "$env:SystemRoot\Fonts"
$fontFace = $null
if     (Test-Path "$fontsDir\BIZUDGothicR.ttf") { $fontFace = "BIZ UDGothic" }
elseif (Test-Path "$fontsDir\msgothic.ttc")      { $fontFace = "MS Gothic" }

if (-not $fontFace) {
    # Non-Japanese Windows: no CJK fonts found — notify once
    $markerDir  = "$env:LOCALAPPDATA\agent-ui"
    $markerFile = "$markerDir\wt-font-notice.flag"
    if (-not (Test-Path $markerFile)) {
        if (-not (Test-Path $markerDir)) { New-Item -ItemType Directory -Path $markerDir | Out-Null }
        [System.IO.File]::WriteAllText($markerFile, (Get-Date -Format 'yyyy-MM-dd'))
        Write-Host "[INFO] 日本語フォント (BIZ UDGothic / MS Gothic) が見つかりませんでした。"
        Write-Host "       日本語テキストが正しく表示されない場合は、Noto Sans Mono CJK JP の"
        Write-Host "       インストールをお勧めします。"
        Write-Host "[INFO] Japanese fonts (BIZ UDGothic / MS Gothic) not found."
        Write-Host "       If Japanese text appears misaligned, consider installing 'Noto Sans Mono CJK JP'."
    }
    exit 0
}

# ── Read and parse settings.json ──────────────────────────────────────
# Strip full-line // comments and trailing commas (JSONC → JSON)
$raw      = [System.IO.File]::ReadAllText($wtSettings, [System.Text.Encoding]::UTF8)
$stripped = $raw      -replace '(?m)^\s*//[^\n]*\n?', ''
$stripped = $stripped -replace ',(\s*[}\]])',          '$1'
$settings = $stripped | ConvertFrom-Json
if (-not $settings) { exit 0 }

# ── Skip if font already configured in defaults (respect user's choice)
$defaults = $settings.profiles.defaults
if ($defaults -and $defaults.PSObject.Properties['font']) {
    if ($null -ne $defaults.font -and $defaults.font.PSObject.Properties['face']) {
        exit 0  # font.face already set — do nothing
    }
    # font object exists but no face — add face
    $defaults.font | Add-Member -NotePropertyName 'face' -NotePropertyValue $fontFace -Force
} else {
    # No font configured — create defaults + font if needed
    if (-not $settings.profiles) { exit 0 }
    if (-not $defaults) {
        $settings.profiles | Add-Member -NotePropertyName 'defaults' `
            -NotePropertyValue ([PSCustomObject]@{}) -Force
        $defaults = $settings.profiles.defaults
    }
    $defaults | Add-Member -NotePropertyName 'font' `
        -NotePropertyValue ([PSCustomObject]@{ face = $fontFace }) -Force
}

# ── Write back (UTF-8 without BOM) ────────────────────────────────────
$json = $settings | ConvertTo-Json -Depth 32
[System.IO.File]::WriteAllText(
    $wtSettings,
    $json,
    (New-Object System.Text.UTF8Encoding $false)
)

Write-Host "[INFO] Windows Terminal のフォントを '$fontFace' に設定しました。"
Write-Host "       新しいウィンドウを開くと適用されます。"
Write-Host "[INFO] Windows Terminal font set to '$fontFace'. Open a new window to apply."

} catch {
    exit 0  # Silently ignore — never block app startup
}
