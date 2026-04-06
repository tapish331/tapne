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
  avoids duplicate builds by:
    - building once during setup-faithful-local
    - running check-cloud-run-web-image with --no-build
    - running push-web-image-to-artifact with -NoBuild
    - setting deploy to -BuildAndPushImage:$false so step 3 is the single push step

.EXAMPLE
  pwsh -File infra/run-cloud-run-workflow.ps1 -Verbose

.EXAMPLE
  pwsh -File infra/run-cloud-run-workflow.ps1 -AutoStartDocker -Verbose

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
    [string]$GoogleMapsApiKey = "",

    [switch]$SkipAuthLogin,
    [switch]$SkipMigrations,
    [switch]$SkipSmokeTest,
    [bool]$DisableBuildAttestations = $true,
    [bool]$DisableContainerVulnerabilityScanning = $true,
    [switch]$AutoStartDocker,
    [switch]$NoAutoStartDocker,

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

$EnableAutoStartDocker = $true
if ($PSBoundParameters.ContainsKey("AutoStartDocker")) {
    $EnableAutoStartDocker = [bool]$AutoStartDocker
}
if ($NoAutoStartDocker) {
    $EnableAutoStartDocker = $false
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

function Get-DotEnvValue {
    param(
        [string]$FilePath,
        [string]$Name
    )

    if ([string]::IsNullOrWhiteSpace($FilePath) -or -not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        return ""
    }
    if ([string]::IsNullOrWhiteSpace($Name)) {
        return ""
    }

    $targetName = $Name.Trim()
    foreach ($line in (Get-Content -LiteralPath $FilePath)) {
        $rawLine = [string]$line
        if ([string]::IsNullOrWhiteSpace($rawLine)) {
            continue
        }
        $trimmedLine = $rawLine.Trim()
        if ($trimmedLine.StartsWith("#")) {
            continue
        }
        if ($trimmedLine.StartsWith("export ")) {
            $trimmedLine = $trimmedLine.Substring(7).TrimStart()
        }

        $equalsIndex = $trimmedLine.IndexOf("=")
        if ($equalsIndex -lt 1) {
            continue
        }

        $key = $trimmedLine.Substring(0, $equalsIndex).Trim()
        if (-not [string]::Equals($key, $targetName, [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }

        $value = $trimmedLine.Substring($equalsIndex + 1).Trim()
        if ($value.Length -ge 2) {
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        return $value.Trim()
    }

    return ""
}

function Invoke-ScriptStep {
    param(
        [string]$StepName,
        [string]$PowerShellExe,
        [string]$ScriptPath,
        [object[]]$Arguments
    )

    if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        throw ("Step '{0}' script not found: {1}" -f $StepName, $ScriptPath)
    }

    Write-Step ("{0}" -f $StepName)
    Write-Verbose ("Executing: {0}" -f $ScriptPath)
    if ($Arguments.Count -gt 0) {
        Write-Verbose ("Arguments: {0}" -f ($Arguments -join " "))
    }

    function Convert-ToPowerShellLiteral {
        param([object]$Value)

        if ($null -eq $Value) {
            return '$null'
        }
        if ($Value -is [string] -and $Value.StartsWith("-")) {
            return [string]$Value
        }
        if ($Value -is [bool]) {
            return $(if ($Value) { '$true' } else { '$false' })
        }
        if ($Value -is [byte] -or $Value -is [int16] -or $Value -is [int32] -or $Value -is [int64] -or $Value -is [decimal] -or $Value -is [double] -or $Value -is [single]) {
            return [string]$Value
        }

        $text = [string]$Value
        return "'" + $text.Replace("'", "''") + "'"
    }

    $stepStart = Get-Date
    $global:LASTEXITCODE = 0
    $serializedArgs = @($Arguments | ForEach-Object { Convert-ToPowerShellLiteral -Value $_ })
    $commandText = "& {0}{1}" -f (Convert-ToPowerShellLiteral -Value $ScriptPath), $(if ($serializedArgs.Count -gt 0) { " " + ($serializedArgs -join " ") } else { "" })
    & $PowerShellExe -NoProfile -ExecutionPolicy Bypass -Command $commandText
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

$resolvedGoogleMapsApiKey = ""
if (-not [string]::IsNullOrWhiteSpace($GoogleMapsApiKey)) {
    $resolvedGoogleMapsApiKey = $GoogleMapsApiKey.Trim()
}
elseif (-not [string]::IsNullOrWhiteSpace($env:GOOGLE_MAPS_API_KEY)) {
    $resolvedGoogleMapsApiKey = $env:GOOGLE_MAPS_API_KEY.Trim()
}
elseif (-not [string]::IsNullOrWhiteSpace($env:GOOGLE_PLACES_API_KEY)) {
    $resolvedGoogleMapsApiKey = $env:GOOGLE_PLACES_API_KEY.Trim()
}
else {
    $dotEnvPath = Join-Path $repoRoot ".env"
    $dotEnvMapsApiKey = Get-DotEnvValue -FilePath $dotEnvPath -Name "GOOGLE_MAPS_API_KEY"
    if ([string]::IsNullOrWhiteSpace($dotEnvMapsApiKey)) {
        $dotEnvMapsApiKey = Get-DotEnvValue -FilePath $dotEnvPath -Name "GOOGLE_PLACES_API_KEY"
    }
    if (-not [string]::IsNullOrWhiteSpace($dotEnvMapsApiKey)) {
        $resolvedGoogleMapsApiKey = $dotEnvMapsApiKey.Trim()
    }
}
if (-not [string]::IsNullOrWhiteSpace($resolvedGoogleMapsApiKey)) {
    $env:GOOGLE_MAPS_API_KEY = $resolvedGoogleMapsApiKey
}

# Resolve GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET from env or .env file
$dotEnvPath = Join-Path $repoRoot ".env"
if ([string]::IsNullOrWhiteSpace($env:GOOGLE_CLIENT_ID)) {
    $dotEnvClientId = Get-DotEnvValue -FilePath $dotEnvPath -Name "GOOGLE_CLIENT_ID"
    if (-not [string]::IsNullOrWhiteSpace($dotEnvClientId)) {
        $env:GOOGLE_CLIENT_ID = $dotEnvClientId.Trim()
    }
}
if ([string]::IsNullOrWhiteSpace($env:GOOGLE_CLIENT_SECRET)) {
    $dotEnvClientSecret = Get-DotEnvValue -FilePath $dotEnvPath -Name "GOOGLE_CLIENT_SECRET"
    if (-not [string]::IsNullOrWhiteSpace($dotEnvClientSecret)) {
        $env:GOOGLE_CLIENT_SECRET = $dotEnvClientSecret.Trim()
    }
}

$localImageRef = "{0}:{1}" -f $ImageName, $ImageTag
$artifactImageRef = "{0}-docker.pkg.dev/{1}/{2}/{3}:{4}" -f $Region, $ProjectId, $Repository, $ImageName, $ImageTag

$buildScript = Join-Path $scriptDirectory "build-lovable-production-frontend.ps1"
$setupScript = Join-Path $scriptDirectory "setup-faithful-local.ps1"
$checkScript = Join-Path $scriptDirectory "check-cloud-run-web-image.ps1"
$pushScript = Join-Path $scriptDirectory "push-web-image-to-artifact.ps1"
$domainScript = Join-Path $scriptDirectory "setup-custom-domain.ps1"
$deployScript = Join-Path $scriptDirectory "deploy-cloud-run.ps1"

$buildArgs = @("-RepoRoot", $repoRoot)
if ($isVerbose) { $buildArgs += "-Verbose" }

$setupArgs = @(
    "-WebImageRef", $localImageRef,
    "-DisableBuildAttestations", $DisableBuildAttestations
)
if (-not $EnableAutoStartDocker) {
    $setupArgs += "-NoAutoStartDocker"
}
if ($isVerbose) {
    $setupArgs += "-Verbose"
}

$checkArgs = @(
    "--no-build",
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
    "-NoBuild",
    "-DisableBuildAttestations", $DisableBuildAttestations,
    "-DisableContainerVulnerabilityScanning", $DisableContainerVulnerabilityScanning
)
if ($SkipAuthLogin) {
    $pushArgs += "-SkipAuthLogin"
}
if ($isVerbose) {
    $pushArgs += "-Verbose"
}

$domainArgs = @(
    "-ProjectId", $ProjectId,
    "-Region", $Region,
    "-ServiceName", $ServiceName,
    "-Domain", $Domain,
    "-WwwDomain", $WwwDomain
)
if ($SkipAuthLogin) {
    $domainArgs += "-SkipAuthLogin"
}
if ($isVerbose) {
    $domainArgs += "-Verbose"
}

$deployArgs = @(
    "-ProjectId", $ProjectId,
    "-Region", $Region,
    "-Repository", $Repository,
    "-ImageName", $ImageName,
    "-ImageTag", $ImageTag,
    "-ServiceName", $ServiceName,
    "-BuildAndPushImage", $false,
    "-DisableContainerVulnerabilityScanning", $DisableContainerVulnerabilityScanning,
    "-CloudRunIngress", "internal-and-cloud-load-balancing",
    "-DjangoAllowedHosts", $djangoAllowedHosts,
    "-CsrfTrustedOrigins", $csrfTrustedOrigins,
    "-CanonicalHost", $canonicalHost,
    "-SmokeBaseUrl", ("https://{0}" -f $canonicalHost),
    "-UptimeCheckHost", $canonicalHost,
    "-SmokeCssPath", "/",
    "-SmokeJsPath", "/sitemap.xml"
)
if ($SkipAuthLogin) {
    $deployArgs += "-SkipAuthLogin"
}
if ($SkipMigrations) {
    $deployArgs += "-SkipMigrations"
}
if ($SkipSmokeTest) {
    $deployArgs += "-SkipSmokeTest"
}
if ($isVerbose) {
    $deployArgs += "-Verbose"
}

Write-Verbose (
    "Run options => ProjectId={0}; Region={1}; Repository={2}; Image={3}; Tag={4}; Service={5}; Domains={6}; RepoRoot={7}; SkipAuthLogin={8}; SkipMigrations={9}; SkipSmokeTest={10}; AutoStartDocker={11}; DisableBuildAttestations={12}; DisableContainerVulnerabilityScanning={13}; GoogleMapsApiKeySet={14}" -f
    $ProjectId, $Region, $Repository, $ImageName, $ImageTag, $ServiceName, ($domains -join ","), $repoRoot, $SkipAuthLogin, $SkipMigrations, $SkipSmokeTest, $EnableAutoStartDocker, $DisableBuildAttestations, $DisableContainerVulnerabilityScanning, (-not [string]::IsNullOrWhiteSpace($resolvedGoogleMapsApiKey))
)

$startTime = Get-Date
try {
    Invoke-ScriptStep -StepName "1/6 build-lovable-production-frontend" -PowerShellExe $powerShellExe -ScriptPath $buildScript -Arguments $buildArgs
    Invoke-ScriptStep -StepName "2/6 setup-faithful-local" -PowerShellExe $powerShellExe -ScriptPath $setupScript -Arguments $setupArgs
    Invoke-ScriptStep -StepName "3/6 check-cloud-run-web-image" -PowerShellExe $powerShellExe -ScriptPath $checkScript -Arguments $checkArgs
    Invoke-ScriptStep -StepName "4/6 push-web-image-to-artifact" -PowerShellExe $powerShellExe -ScriptPath $pushScript -Arguments $pushArgs
    Invoke-ScriptStep -StepName "5/6 setup-custom-domain" -PowerShellExe $powerShellExe -ScriptPath $domainScript -Arguments $domainArgs
    Invoke-ScriptStep -StepName "6/6 deploy-cloud-run" -PowerShellExe $powerShellExe -ScriptPath $deployScript -Arguments $deployArgs
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
