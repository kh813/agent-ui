# Build all .skill packages from python/skills/ (bundled) and
# python/skills-personal/ (per-installation, gitignored, created by
# `my-skills create` / skill-catalog import).
# Creates a temp .zip then renames to .skill to bypass Compress-Archive extension restriction
# A `disabled/` subfolder under either root is excluded from the build.

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..\..\..")).Path
$SkillsOut   = Join-Path $ProjectRoot "skills"
$SkillRoots  = @(
    (Join-Path $ProjectRoot "python\skills"),
    (Join-Path $ProjectRoot "python\skills-personal")
)

if (-not (Test-Path $SkillsOut)) {
    New-Item -ItemType Directory -Path $SkillsOut | Out-Null
}
Get-ChildItem -Path $SkillsOut -Filter "*.skill" | Remove-Item -Force

$count = 0
$seen = @{}
foreach ($root in $SkillRoots) {
    if (-not (Test-Path $root)) { continue }

    Get-ChildItem -Path $root -Recurse -Filter "SKILL.md" |
        Where-Object { $_.FullName -notmatch '[\\/]disabled[\\/]' } |
        Sort-Object FullName |
        ForEach-Object {
            $skillName = $_.Directory.Name

            if ($seen.ContainsKey($skillName)) {
                Write-Warning "Duplicate skill name '$skillName': $($seen[$skillName]) vs $($_.Directory.FullName) — keeping the first one."
                return
            }
            $seen[$skillName] = $_.Directory.FullName

            $output = Join-Path $SkillsOut "$skillName.skill"
            $tmpZip = Join-Path $SkillsOut "$skillName.zip"

            Push-Location $_.Directory.FullName
            try {
                Compress-Archive -Path "SKILL.md" -DestinationPath $tmpZip -Force 2>$null
            } finally {
                Pop-Location
            }

            if (Test-Path $output) { Remove-Item $output }
            Move-Item -Path $tmpZip -Destination $output | Out-Null

            Write-Host "  Built: skills\$skillName.skill"
            $count++
        }
}

Write-Host ""
Write-Host "Done: $count skill(s) -> skills\"
