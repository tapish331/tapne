<#
.SYNOPSIS
  PowerShell entrypoint for the Cloud Run web image readiness checker.

.DESCRIPTION
  This wrapper intentionally delegates to `infra/check-cloud-run-web-image.sh`
  so behavior stays exactly in sync with the canonical checker implementation.
  All arguments are forwarded verbatim, and the Bash script exit code is
  preserved.

.EXAMPLE
  .\infra\check-cloud-run-web-image.ps1 --verbose

.EXAMPLE
  .\infra\check-cloud-run-web-image.ps1 --image tapne-web:cloudrun-check --artifact-image asia-south1-docker.pkg.dev/...
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CheckerArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$DefaultImageRef = "tapne-web:cloudrun-check"
$DefaultArtifactImageRef = "asia-south1-docker.pkg.dev/tapne-487110/tapne/tapne-web:cloudrun-check"
$DefaultCloudRunService = "tapne-web"
$DefaultCloudRunRegion = "asia-south1"

function Convert-ToBashSingleQuoted {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + $Value.Replace("'", "'""'""'") + "'"
}

function Convert-WindowsPathToWslPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ($Path -match '^([A-Za-z]):[\\/](.*)$') {
        $drive = $Matches[1].ToLowerInvariant()
        $tail = ($Matches[2] -replace '\\', '/')
        return "/mnt/$drive/$tail"
    }

    return ($Path -replace '\\', '/')
}

function Resolve-BashLauncher {
    $candidates = @(
        "$env:ProgramFiles\Git\bin\bash.exe",
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
    )

    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate)) {
            return [PSCustomObject]@{
                Type = "git-bash"
                Exe  = $candidate
            }
        }
    }

    $bashCmd = Get-Command bash -ErrorAction SilentlyContinue
    if ($null -ne $bashCmd -and -not [string]::IsNullOrWhiteSpace($bashCmd.Source)) {
        $source = $bashCmd.Source
        if ($source -match 'Git\\bin\\bash\.exe|msys|mingw') {
            return [PSCustomObject]@{
                Type = "git-bash"
                Exe  = $source
            }
        }

        if ($source -match 'Windows\\System32\\bash\.exe') {
            $wslCmd = Get-Command wsl.exe -ErrorAction SilentlyContinue
            if ($null -ne $wslCmd) {
                return [PSCustomObject]@{
                    Type = "wsl"
                    Exe  = $wslCmd.Source
                }
            }
        }

        return [PSCustomObject]@{
            Type = "bash"
            Exe  = $source
        }
    }

    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($null -ne $wsl -and -not [string]::IsNullOrWhiteSpace($wsl.Source)) {
        return [PSCustomObject]@{
            Type = "wsl"
            Exe  = $wsl.Source
        }
    }

    return $null
}

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$bashScriptPath = Join-Path $scriptDir "check-cloud-run-web-image.sh"

if (-not (Test-Path -LiteralPath $bashScriptPath)) {
    throw "Missing required script: $bashScriptPath"
}

$normalizedArgs = [System.Collections.Generic.List[string]]::new()
$wrapperVerbose = $false
foreach ($arg in $CheckerArgs) {
    if ($arg -eq "--verbose") {
        $wrapperVerbose = $true
        continue
    }
    [void]$normalizedArgs.Add($arg)
}

if ($wrapperVerbose) {
    $VerbosePreference = "Continue"
}

$effectiveArgs = [System.Collections.Generic.List[string]]::new()
foreach ($arg in $normalizedArgs) {
    [void]$effectiveArgs.Add($arg)
}

$isHelp = $effectiveArgs.Contains("--help") -or $effectiveArgs.Contains("-h")
if (-not $isHelp) {
    if (-not $effectiveArgs.Contains("--image")) {
        [void]$effectiveArgs.Add("--image")
        [void]$effectiveArgs.Add($DefaultImageRef)
    }
    if (-not $effectiveArgs.Contains("--artifact-image")) {
        [void]$effectiveArgs.Add("--artifact-image")
        [void]$effectiveArgs.Add($DefaultArtifactImageRef)
    }
    if (-not $effectiveArgs.Contains("--service")) {
        [void]$effectiveArgs.Add("--service")
        [void]$effectiveArgs.Add($DefaultCloudRunService)
    }
    if (-not $effectiveArgs.Contains("--region")) {
        [void]$effectiveArgs.Add("--region")
        [void]$effectiveArgs.Add($DefaultCloudRunRegion)
    }
}

$CheckerArgs = @($effectiveArgs)

$launcher = Resolve-BashLauncher
if ($null -eq $launcher) {
    throw "No Bash runtime found. Install Git Bash or enable WSL, then retry."
}

$repoRootForShell = $repoRoot
if ($launcher.Type -eq "wsl") {
    $repoRootForShell = Convert-WindowsPathToWslPath -Path $repoRoot
}
else {
    $repoRootForShell = ($repoRoot -replace '\\', '/')
}

$command = "cd $(Convert-ToBashSingleQuoted -Value $repoRootForShell) && bash 'infra/check-cloud-run-web-image.sh'"
if ($CheckerArgs.Count -gt 0) {
    $escapedArgs = $CheckerArgs | ForEach-Object { Convert-ToBashSingleQuoted -Value $_ }
    $command = "$command $($escapedArgs -join ' ')"
}

Write-Verbose ("Using launcher: {0} ({1})" -f $launcher.Exe, $launcher.Type)
Write-Verbose ("Running command: {0}" -f $command)

if ($launcher.Type -eq "wsl") {
    & $launcher.Exe "bash" "-lc" $command
}
else {
    & $launcher.Exe "-lc" $command
}

exit $LASTEXITCODE
