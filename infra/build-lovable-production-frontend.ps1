<#
.SYNOPSIS
  Builds the Lovable SPA into an external production artifact directory.

.DESCRIPTION
  This script treats the checked-out lovable/ tree as read-only. It copies
  lovable/ and frontend_spa/ into an isolated temporary workspace, installs
  dependencies there when needed, and emits the production bundle into
  artifacts/lovable-production-dist so Django can serve or wrap it without
  modifying the original lovable source tree.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RepoRoot = "",
    [string]$OutputDir = "",
    [string]$LovableRoot = "",
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$RepoRoot = (Resolve-Path $RepoRoot).Path

$frontendSpaRoot = Join-Path $RepoRoot "frontend_spa"
$resolvedLovableRoot = $LovableRoot
if ([string]::IsNullOrWhiteSpace($resolvedLovableRoot)) {
    $resolvedLovableRoot = Join-Path $RepoRoot "lovable"
} elseif (-not [System.IO.Path]::IsPathRooted($resolvedLovableRoot)) {
    $resolvedLovableRoot = Join-Path $RepoRoot $resolvedLovableRoot
}
$lovableRoot = (Resolve-Path $resolvedLovableRoot).Path
$resolvedOutputDir = $OutputDir
if ([string]::IsNullOrWhiteSpace($resolvedOutputDir)) {
    $resolvedOutputDir = Join-Path $RepoRoot "artifacts\\lovable-production-dist"
} elseif (-not [System.IO.Path]::IsPathRooted($resolvedOutputDir)) {
    $resolvedOutputDir = Join-Path $RepoRoot $resolvedOutputDir
}
$resolvedOutputDir = [System.IO.Path]::GetFullPath($resolvedOutputDir)

if (-not (Test-Path -LiteralPath $lovableRoot -PathType Container)) {
    throw "Lovable source directory was not found."
}
if (-not (Test-Path -LiteralPath $frontendSpaRoot -PathType Container)) {
    throw "External frontend_spa source directory was not found."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required to build the Lovable frontend."
}

function Copy-TreeReadOnly {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [string[]]$ExcludeDirectories = @()
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    $arguments = @(
        $Source,
        $Destination,
        "/E",
        "/R:2",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP"
    )
    if ($ExcludeDirectories.Count -gt 0) {
        $arguments += "/XD"
        $arguments += $ExcludeDirectories
    }

    & robocopy @arguments | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed while staging '$Source' into '$Destination'."
    }
}

$isolatedRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("tapne-lovable-build-" + [Guid]::NewGuid().ToString("N"))
$isolatedLovableRoot = Join-Path $isolatedRoot "lovable"
$isolatedFrontendSpaRoot = Join-Path $isolatedRoot "frontend_spa"
$isolatedConfigPath = Join-Path $isolatedFrontendSpaRoot "vite.production.config.ts"
$isolatedNodeModules = Join-Path $isolatedLovableRoot "node_modules"
$viteExecutable = Join-Path $isolatedNodeModules ".bin\vite.cmd"
$isolatedPackageLock = Join-Path $isolatedLovableRoot "package-lock.json"
$sourceNodeModules = Join-Path $lovableRoot "node_modules"
$lovableGitStatusBefore = $null

if (Test-Path -LiteralPath (Join-Path $lovableRoot ".git")) {
    $lovableGitStatusBefore = (git -C $lovableRoot status --porcelain=v1 | Out-String)
}

try {
    Copy-TreeReadOnly -Source $lovableRoot -Destination $isolatedLovableRoot -ExcludeDirectories @(".git", "node_modules", "dist", "dist-ssr")
    Copy-TreeReadOnly -Source $frontendSpaRoot -Destination $isolatedFrontendSpaRoot -ExcludeDirectories @(".git", "node_modules", "dist", "dist-ssr")

    if ($SkipInstall) {
        if (-not (Test-Path -LiteralPath $sourceNodeModules -PathType Container)) {
            throw "SkipInstall requires lovable/node_modules to already exist."
        }
        New-Item -ItemType Junction -Path $isolatedNodeModules -Target $sourceNodeModules | Out-Null
    } else {
        Push-Location $isolatedLovableRoot
        try {
            if (Test-Path -LiteralPath $isolatedPackageLock -PathType Leaf) {
                npm ci
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "npm ci failed in the isolated Lovable workspace; falling back to npm install --package-lock=false."
                    if (Test-Path -LiteralPath $isolatedNodeModules) {
                        Remove-Item -LiteralPath $isolatedNodeModules -Recurse -Force
                    }
                    npm install --package-lock=false
                    if ($LASTEXITCODE -ne 0) {
                        throw "npm install fallback failed in the isolated Lovable workspace."
                    }
                }
            } else {
                npm install --package-lock=false
                if ($LASTEXITCODE -ne 0) {
                    throw "npm install failed in the isolated Lovable workspace."
                }
            }
        }
        finally {
            Pop-Location
        }
    }

    if (Test-Path -LiteralPath $resolvedOutputDir) {
        Remove-Item -LiteralPath $resolvedOutputDir -Recurse -Force
    }

    if (-not (Test-Path -LiteralPath $viteExecutable -PathType Leaf)) {
        throw "Vite executable was not found in the isolated Lovable workspace."
    }

    & $viteExecutable "build" "--config=$isolatedConfigPath" "--outDir=$resolvedOutputDir"
    if ($LASTEXITCODE -ne 0) {
        throw "Lovable build failed from the isolated workspace."
    }
}
finally {
    if (Test-Path -LiteralPath $isolatedRoot) {
        Remove-Item -LiteralPath $isolatedRoot -Recurse -Force
    }
}

$indexPath = Join-Path $resolvedOutputDir "index.html"
if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) {
    throw "Lovable production bundle was created without index.html."
}

if ($null -ne $lovableGitStatusBefore) {
    $lovableGitStatusAfter = (git -C $lovableRoot status --porcelain=v1 | Out-String)
    if ($lovableGitStatusBefore -ne $lovableGitStatusAfter) {
        throw "Build mutated the Lovable worktree. git status before and after the build did not match."
    }
}

Write-Host ("Built Lovable frontend from {0} into {1} without writing inside the checked-out lovable/" -f $lovableRoot, $resolvedOutputDir) -ForegroundColor Green
