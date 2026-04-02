<#
.SYNOPSIS
  Builds the Lovable SPA into an external production artifact directory.

.DESCRIPTION
  This script never writes into lovable/dist. It installs dependencies from
  lovable/package.json when needed without rewriting the lovable lockfile, and emits the production bundle into
  artifacts/lovable-production-dist so Django can serve or wrap it without
  modifying the lovable source tree.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RepoRoot = "",
    [string]$OutputDir = "",
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$lovableRoot = Join-Path $RepoRoot "lovable"
$frontendSpaRoot = Join-Path $RepoRoot "frontend_spa"
$resolvedOutputDir = $OutputDir
if ([string]::IsNullOrWhiteSpace($resolvedOutputDir)) {
    $resolvedOutputDir = Join-Path $RepoRoot "artifacts\\lovable-production-dist"
}

if (-not (Test-Path -LiteralPath $lovableRoot -PathType Container)) {
    throw "Lovable source directory was not found."
}
if (-not (Test-Path -LiteralPath $frontendSpaRoot -PathType Container)) {
    throw "External frontend_spa source directory was not found."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required to build the Lovable frontend."
}

Push-Location $lovableRoot
try {
    if (-not $SkipInstall) {
        npm install --package-lock=false
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed."
        }
    }

    if (Test-Path -LiteralPath $resolvedOutputDir) {
        Remove-Item -LiteralPath $resolvedOutputDir -Recurse -Force
    }

    npx vite build "--config=..\\frontend_spa\\vite.production.config.ts" "--outDir=$resolvedOutputDir"
    if ($LASTEXITCODE -ne 0) {
        throw "Lovable build failed."
    }
}
finally {
    Pop-Location
}

$indexPath = Join-Path $resolvedOutputDir "index.html"
if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) {
    throw "Lovable production bundle was created without index.html."
}

Write-Host ("Built Lovable frontend into {0}" -f $resolvedOutputDir) -ForegroundColor Green
