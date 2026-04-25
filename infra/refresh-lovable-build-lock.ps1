<#
.SYNOPSIS
  Regenerates the repo-owned external package lock for the Lovable build.

.DESCRIPTION
  This script copies lovable/package.json into a temporary workspace,
  generates package-lock.json inside a node:22-slim container, and writes the
  canonical lock plus metadata into infra/ without modifying lovable/.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RepoRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-DockerReady {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "docker is required to refresh the Lovable build lock."
    }

    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "docker is installed but the daemon is not reachable."
    }
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$RepoRoot = (Resolve-Path $RepoRoot).Path

$generatorImage = "node:22-slim"
$generatorCommand = "npm install --package-lock-only --ignore-scripts --no-audit --no-fund"
$lovableRoot = Join-Path $RepoRoot "lovable"
$lovablePackageJsonPath = Join-Path $lovableRoot "package.json"
$outputLockPath = Join-Path $RepoRoot "infra\lovable-build.package-lock.json"
$outputMetadataPath = Join-Path $RepoRoot "infra\lovable-build.lock-metadata.json"
$lovableGitStatusBefore = $null

if (-not (Test-Path -LiteralPath $lovablePackageJsonPath -PathType Leaf)) {
    throw ("Lovable package.json was not found: {0}" -f $lovablePackageJsonPath)
}

Assert-DockerReady

if (Test-Path -LiteralPath (Join-Path $lovableRoot ".git")) {
    $lovableGitStatusBefore = (git -C $lovableRoot status --porcelain=v1 | Out-String)
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("tapne-lovable-lock-" + [Guid]::NewGuid().ToString("N"))
$workspacePath = Join-Path $tempRoot "workspace"
$workspacePackageJsonPath = Join-Path $workspacePath "package.json"
$workspacePackageLockPath = Join-Path $workspacePath "package-lock.json"
$workspaceNpmVersionPath = Join-Path $workspacePath ".npm-version"

try {
    New-Item -ItemType Directory -Path $workspacePath -Force | Out-Null
    Copy-Item -LiteralPath $lovablePackageJsonPath -Destination $workspacePackageJsonPath -Force

    $workspaceMount = "{0}:/workspace" -f $workspacePath
    $dockerCommand = "{0} && npm --version > /workspace/.npm-version" -f $generatorCommand
    & docker run --rm -v $workspaceMount -w /workspace $generatorImage sh -lc $dockerCommand
    if ($LASTEXITCODE -ne 0) {
        throw "docker failed while generating the external Lovable build lock."
    }

    if (-not (Test-Path -LiteralPath $workspacePackageLockPath -PathType Leaf)) {
        throw "The generator workspace did not produce package-lock.json."
    }
    if (-not (Test-Path -LiteralPath $workspaceNpmVersionPath -PathType Leaf)) {
        throw "The generator workspace did not record npm version information."
    }

    Copy-Item -LiteralPath $workspacePackageLockPath -Destination $outputLockPath -Force

    $metadata = [ordered]@{
        lock_format_version = 1
        package_json_path = "lovable/package.json"
        lockfile_path = "infra/lovable-build.package-lock.json"
        package_json_sha256 = (Get-FileHash -LiteralPath $lovablePackageJsonPath -Algorithm SHA256).Hash.ToLowerInvariant()
        generator_image = $generatorImage
        generator_command = $generatorCommand
        npm_version = (Get-Content -LiteralPath $workspaceNpmVersionPath -Raw).Trim()
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
    $metadata | ConvertTo-Json | Set-Content -LiteralPath $outputMetadataPath -Encoding utf8NoBOM
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}

if ($null -ne $lovableGitStatusBefore) {
    $lovableGitStatusAfter = (git -C $lovableRoot status --porcelain=v1 | Out-String)
    if ($lovableGitStatusBefore -ne $lovableGitStatusAfter) {
        throw "Refreshing the external Lovable build lock mutated the Lovable worktree."
    }
}

Write-Host ("Refreshed {0} and {1} from {2} without writing inside lovable/" -f $outputLockPath, $outputMetadataPath, $lovablePackageJsonPath) -ForegroundColor Green
