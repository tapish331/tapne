<#
.SYNOPSIS
  Idempotently bootstraps GCP Artifact Registry setup and pushes the Tapne web image.

.DESCRIPTION
  This script performs the full "setup + upload" flow for Artifact Registry:
    1) Verifies gcloud + docker are available
    2) Ensures you are authenticated with gcloud
    3) Sets the active gcloud project
    4) Enables artifactregistry.googleapis.com
    5) Ensures the Docker repository exists (creates it if missing)
    6) Configures Docker auth for REGION-docker.pkg.dev
    7) Builds the local web image (unless -NoBuild)
    8) Tags and pushes to Artifact Registry
    9) Verifies manifest contains linux/amd64 (best effort)

  Pushing the same remote tag replaces the previous tag target (normal registry behavior).

.PARAMETER ProjectId
  GCP project id.

.PARAMETER Region
  Artifact Registry region, e.g. asia-south1.

.PARAMETER Repository
  Artifact Registry repository name.

.PARAMETER ImageName
  Image name inside the repository, e.g. tapne-web.

.PARAMETER ImageTag
  Image tag to push, e.g. cloudrun-check.

.PARAMETER LocalImageRef
  Local Docker image ref to tag/push. Defaults to "<ImageName>:<ImageTag>".

.PARAMETER Dockerfile
  Dockerfile path, relative to repo root by default.

.PARAMETER BuildContext
  Docker build context path, relative to repo root by default.

.PARAMETER NoBuild
  Skip docker build and push an existing local image.

.PARAMETER SkipAuthLogin
  Do not auto-run "gcloud auth login" when no active account is found.

.EXAMPLE
  pwsh -File infra/push-web-image-to-artifact.ps1 -Verbose

.EXAMPLE
  pwsh -File infra/push-web-image-to-artifact.ps1 `
    -ProjectId tapne-487110 `
    -Region asia-south1 `
    -Repository tapne `
    -ImageName tapne-web `
    -ImageTag cloudrun-check `
    -Verbose

.EXAMPLE
  pwsh -File infra/push-web-image-to-artifact.ps1 -NoBuild -Verbose
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

    [string]$LocalImageRef = "",

    [ValidateNotNullOrEmpty()]
    [string]$Dockerfile = "infra/Dockerfile.web",

    [ValidateNotNullOrEmpty()]
    [string]$BuildContext = ".",

    [switch]$NoBuild,
    [switch]$SkipAuthLogin,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
# Native stderr should not be treated as terminating errors for gcloud/docker.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}
# Avoid noisy update-check output during automation.
$env:CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK = "1"

if ($ExtraArgs -contains "--verbose") {
    $VerbosePreference = "Continue"
    Write-Verbose "Verbose logging enabled via --verbose."
}

$unsupportedArgs = @($ExtraArgs | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and $_ -ne "--verbose" })
if ($unsupportedArgs.Count -gt 0) {
    Write-Warning ("Ignoring unsupported argument(s): {0}" -f ($unsupportedArgs -join ", "))
}

if ([string]::IsNullOrWhiteSpace($LocalImageRef)) {
    $LocalImageRef = "{0}:{1}" -f $ImageName, $ImageTag
}

$registryHost = "{0}-docker.pkg.dev" -f $Region
$remoteImageRef = "{0}/{1}/{2}/{3}:{4}" -f $registryHost, $ProjectId, $Repository, $ImageName, $ImageTag
$remoteImagePath = "{0}/{1}/{2}/{3}" -f $registryHost, $ProjectId, $Repository, $ImageName
$gcloudCli = "gcloud"
$gcloudCmdCandidate = Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue
if ($null -ne $gcloudCmdCandidate) {
    $gcloudCli = $gcloudCmdCandidate.Source
}

$scriptDirectory = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path
$dockerfilePath = Join-Path $repoRoot $Dockerfile
$buildContextPath = Join-Path $repoRoot $BuildContext

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ("==> {0}" -f $Message) -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host ("[OK] {0}" -f $Message) -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host ("[INFO] {0}" -f $Message) -ForegroundColor Yellow
}

function Test-CommandExists {
    param([string]$CommandName)
    return [bool](Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function Invoke-External {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 0
    )

    Write-Verbose ("Running: {0} {1}" -f $FilePath, ($Arguments -join " "))

    if ($TimeoutSeconds -gt 0) {
        $job = Start-Job -ScriptBlock {
            param(
                [string]$InnerFilePath,
                [string[]]$InnerArguments
            )
            $ErrorActionPreference = "SilentlyContinue"
            $jobOutput = & $InnerFilePath @InnerArguments 2>&1 | ForEach-Object { $_.ToString() }
            return [PSCustomObject]@{
                ExitCode = $LASTEXITCODE
                Output   = @($jobOutput)
            }
        } -ArgumentList $FilePath, @($Arguments)

        $completed = Wait-Job -Job $job -Timeout $TimeoutSeconds
        if ($null -eq $completed) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue | Out-Null
            Remove-Job -Job $job -ErrorAction SilentlyContinue
            return [PSCustomObject]@{
                ExitCode = 124
                Output   = @("Command timed out after {0} second(s)." -f $TimeoutSeconds)
            }
        }

        $jobResult = Receive-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -ErrorAction SilentlyContinue
        if ($null -eq $jobResult) {
            return [PSCustomObject]@{
                ExitCode = 1
                Output   = @("Command returned no output/result.")
            }
        }

        return [PSCustomObject]@{
            ExitCode = [int]$jobResult.ExitCode
            Output   = @($jobResult.Output)
        }
    }

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $output = & $FilePath @Arguments 2>&1 | ForEach-Object { $_.ToString() }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return [PSCustomObject]@{
        ExitCode = $exitCode
        Output   = @($output)
    }
}

function Invoke-Required {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$FailureMessage,
        [int]$TimeoutSeconds = 0,
        [switch]$PassThru
    )

    $result = Invoke-External -FilePath $FilePath -Arguments $Arguments -TimeoutSeconds $TimeoutSeconds
    if ($result.ExitCode -ne 0) {
        $details = ($result.Output -join [Environment]::NewLine).Trim()
        if ([string]::IsNullOrWhiteSpace($details)) {
            throw $FailureMessage
        }

        throw ("{0}`n{1}" -f $FailureMessage, $details)
    }

    foreach ($line in $result.Output) {
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            Write-Verbose $line
        }
    }

    if ($PassThru) {
        return $result.Output
    }
}

Write-Verbose (
    "Run options => ProjectId={0}; Region={1}; Repository={2}; ImageName={3}; ImageTag={4}; LocalImageRef={5}; NoBuild={6}; SkipAuthLogin={7}" -f
    $ProjectId, $Region, $Repository, $ImageName, $ImageTag, $LocalImageRef, $NoBuild, $SkipAuthLogin
)

Write-Step "Preflight checks"
if (-not (Test-CommandExists -CommandName "gcloud")) {
    throw "gcloud CLI is not available on PATH."
}
if (-not (Test-CommandExists -CommandName "docker")) {
    throw "Docker CLI is not available on PATH."
}

Invoke-Required -FilePath $gcloudCli -Arguments @("--version") -TimeoutSeconds 30 -FailureMessage "gcloud is installed but not functioning."
Invoke-Required -FilePath "docker" -Arguments @("version", "--format", "{{.Server.Version}}") -TimeoutSeconds 45 -FailureMessage "Docker daemon check timed out or failed. Restart Docker Desktop and retry."
Write-Ok "gcloud and docker are available."

Write-Step "Ensuring gcloud authentication"
$activeAccountResult = Invoke-External -FilePath $gcloudCli -Arguments @("auth", "list", "--filter=status:ACTIVE", "--format=value(account)")
$activeAccount = ($activeAccountResult.Output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1)

if ([string]::IsNullOrWhiteSpace($activeAccount)) {
    if ($SkipAuthLogin) {
        throw "No active gcloud account found and -SkipAuthLogin was set."
    }

    Write-Info "No active gcloud account detected. Launching interactive login..."
    Invoke-Required -FilePath $gcloudCli -Arguments @("auth", "login") -FailureMessage "gcloud auth login failed."

    $activeAccountResult = Invoke-External -FilePath $gcloudCli -Arguments @("auth", "list", "--filter=status:ACTIVE", "--format=value(account)")
    $activeAccount = ($activeAccountResult.Output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1)
}

if ([string]::IsNullOrWhiteSpace($activeAccount)) {
    throw "No active gcloud account found after login."
}

Write-Ok ("Using gcloud account: {0}" -f $activeAccount)

Write-Step "Setting gcloud project"
Invoke-Required -FilePath $gcloudCli -Arguments @("config", "set", "project", $ProjectId) -FailureMessage ("Failed to set gcloud project to '{0}'." -f $ProjectId)
$effectiveProject = (Invoke-Required -FilePath $gcloudCli -Arguments @("config", "get-value", "project") -FailureMessage "Failed to read active gcloud project." -PassThru | Select-Object -First 1)
Write-Ok ("Active project: {0}" -f $effectiveProject)

Write-Step "Ensuring Artifact Registry API is enabled"
Invoke-Required -FilePath $gcloudCli -Arguments @("services", "enable", "artifactregistry.googleapis.com", "--project", $ProjectId) -FailureMessage "Failed to enable artifactregistry.googleapis.com."
Write-Ok "Artifact Registry API is enabled."

Write-Step "Ensuring Artifact Registry repository exists"
$repoDescribe = Invoke-External -FilePath $gcloudCli -Arguments @(
    "artifacts", "repositories", "describe", $Repository,
    "--project", $ProjectId,
    "--location", $Region,
    "--format=value(name)"
)

if ($repoDescribe.ExitCode -eq 0) {
    Write-Ok ("Repository already exists: {0}" -f $Repository)
}
else {
    Write-Info ("Repository '{0}' not found in {1}. Creating..." -f $Repository, $Region)
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "artifacts", "repositories", "create", $Repository,
        "--project", $ProjectId,
        "--repository-format", "docker",
        "--location", $Region,
        "--description", "Tapne container images"
    ) -FailureMessage ("Failed to create Artifact Registry repository '{0}'." -f $Repository)
    Write-Ok ("Repository created: {0}" -f $Repository)
}

Write-Step "Configuring Docker auth helper for Artifact Registry"
Invoke-Required -FilePath $gcloudCli -Arguments @("auth", "configure-docker", $registryHost, "--quiet") -FailureMessage ("Failed to configure docker auth for {0}." -f $registryHost)
Write-Ok ("Docker auth configured for {0}" -f $registryHost)

if (-not (Test-Path -Path $dockerfilePath -PathType Leaf)) {
    throw ("Dockerfile not found: {0}" -f $dockerfilePath)
}
if (-not (Test-Path -Path $buildContextPath -PathType Container -ErrorAction SilentlyContinue) -and -not (Test-Path -Path $buildContextPath -PathType Leaf -ErrorAction SilentlyContinue)) {
    throw ("Build context path not found: {0}" -f $buildContextPath)
}

if (-not $NoBuild) {
    Write-Step "Building local web image"
    Invoke-Required -FilePath "docker" -Arguments @("build", "-f", $dockerfilePath, "-t", $LocalImageRef, $buildContextPath) -FailureMessage ("Docker build failed for '{0}'." -f $LocalImageRef)
    Write-Ok ("Built local image: {0}" -f $LocalImageRef)
}
else {
    Write-Step "Skipping build (-NoBuild)"
    $inspectLocal = Invoke-External -FilePath "docker" -Arguments @("image", "inspect", $LocalImageRef)
    if ($inspectLocal.ExitCode -ne 0) {
        throw ("Local image '{0}' not found and -NoBuild was set." -f $LocalImageRef)
    }
    Write-Ok ("Using existing local image: {0}" -f $LocalImageRef)
}

Write-Step "Checking existing remote tag (replace behavior)"
$existingTagResult = Invoke-External -FilePath $gcloudCli -Arguments @(
    "artifacts", "docker", "tags", "list", $remoteImagePath,
    "--project", $ProjectId,
    "--filter", ("tag:{0}" -f $ImageTag),
    "--format=value(version)"
)
$existingDigest = ($existingTagResult.Output | Where-Object { $_ -match '^sha256:' } | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($existingDigest)) {
    $existingDigest = ($existingTagResult.Output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1)
}
if (-not [string]::IsNullOrWhiteSpace($existingDigest)) {
    Write-Info ("Remote tag already exists and will be replaced: {0}" -f $remoteImageRef)
}
else {
    Write-Info ("Remote tag does not exist yet: {0}" -f $remoteImageRef)
}

Write-Step "Tagging and pushing image"
Invoke-Required -FilePath "docker" -Arguments @("tag", $LocalImageRef, $remoteImageRef) -FailureMessage "Failed to tag image for Artifact Registry."
Invoke-Required -FilePath "docker" -Arguments @("push", $remoteImageRef) -FailureMessage "Failed to push image to Artifact Registry."
Write-Ok ("Pushed image: {0}" -f $remoteImageRef)

Write-Step "Post-push verification"
$manifestResult = Invoke-External -FilePath "docker" -Arguments @("manifest", "inspect", $remoteImageRef)
if ($manifestResult.ExitCode -eq 0) {
    try {
        $manifestJson = ($manifestResult.Output -join [Environment]::NewLine) | ConvertFrom-Json
        $hasLinuxAmd64 = $false

        if ($null -ne $manifestJson.manifests) {
            foreach ($manifestItem in $manifestJson.manifests) {
                if ($manifestItem.platform.os -eq "linux" -and $manifestItem.platform.architecture -eq "amd64") {
                    $hasLinuxAmd64 = $true
                    break
                }
            }
        }
        elseif ($manifestJson.os -eq "linux" -and $manifestJson.architecture -eq "amd64") {
            $hasLinuxAmd64 = $true
        }

        if ($hasLinuxAmd64) {
            Write-Ok "Manifest includes linux/amd64."
        }
        else {
            Write-Warning "Manifest was read but linux/amd64 was not explicitly detected."
        }
    }
    catch {
        Write-Warning "Manifest output could not be parsed as JSON."
    }
}
else {
    Write-Warning "Could not inspect pushed manifest in this shell. Push already succeeded."
}

Write-Host ""
Write-Host "Remote image ref:" -ForegroundColor Cyan
Write-Host ("  {0}" -f $remoteImageRef)
Write-Host ""
Write-Ok "Artifact Registry setup + web image upload completed."
