param(
    [string]$OutputDir = ".\dist"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ManifestPath = Join-Path $RepoRoot "blender_manifest.toml"

if (-not (Test-Path $ManifestPath)) {
    throw "blender_manifest.toml was not found in $RepoRoot"
}

$Manifest = Get-Content $ManifestPath -Raw

$IdMatch = [regex]::Match($Manifest, '(?m)^id\s*=\s*"([^"]+)"')
$VersionMatch = [regex]::Match($Manifest, '(?m)^version\s*=\s*"([^"]+)"')

if (-not $IdMatch.Success -or -not $VersionMatch.Success) {
    throw "Could not read extension id/version from blender_manifest.toml"
}

$ExtensionId = $IdMatch.Groups[1].Value
$Version = $VersionMatch.Groups[1].Value
$ResolvedOutputDir = Join-Path $RepoRoot $OutputDir

New-Item -ItemType Directory -Force -Path $ResolvedOutputDir | Out-Null

$Blender = Get-Command blender -ErrorAction SilentlyContinue
if ($null -ne $Blender) {
    Write-Host "Using Blender CLI build command..."
    & $Blender.Source --command extension build --source-dir $RepoRoot --output-dir $ResolvedOutputDir
    exit $LASTEXITCODE
}

$ArchiveName = "$ExtensionId-$Version.zip"
$ArchivePath = Join-Path $ResolvedOutputDir $ArchiveName
$StagingDir = Join-Path $env:TEMP "$ExtensionId-$Version-build"

if (Test-Path $StagingDir) {
    Remove-Item -Recurse -Force -LiteralPath $StagingDir
}

New-Item -ItemType Directory -Force -Path $StagingDir | Out-Null

$IncludePaths = @(
    "__init__.py",
    "blender_manifest.toml",
    "constants.py",
    "preferences.py",
    "properties.py",
    "operators",
    "ui",
    "utils"
)

foreach ($RelativePath in $IncludePaths) {
    $Source = Join-Path $RepoRoot $RelativePath
    $Target = Join-Path $StagingDir $RelativePath
    if (Test-Path $Source -PathType Container) {
        Copy-Item -Recurse -Force -Path $Source -Destination $Target
    }
    else {
        Copy-Item -Force -Path $Source -Destination $Target
    }
}

Get-ChildItem -Path $StagingDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path $StagingDir -Recurse -File -Include "*.pyc" | Remove-Item -Force

if (Test-Path $ArchivePath) {
    Remove-Item -Force -LiteralPath $ArchivePath
}

Compress-Archive -Path (Join-Path $StagingDir "*") -DestinationPath $ArchivePath -CompressionLevel Optimal
Remove-Item -Recurse -Force -LiteralPath $StagingDir

Write-Host "Created fallback extension package: $ArchivePath"
