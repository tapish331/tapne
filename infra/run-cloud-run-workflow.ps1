<#
.SYNOPSIS
  Executes the full Tapne Cloud Run workflow in a fixed order.

.DESCRIPTION
  Runs these scripts sequentially and stops on first failure:
    1) infra/setup-faithful-local.ps1
    2) infra/check-cloud-run-web-image.ps1
    3) infra/push-web-image-to-artifact.ps1
    4) infra/setup-custom-domain.ps1
    5) infra/deploy-cloud-run.ps1

  This orchestrator keeps one shared image tag across check/push/deploy and
  sets deploy to -BuildAndPushImage:$false so step 3 is the single push step.

.EXAMPLE
  pwsh -File infra/run-cloud-run-workflow.ps1 -Verbose

.EXAMPLE
  pwsh -File infra/run-cloud-run-workflow.ps1 `
    -ProjectId tapne-487110 `
    -Region asia-south1 `
    -Domain tapnetravel.com `
    -WwwDomain www.tapnetravel.com `
    -ImageTag cloudrun-check `
    -Verbose
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateNotNullOrEmpty()]
    [string]$ProjectId = "tapne-487110",

    [ValidateNotNullOrEmpty()]
    [string]$Region = "asia-south1",

    [ValidateNotNullOrEmpty()]
    [string]$Repository = "tapne",

    [ValidateNotNullOrEmpty()]
    [string]$ImageName = "tapne-web",

    [ValidateNotNullOrEmpty()]
    [string]$ImageTag = "cloudrun-check",

    [ValidateNotNullOrEmpty()]
    [string]$ServiceName = "tapne-web",

    [ValidateNotNullOrEmpty()]
    [string]$Domain = "tapnetravel.com",

    [string]$WwwDomain = "www.tapnetravel.com",

    [switch]$SkipAuthLogin,
    [switch]$SkipMigrations,
    [switch]$SkipSmokeTest,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($ExtraArgs -contains "--verbose") {
    $VerbosePreference = "Continue"
    Write-Verbose "Verbose logging enabled via --verbose."
}

$unsupportedArgs = @($ExtraArgs | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and $_ -ne "--verbose" })
if ($unsupportedArgs.Count -gt 0) {
    Write-Warning ("Ignoring unsupported argument(s): {0}" -f ($unsupportedArgs -join ", "))
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ("==> {0}" -f $Message) -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host ("[OK] {0}" -f $Message) -ForegroundColor Green
}

function Resolve-PowerShellExe {
    $pwshPath = Join-Path $PSHOME "pwsh.exe"
    if (Test-Path -LiteralPath $pwshPath -PathType Leaf) {
        return $pwshPath
    }

    $powershellPath = Join-Path $PSHOME "powershell.exe"
    if (Test-Path -LiteralPath $powershellPath -PathType Leaf) {
        return $powershellPath
    }

    $pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($null -ne $pwshCmd -and -not [string]::IsNullOrWhiteSpace($pwshCmd.Source)) {
        return $pwshCmd.Source
    }

    $psCmd = Get-Command powershell -ErrorAction SilentlyContinue
    if ($null -ne $psCmd -and -not [string]::IsNullOrWhiteSpace($psCmd.Source)) {
        return $psCmd.Source
    }

    throw "Could not find a PowerShell executable (pwsh or powershell)."
}

function Get-UniqueDomains {
    param(
        [string]$Primary,
        [string]$Secondary
    )

    $domains = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in @($Primary, $Secondary)) {
        $normalized = ([string]$candidate).Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($normalized)) {
            continue
        }
        if (-not $domains.Contains($normalized)) {
            [void]$domains.Add($normalized)
        }
    }

    return @($domains)
}

function Invoke-ScriptStep {
    param(
        [string]$StepName,
        [string]$PowerShellExe,
        [string]$ScriptPath,
        [string[]]$Arguments
    )

    if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        throw ("Step '{0}' script not found: {1}" -f $StepName, $ScriptPath)
    }

    Write-Step ("{0}" -f $StepName)
    Write-Verbose ("Executing: {0}" -f $ScriptPath)
    if ($Arguments.Count -gt 0) {
        Write-Verbose ("Arguments: {0}" -f ($Arguments -join " "))
    }

    $stepStart = Get-Date
    $global:LASTEXITCODE = 0
    & $PowerShellExe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @Arguments
    $exitCode = [int]$LASTEXITCODE

    if ($exitCode -ne 0) {
        throw ("Step '{0}' failed with exit code {1}." -f $StepName, $exitCode)
    }

    $elapsed = (Get-Date) - $stepStart
    Write-Ok ("{0} completed in {1:hh\:mm\:ss}" -f $StepName, $elapsed)
}

$isVerbose = $VerbosePreference -eq "Continue"
$powerShellExe = Resolve-PowerShellExe
$scriptDirectory = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path

$domains = Get-UniqueDomains -Primary $Domain -Secondary $WwwDomain
if ($domains.Count -eq 0) {
    throw "At least one non-empty domain is required."
}

$canonicalHost = $domains[0]
$djangoAllowedHosts = ($domains -join ",")
$csrfTrustedOrigins = (($domains | ForEach-Object { "https://{0}" -f $_ }) -join ",")

$localImageRef = "{0}:{1}" -f $ImageName, $ImageTag
$artifactImageRef = "{0}-docker.pkg.dev/{1}/{2}/{3}:{4}" -f $Region, $ProjectId, $Repository, $ImageName, $ImageTag

$setupScript = Join-Path $scriptDirectory "setup-faithful-local.ps1"
$checkScript = Join-Path $scriptDirectory "check-cloud-run-web-image.ps1"
$pushScript = Join-Path $scriptDirectory "push-web-image-to-artifact.ps1"
$domainScript = Join-Path $scriptDirectory "setup-custom-domain.ps1"
$deployScript = Join-Path $scriptDirectory "deploy-cloud-run.ps1"

$setupArgs = @(
    "-Verbose:$isVerbose"
)

$checkArgs = @(
    "--image", $localImageRef,
    "--artifact-image", $artifactImageRef,
    "--service", $ServiceName,
    "--region", $Region
)
if ($isVerbose) {
    $checkArgs += "--verbose"
}

$pushArgs = @(
    "-ProjectId", $ProjectId,
    "-Region", $Region,
    "-Repository", $Repository,
    "-ImageName", $ImageName,
    "-ImageTag", $ImageTag,
    "-SkipAuthLogin:$([bool]$SkipAuthLogin)",
    "-Verbose:$isVerbose"
)

$domainArgs = @(
    "-ProjectId", $ProjectId,
    "-Region", $Region,
    "-ServiceName", $ServiceName,
    "-Domain", $Domain,
    "-WwwDomain", $WwwDomain,
    "-SkipAuthLogin:$([bool]$SkipAuthLogin)",
    "-Verbose:$isVerbose"
)

$deployArgs = @(
    "-ProjectId", $ProjectId,
    "-Region", $Region,
    "-Repository", $Repository,
    "-ImageName", $ImageName,
    "-ImageTag", $ImageTag,
    "-ServiceName", $ServiceName,
    "-BuildAndPushImage:$false",
    "-SkipAuthLogin:$([bool]$SkipAuthLogin)",
    "-SkipMigrations:$([bool]$SkipMigrations)",
    "-SkipSmokeTest:$([bool]$SkipSmokeTest)",
    "-CloudRunIngress", "internal-and-cloud-load-balancing",
    "-DjangoAllowedHosts", $djangoAllowedHosts,
    "-CsrfTrustedOrigins", $csrfTrustedOrigins,
    "-CanonicalHost", $canonicalHost,
    "-SmokeBaseUrl", ("https://{0}" -f $canonicalHost),
    "-UptimeCheckHost", $canonicalHost,
    "-Verbose:$isVerbose"
)

Write-Verbose (
    "Run options => ProjectId={0}; Region={1}; Repository={2}; Image={3}; Tag={4}; Service={5}; Domains={6}; RepoRoot={7}; SkipAuthLogin={8}; SkipMigrations={9}; SkipSmokeTest={10}" -f
    $ProjectId, $Region, $Repository, $ImageName, $ImageTag, $ServiceName, ($domains -join ","), $repoRoot, $SkipAuthLogin, $SkipMigrations, $SkipSmokeTest
)

$startTime = Get-Date
try {
    Invoke-ScriptStep -StepName "1/5 setup-faithful-local" -PowerShellExe $powerShellExe -ScriptPath $setupScript -Arguments $setupArgs
    Invoke-ScriptStep -StepName "2/5 check-cloud-run-web-image" -PowerShellExe $powerShellExe -ScriptPath $checkScript -Arguments $checkArgs
    Invoke-ScriptStep -StepName "3/5 push-web-image-to-artifact" -PowerShellExe $powerShellExe -ScriptPath $pushScript -Arguments $pushArgs
    Invoke-ScriptStep -StepName "4/5 setup-custom-domain" -PowerShellExe $powerShellExe -ScriptPath $domainScript -Arguments $domainArgs
    Invoke-ScriptStep -StepName "5/5 deploy-cloud-run" -PowerShellExe $powerShellExe -ScriptPath $deployScript -Arguments $deployArgs
}
catch {
    Write-Host ""
    Write-Host ("[FAILED] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}

$totalElapsed = (Get-Date) - $startTime
Write-Host ""
Write-Host "Workflow summary:" -ForegroundColor Cyan
Write-Host ("  Local image:     {0}" -f $localImageRef)
Write-Host ("  Artifact image:  {0}" -f $artifactImageRef)
Write-Host ("  Canonical host:  {0}" -f $canonicalHost)
Write-Host ("  Total duration:  {0:hh\:mm\:ss}" -f $totalElapsed)
Write-Host ""
Write-Ok "All workflow steps completed successfully."
