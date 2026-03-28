<#
.SYNOPSIS
  Provision and deploy Tapne web to Cloud Run (gcloud 443 compatible).

.DESCRIPTION
  Idempotent end-to-end deploy automation for this repo:
  - Enables required GCP APIs
  - Provisions runtime service account + IAM
  - Provisions Cloud SQL/Postgres, Redis, VPC connector, and GCS bucket
  - Upserts required secrets
  - Builds/pushes image via infra/push-web-image-to-artifact.ps1
  - Runs migrations as a Cloud Run Job
  - Deploys Cloud Run web service and smoke-tests health/static endpoints

  Uses gcloud flags supported in SDK 443.0.0:
  --vpc-connector and --vpc-egress (not --network/--subnet on run deploy).
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

    [string]$ImageTag = "",

    [ValidateNotNullOrEmpty()]
    [string]$ServiceName = "tapne-web",

    [ValidateNotNullOrEmpty()]
    [string]$ServiceAccountName = "tapne-runtime",

    [ValidateNotNullOrEmpty()]
    [string]$CloudSqlInstance = "tapne-pg",

    [ValidateNotNullOrEmpty()]
    [string]$CloudSqlDatabase = "tapne_db",

    [ValidateNotNullOrEmpty()]
    [string]$CloudSqlUser = "tapne",

    [ValidateNotNullOrEmpty()]
    [string]$CloudSqlTier = "db-f1-micro",

    [ValidateRange(10, 65536)]
    [int]$CloudSqlStorageGb = 10,

    [ValidateSet("SSD", "HDD")]
    [string]$CloudSqlStorageType = "HDD",

    [ValidateNotNullOrEmpty()]
    [string]$CloudSqlDatabaseVersion = "POSTGRES_15",

    [string]$CloudSqlReplacementInstance = "",

    [ValidateNotNullOrEmpty()]
    [string]$RedisInstance = "tapne-redis",

    [ValidateRange(1, 300)]
    [int]$RedisSizeGb = 1,

    [bool]$EnableRedis = $false,

    [ValidateNotNullOrEmpty()]
    [string]$Network = "default",

    [ValidateNotNullOrEmpty()]
    [string]$VpcConnector = "tapne-svpc",

    [ValidateNotNullOrEmpty()]
    [string]$VpcConnectorRange = "10.8.0.0/28",

    [string]$BucketName = "",

    [ValidateRange(1, 8)]
    [int]$CloudRunCpu = 1,

    [ValidateNotNullOrEmpty()]
    [string]$CloudRunMemory = "1Gi",

    [ValidateRange(30, 3600)]
    [int]$CloudRunTimeoutSeconds = 300,

    [ValidateRange(0, 1000)]
    [int]$CloudRunMinInstances = 0,

    [ValidateRange(1, 2000)]
    [int]$CloudRunMaxInstances = 10,

    [ValidateRange(1, 32)]
    [int]$WebConcurrency = 2,

    [ValidateRange(30, 600)]
    [int]$GunicornTimeout = 120,

    [ValidateRange(1, 1000)]
    [int]$CloudRunConcurrency = 10,

    [ValidateSet("all", "internal", "internal-and-cloud-load-balancing")]
    [string]$CloudRunIngress = "internal-and-cloud-load-balancing",

    [ValidatePattern("^\d{2}:\d{2}$")]
    [string]$CloudSqlBackupStartTime = "03:00",

    [bool]$EnableCloudSqlBackups = $true,
    [bool]$EnableCloudSqlPointInTimeRecovery = $true,
    [bool]$UsePrivateCloudSqlIp = $true,

    [string]$PrivateServiceRangeName = "",

    [ValidateRange(16, 24)]
    [int]$PrivateServiceRangePrefixLength = 16,

    [bool]$EnableGcsSignedUrls = $true,

    [bool]$ConfigureMonitoring = $true,
    [string[]]$MonitoringNotificationChannels = @(),

    [bool]$BuildAndPushImage = $true,
    [bool]$DisableBuildAttestations = $true,
    [bool]$DisableContainerVulnerabilityScanning = $true,
    [bool]$AutoFixGcsDependency = $true,
    [bool]$AllowUnauthenticated = $true,

    [string[]]$DjangoAllowedHosts = @(),
    [string[]]$CsrfTrustedOrigins = @(),
    [string]$CanonicalHost = "",
    [string]$GoogleMapsApiKey = "",

    [string]$SmokeBaseUrl = "",
    [string]$SmokeHealthPath = "/runtime/health/",
    [string]$SmokeCssPath = "/static/css/tapne.css",
    [string]$SmokeJsPath = "/static/js/tapne-ui.js",

    [string]$UptimeCheckHost = "",
    [string]$UptimeCheckPath = "/runtime/health/",

    [switch]$SkipMigrations,
    [switch]$RunBootstrapRuntime,
    [switch]$SkipSmokeTest,
    [switch]$ValidateOnly,
    [switch]$SkipAuthLogin,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$env:CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK = "1"

if ($ExtraArgs -contains "--verbose") {
    $VerbosePreference = "Continue"
    Write-Verbose "Verbose logging enabled via --verbose."
}

$unsupportedArgs = @($ExtraArgs | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and $_ -ne "--verbose" })
if ($unsupportedArgs.Count -gt 0) {
    Write-Warning ("Ignoring unsupported argument(s): {0}" -f ($unsupportedArgs -join ", "))
}

if ([string]::IsNullOrWhiteSpace($ImageTag)) {
    $ImageTag = "cloudrun-{0}" -f (Get-Date -Format "yyyyMMddHHmmss")
}
if ([string]::IsNullOrWhiteSpace($BucketName)) {
    $BucketName = "tapne-{0}-media" -f $ProjectId
}
if ([string]::IsNullOrWhiteSpace($PrivateServiceRangeName)) {
    $networkLeaf = (($Network -split "/") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1)
    if ([string]::IsNullOrWhiteSpace($networkLeaf)) {
        $networkLeaf = $Network
    }
    $PrivateServiceRangeName = "google-managed-services-{0}" -f $networkLeaf
}

$serviceAccountEmail = "{0}@{1}.iam.gserviceaccount.com" -f $ServiceAccountName, $ProjectId
$imageRef = "{0}-docker.pkg.dev/{1}/{2}/{3}:{4}" -f $Region, $ProjectId, $Repository, $ImageName, $ImageTag
$bucketRef = "gs://{0}" -f $BucketName

$secretNames = @{
    SecretKey         = "tapne-secret-key"
    DatabaseUrl       = "tapne-database-url"
    DatabaseUrlCandidate = "tapne-database-url-candidate"
    RedisUrl          = "tapne-redis-url"
    CeleryBrokerUrl   = "tapne-celery-broker-url"
    CeleryResultStore = "tapne-celery-result-backend"
    GoogleMapsApiKey  = "tapne-google-maps-api-key"
}

$scriptDirectory = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path
$pushScriptPath = Join-Path $scriptDirectory "push-web-image-to-artifact.ps1"
$requirementsPath = Join-Path $repoRoot "requirements.txt"

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

function ConvertTo-BoolString {
    param([bool]$Value)
    if ($Value) { return "true" }
    return "false"
}

function Get-RedactedArguments {
    param([string[]]$Arguments)

    $source = @($Arguments)
    $masked = New-Object System.Collections.Generic.List[string]
    $i = 0
    while ($i -lt $source.Count) {
        $arg = [string]$source[$i]
        if ($arg -eq "--password") {
            [void]$masked.Add($arg)
            if (($i + 1) -lt $source.Count) {
                [void]$masked.Add("****")
                $i += 2
                continue
            }
            $i += 1
            continue
        }
        if ($arg.StartsWith("--password=")) {
            [void]$masked.Add("--password=****")
            $i += 1
            continue
        }
        [void]$masked.Add($arg)
        $i += 1
    }
    return @($masked)
}

function Split-CommaList {
    param([string[]]$Values)

    $items = New-Object System.Collections.Generic.List[string]
    foreach ($value in @($Values)) {
        if ([string]::IsNullOrWhiteSpace($value)) {
            continue
        }
        foreach ($token in ([string]$value -split ",")) {
            $item = $token.Trim()
            if ([string]::IsNullOrWhiteSpace($item)) {
                continue
            }
            if (-not $items.Contains($item)) {
                [void]$items.Add($item)
            }
        }
    }
    return @($items)
}

function ConvertTo-GcloudDictArg {
    param(
        [string[]]$Entries,
        [string]$Delimiter = ""
    )

    $normalizedEntries = @($Entries | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($normalizedEntries.Count -eq 0) {
        return ""
    }

    if ([string]::IsNullOrWhiteSpace($Delimiter)) {
        # Avoid shell metacharacters that can be interpreted by gcloud.cmd/cmd.exe on Windows.
        $candidateDelimiters = @("~", "#", "@", "!", ";", "+", "%", "_")
        foreach ($candidate in $candidateDelimiters) {
            $candidateUsed = $false
            foreach ($entry in $normalizedEntries) {
                if ($entry.Contains($candidate)) {
                    $candidateUsed = $true
                    break
                }
            }
            if (-not $candidateUsed) {
                $Delimiter = $candidate
                break
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($Delimiter)) {
        throw "Unable to choose a safe gcloud dictionary delimiter for provided entries."
    }

    foreach ($entry in $normalizedEntries) {
        if (-not $entry.Contains("=")) {
            throw ("Invalid gcloud key/value entry: {0}" -f $entry)
        }
        if ($entry.Contains($Delimiter)) {
            throw ("Entry contains unsupported delimiter '{0}': {1}" -f $Delimiter, $entry)
        }
    }

    $caretToken = "^"
    if ($IsWindows) {
        # gcloud.cmd is mediated by cmd.exe; each literal caret must be escaped.
        $caretToken = "^^^^"
    }

    return ("{0}{1}{0}{2}" -f $caretToken, $Delimiter, ($normalizedEntries -join $Delimiter))
}

function Resolve-HttpPath {
    param(
        [string]$PathValue,
        [string]$DefaultPath
    )

    $resolved = $PathValue
    if ([string]::IsNullOrWhiteSpace($resolved)) {
        $resolved = $DefaultPath
    }
    $resolved = $resolved.Trim()
    if ([string]::IsNullOrWhiteSpace($resolved)) {
        throw "HTTP path value cannot be empty."
    }
    if (-not $resolved.StartsWith("/")) {
        $resolved = "/" + $resolved
    }
    return $resolved
}

function Resolve-BaseUrl {
    param(
        [string]$Candidate,
        [string]$Fallback,
        [string]$ParameterName
    )

    $resolvedCandidate = $Candidate
    if ([string]::IsNullOrWhiteSpace($resolvedCandidate)) {
        $resolvedCandidate = $Fallback
    }
    $resolvedCandidate = $resolvedCandidate.Trim()

    try {
        $uri = [System.Uri]$resolvedCandidate
    }
    catch {
        throw ("{0} must be an absolute URL. Received: {1}" -f $ParameterName, $resolvedCandidate)
    }

    if (-not $uri.IsAbsoluteUri -or [string]::IsNullOrWhiteSpace($uri.Host)) {
        throw ("{0} must include scheme and host. Received: {1}" -f $ParameterName, $resolvedCandidate)
    }

    return $uri.GetLeftPart([System.UriPartial]::Authority).TrimEnd("/")
}

function Resolve-HostName {
    param(
        [string]$Candidate,
        [string]$FallbackHost,
        [string]$ParameterName
    )

    $resolved = $Candidate
    if ([string]::IsNullOrWhiteSpace($resolved)) {
        $resolved = $FallbackHost
    }
    $resolved = $resolved.Trim()
    if ([string]::IsNullOrWhiteSpace($resolved)) {
        throw ("{0} could not be resolved to a host value." -f $ParameterName)
    }

    if ($resolved.Contains("://")) {
        try {
            $uri = [System.Uri]$resolved
        }
        catch {
            throw ("{0} is not a valid URL/host value: {1}" -f $ParameterName, $resolved)
        }
        if ([string]::IsNullOrWhiteSpace($uri.Host)) {
            throw ("{0} is missing a host component: {1}" -f $ParameterName, $resolved)
        }
        return $uri.Host
    }

    if ($resolved.Contains("/")) {
        $resolved = ($resolved -split "/")[0].Trim()
    }
    if ([string]::IsNullOrWhiteSpace($resolved)) {
        throw ("{0} is missing a host component." -f $ParameterName)
    }
    return $resolved
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

    $logArguments = Get-RedactedArguments -Arguments $Arguments
    Write-Verbose ("Running: {0} {1}" -f $FilePath, ($logArguments -join " "))

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

function Get-CloudRunServiceEnvMap {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$Region,
        [string]$ServiceName
    )

    $describe = Invoke-External -FilePath $GcloudCli -Arguments @(
        "run", "services", "describe", $ServiceName,
        "--project", $Project,
        "--region", $Region,
        "--format=json"
    )
    if ($describe.ExitCode -ne 0) {
        return $null
    }

    $rawJson = ($describe.Output -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($rawJson)) {
        return @{}
    }

    try {
        $service = $rawJson | ConvertFrom-Json -Depth 100
    }
    catch {
        Write-Warning ("Failed to parse existing Cloud Run service JSON; host/csrf env values may not be preserved automatically. Details: {0}" -f $_.Exception.Message)
        return @{}
    }

    $envMap = @{}
    if ($null -eq $service -or $service.PSObject.Properties.Match("spec").Count -eq 0 -or $null -eq $service.spec) {
        return $envMap
    }
    if ($service.spec.PSObject.Properties.Match("template").Count -eq 0 -or $null -eq $service.spec.template) {
        return $envMap
    }
    if ($service.spec.template.PSObject.Properties.Match("spec").Count -eq 0 -or $null -eq $service.spec.template.spec) {
        return $envMap
    }
    if ($service.spec.template.spec.PSObject.Properties.Match("containers").Count -eq 0 -or $null -eq $service.spec.template.spec.containers) {
        return $envMap
    }

    $containers = @($service.spec.template.spec.containers)
    if ($containers.Count -eq 0) {
        return $envMap
    }

    $container = $containers[0]
    if ($null -eq $container -or $container.PSObject.Properties.Match("env").Count -eq 0 -or $null -eq $container.env) {
        return $envMap
    }

    foreach ($entry in @($container.env)) {
        if ($null -eq $entry) {
            continue
        }
        $name = ""
        $value = $null
        if ($entry.PSObject.Properties.Match("name").Count -gt 0) {
            $name = [string]$entry.name
        }
        if ($entry.PSObject.Properties.Match("value").Count -gt 0) {
            $value = [string]$entry.value
        }
        if (-not [string]::IsNullOrWhiteSpace($name) -and $null -ne $value) {
            $envMap[$name] = $value
        }
    }

    return $envMap
}

function Get-ResourceLeafName {
    param([string]$Reference)

    if ([string]::IsNullOrWhiteSpace($Reference)) {
        return ""
    }

    $trimmed = $Reference.Trim()
    if (-not $trimmed.Contains("/")) {
        return $trimmed
    }

    $segments = @($trimmed -split "/")
    for ($idx = $segments.Count - 1; $idx -ge 0; $idx--) {
        $segment = [string]$segments[$idx]
        if (-not [string]::IsNullOrWhiteSpace($segment)) {
            return $segment.Trim()
        }
    }

    return ""
}

function Get-CloudRunLoadBalancerDomains {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$Region,
        [string]$ServiceName
    )

    $domains = New-Object System.Collections.Generic.List[string]

    $negList = Invoke-External -FilePath $GcloudCli -Arguments @(
        "compute", "network-endpoint-groups", "list",
        "--project", $Project,
        "--regions", $Region,
        "--format=json"
    )
    if ($negList.ExitCode -ne 0) {
        Write-Warning "Failed listing network endpoint groups for custom domain inference."
        return @()
    }

    $negJson = ($negList.Output -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($negJson)) {
        return @()
    }

    try {
        $negs = @($negJson | ConvertFrom-Json -Depth 100)
    }
    catch {
        Write-Warning ("Failed parsing NEG list JSON for custom domain inference. Details: {0}" -f $_.Exception.Message)
        return @()
    }

    $negNames = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($neg in $negs) {
        if ($null -eq $neg) {
            continue
        }
        $negType = ""
        if ($neg.PSObject.Properties.Match("networkEndpointType").Count -gt 0) {
            $negType = [string]$neg.networkEndpointType
        }
        if ($negType -ne "SERVERLESS") {
            continue
        }

        $cloudRunService = ""
        if ($neg.PSObject.Properties.Match("cloudRun").Count -gt 0 -and $null -ne $neg.cloudRun) {
            if ($neg.cloudRun.PSObject.Properties.Match("service").Count -gt 0) {
                $cloudRunService = [string]$neg.cloudRun.service
            }
        }
        if ([string]::IsNullOrWhiteSpace($cloudRunService) -or $cloudRunService -ne $ServiceName) {
            continue
        }

        $negName = ""
        if ($neg.PSObject.Properties.Match("name").Count -gt 0) {
            $negName = [string]$neg.name
        }
        if (-not [string]::IsNullOrWhiteSpace($negName)) {
            [void]$negNames.Add($negName)
        }
    }

    if ($negNames.Count -eq 0) {
        return @()
    }

    $backendList = Invoke-External -FilePath $GcloudCli -Arguments @(
        "compute", "backend-services", "list",
        "--project", $Project,
        "--global",
        "--format=json"
    )
    if ($backendList.ExitCode -ne 0) {
        Write-Warning "Failed listing backend services for custom domain inference."
        return @()
    }

    $backendJson = ($backendList.Output -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($backendJson)) {
        return @()
    }

    try {
        $backendServices = @($backendJson | ConvertFrom-Json -Depth 100)
    }
    catch {
        Write-Warning ("Failed parsing backend service JSON for custom domain inference. Details: {0}" -f $_.Exception.Message)
        return @()
    }

    $backendNames = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($backendService in $backendServices) {
        if ($null -eq $backendService -or $backendService.PSObject.Properties.Match("backends").Count -eq 0 -or $null -eq $backendService.backends) {
            continue
        }

        $matchesNeg = $false
        foreach ($backend in @($backendService.backends)) {
            if ($null -eq $backend) {
                continue
            }
            $groupRef = ""
            if ($backend.PSObject.Properties.Match("group").Count -gt 0) {
                $groupRef = [string]$backend.group
            }
            if ([string]::IsNullOrWhiteSpace($groupRef)) {
                continue
            }
            $groupName = Get-ResourceLeafName -Reference $groupRef
            if ($negNames.Contains($groupName)) {
                $matchesNeg = $true
                break
            }
        }

        if (-not $matchesNeg) {
            continue
        }

        $backendName = ""
        if ($backendService.PSObject.Properties.Match("name").Count -gt 0) {
            $backendName = [string]$backendService.name
        }
        if (-not [string]::IsNullOrWhiteSpace($backendName)) {
            [void]$backendNames.Add($backendName)
        }
    }

    if ($backendNames.Count -eq 0) {
        return @()
    }

    $urlMapList = Invoke-External -FilePath $GcloudCli -Arguments @(
        "compute", "url-maps", "list",
        "--project", $Project,
        "--global",
        "--format=json"
    )
    if ($urlMapList.ExitCode -ne 0) {
        Write-Warning "Failed listing URL maps for custom domain inference."
        return @()
    }

    $urlMapJson = ($urlMapList.Output -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($urlMapJson)) {
        return @()
    }

    try {
        $urlMaps = @($urlMapJson | ConvertFrom-Json -Depth 100)
    }
    catch {
        Write-Warning ("Failed parsing URL map JSON for custom domain inference. Details: {0}" -f $_.Exception.Message)
        return @()
    }

    $urlMapNames = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($urlMap in $urlMaps) {
        if ($null -eq $urlMap) {
            continue
        }

        $urlMapText = ""
        try {
            $urlMapText = ($urlMap | ConvertTo-Json -Depth 100 -Compress)
        }
        catch {
            continue
        }
        if ([string]::IsNullOrWhiteSpace($urlMapText)) {
            continue
        }

        $matchesBackend = $false
        foreach ($backendName in $backendNames) {
            if ($urlMapText.Contains(("backendServices/{0}" -f $backendName))) {
                $matchesBackend = $true
                break
            }
        }
        if (-not $matchesBackend) {
            continue
        }

        $urlMapName = ""
        if ($urlMap.PSObject.Properties.Match("name").Count -gt 0) {
            $urlMapName = [string]$urlMap.name
        }
        if (-not [string]::IsNullOrWhiteSpace($urlMapName)) {
            [void]$urlMapNames.Add($urlMapName)
        }
    }

    if ($urlMapNames.Count -eq 0) {
        return @()
    }

    $httpsProxyList = Invoke-External -FilePath $GcloudCli -Arguments @(
        "compute", "target-https-proxies", "list",
        "--project", $Project,
        "--global",
        "--format=json"
    )
    if ($httpsProxyList.ExitCode -ne 0) {
        Write-Warning "Failed listing target HTTPS proxies for custom domain inference."
        return @()
    }

    $httpsProxyJson = ($httpsProxyList.Output -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($httpsProxyJson)) {
        return @()
    }

    try {
        $httpsProxies = @($httpsProxyJson | ConvertFrom-Json -Depth 100)
    }
    catch {
        Write-Warning ("Failed parsing target HTTPS proxy JSON for custom domain inference. Details: {0}" -f $_.Exception.Message)
        return @()
    }

    $certNames = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($httpsProxy in $httpsProxies) {
        if ($null -eq $httpsProxy) {
            continue
        }

        $urlMapRef = ""
        if ($httpsProxy.PSObject.Properties.Match("urlMap").Count -gt 0) {
            $urlMapRef = [string]$httpsProxy.urlMap
        }
        $urlMapName = Get-ResourceLeafName -Reference $urlMapRef
        if ([string]::IsNullOrWhiteSpace($urlMapName) -or -not $urlMapNames.Contains($urlMapName)) {
            continue
        }

        if ($httpsProxy.PSObject.Properties.Match("sslCertificates").Count -eq 0 -or $null -eq $httpsProxy.sslCertificates) {
            continue
        }
        foreach ($certificateRef in @($httpsProxy.sslCertificates)) {
            $certificateName = Get-ResourceLeafName -Reference ([string]$certificateRef)
            if (-not [string]::IsNullOrWhiteSpace($certificateName)) {
                [void]$certNames.Add($certificateName)
            }
        }
    }

    if ($certNames.Count -eq 0) {
        return @()
    }

    foreach ($certName in $certNames) {
        $certificateDescribe = Invoke-External -FilePath $GcloudCli -Arguments @(
            "compute", "ssl-certificates", "describe", $certName,
            "--project", $Project,
            "--format=json",
            "--global"
        )
        if ($certificateDescribe.ExitCode -ne 0) {
            continue
        }

        $certJson = ($certificateDescribe.Output -join [Environment]::NewLine).Trim()
        if ([string]::IsNullOrWhiteSpace($certJson)) {
            continue
        }

        try {
            $certificate = $certJson | ConvertFrom-Json -Depth 100
        }
        catch {
            continue
        }

        if ($null -eq $certificate -or $certificate.PSObject.Properties.Match("managed").Count -eq 0 -or $null -eq $certificate.managed) {
            continue
        }
        if ($certificate.managed.PSObject.Properties.Match("domains").Count -eq 0 -or $null -eq $certificate.managed.domains) {
            continue
        }

        foreach ($domain in @($certificate.managed.domains)) {
            $candidateDomain = ([string]$domain).Trim().TrimEnd(".").ToLowerInvariant()
            if ([string]::IsNullOrWhiteSpace($candidateDomain)) {
                continue
            }
            if ($candidateDomain.StartsWith("*.")) {
                continue
            }
            if (-not $domains.Contains($candidateDomain)) {
                [void]$domains.Add($candidateDomain)
            }
        }
    }

    return @($domains)
}

function Select-PreferredCustomDomain {
    param([string[]]$Domains)

    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($domain in @($Domains)) {
        $candidate = ([string]$domain).Trim().TrimEnd(".").ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }
        if ($candidate.StartsWith("*.")) {
            continue
        }
        if ($candidate.EndsWith(".run.app")) {
            continue
        }
        if (-not $candidates.Contains($candidate)) {
            [void]$candidates.Add($candidate)
        }
    }

    if ($candidates.Count -eq 0) {
        return ""
    }

    $ordered = @(
        $candidates |
            Sort-Object `
                @{ Expression = { if ([string]$_ -like "www.*") { 1 } else { 0 } } }, `
                @{ Expression = { ([string]$_ -split "\.").Count } }, `
                @{ Expression = { ([string]$_).Length } }, `
                @{ Expression = { [string]$_ } }
    )

    return [string]$ordered[0]
}

function Get-CloudSqlOperationId {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $null
    }

    if ($Text -match "operations/([A-Za-z0-9-]+)") {
        return [string]$Matches[1]
    }

    if ($Text -match "\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b") {
        return [string]$Matches[1]
    }

    return $null
}

function Wait-CloudSqlOperation {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$OperationId
    )

    $waitArgVariants = @(
        @("sql", "operations", "wait", $OperationId, "--project", $Project),
        @("sql", "operations", "wait", "--project", $Project, $OperationId),
        @("beta", "sql", "operations", "wait", $OperationId, "--project", $Project),
        @("beta", "sql", "operations", "wait", "--project", $Project, $OperationId)
    )

    $lastError = ""
    foreach ($waitArgs in $waitArgVariants) {
        $waitResult = Invoke-External -FilePath $GcloudCli -Arguments $waitArgs
        if ($waitResult.ExitCode -eq 0) {
            foreach ($line in $waitResult.Output) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Verbose $line
                }
            }
            return
        }

        $details = ($waitResult.Output -join [Environment]::NewLine).Trim()
        $lastError = $details

        $looksLikeCommandMismatch = (
            $details -match "Invalid choice" -or
            $details -match "is not a gcloud command" -or
            $details -match "unrecognized arguments" -or
            $details -match "Must be specified"
        )
        if ($looksLikeCommandMismatch) {
            continue
        }

        if ([string]::IsNullOrWhiteSpace($details)) {
            throw ("Cloud SQL operation {0} failed while waiting." -f $OperationId)
        }
        throw ("Cloud SQL operation {0} failed while waiting.`n{1}" -f $OperationId, $details)
    }

    if ([string]::IsNullOrWhiteSpace($lastError)) {
        throw ("Failed waiting for Cloud SQL operation {0}: no compatible wait command found." -f $OperationId)
    }
    throw ("Failed waiting for Cloud SQL operation {0}.`n{1}" -f $OperationId, $lastError)
}

function Invoke-RequiredWithCloudSqlWait {
    param(
        [string]$GcloudCli,
        [string[]]$Arguments,
        [string]$Project,
        [string]$FailureMessage
    )

    $result = Invoke-External -FilePath $GcloudCli -Arguments $Arguments
    if ($result.ExitCode -eq 0) {
        foreach ($line in $result.Output) {
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Verbose $line
            }
        }
        return
    }

    $details = ($result.Output -join [Environment]::NewLine).Trim()
    $isLongRunningTimeout = $details -match "taking longer than expected"
    if ($isLongRunningTimeout) {
        $operationId = Get-CloudSqlOperationId -Text $details
        if (-not [string]::IsNullOrWhiteSpace($operationId)) {
            Write-Info ("Cloud SQL operation is still running; waiting for completion (operation: {0})..." -f $operationId)
            Wait-CloudSqlOperation -GcloudCli $GcloudCli -Project $Project -OperationId $operationId
            return
        }
    }

    if ([string]::IsNullOrWhiteSpace($details)) {
        throw $FailureMessage
    }
    throw ("{0}`n{1}" -f $FailureMessage, $details)
}

function Remove-BucketIamBindingIfPresent {
    param(
        [string]$GcloudCli,
        [string]$BucketRef,
        [string]$Member,
        [string]$Role
    )

    $removeResult = Invoke-External -FilePath $GcloudCli -Arguments @(
        "storage", "buckets", "remove-iam-policy-binding", $BucketRef,
        "--member", $Member,
        "--role", $Role,
        "--quiet"
    )
    if ($removeResult.ExitCode -eq 0) {
        Write-Info ("Removed legacy IAM role from bucket: {0}" -f $Role)
        return
    }

    $details = ($removeResult.Output -join [Environment]::NewLine)
    if ($details -match "No matching binding" -or $details -match "not found") {
        return
    }
    Write-Warning ("Could not remove bucket IAM role '{0}'. Details: {1}" -f $Role, $details.Trim())
}

function Set-PrivateServiceConnection {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$Network,
        [string]$RangeName,
        [int]$PrefixLength
    )

    $rangeDescribe = Invoke-External -FilePath $GcloudCli -Arguments @(
        "compute", "addresses", "describe", $RangeName,
        "--project", $Project,
        "--global",
        "--format=value(name)"
    )
    if ($rangeDescribe.ExitCode -ne 0) {
        Invoke-Required -FilePath $GcloudCli -Arguments @(
            "compute", "addresses", "create", $RangeName,
            "--project", $Project,
            "--global",
            "--purpose=VPC_PEERING",
            "--prefix-length", $PrefixLength,
            "--network", $Network,
            "--quiet"
        ) -FailureMessage ("Failed creating private service range '{0}'." -f $RangeName)
        Write-Ok ("Created private service range: {0}" -f $RangeName)
    }
    else {
        Write-Ok ("Private service range already exists: {0}" -f $RangeName)
    }

    $peeringList = Invoke-Required -FilePath $GcloudCli -Arguments @(
        "services", "vpc-peerings", "list",
        "--project", $Project,
        "--network", $Network,
        "--service", "servicenetworking.googleapis.com",
        "--format=value(peering)"
    ) -FailureMessage "Failed listing service networking peerings." -PassThru

    $nonEmptyPeerings = @($peeringList | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $hasPeering = $nonEmptyPeerings.Count -gt 0
    if ($hasPeering) {
        Write-Ok "Private service connection already exists for servicenetworking.googleapis.com."
        return
    }

    $connectResult = Invoke-External -FilePath $GcloudCli -Arguments @(
        "services", "vpc-peerings", "connect",
        "--project", $Project,
        "--service", "servicenetworking.googleapis.com",
        "--network", $Network,
        "--ranges", $RangeName
    )
    if ($connectResult.ExitCode -eq 0) {
        foreach ($line in $connectResult.Output) {
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Verbose $line
            }
        }
        Write-Ok "Private service connection established."
        return
    }

    $connectDetails = ($connectResult.Output -join [Environment]::NewLine)
    if ($connectDetails -match "Cannot modify allocated ranges in CreateConnection" -or $connectDetails -match "already exists") {
        Invoke-Required -FilePath $GcloudCli -Arguments @(
            "services", "vpc-peerings", "update",
            "--project", $Project,
            "--service", "servicenetworking.googleapis.com",
            "--network", $Network,
            "--ranges", $RangeName
        ) -FailureMessage "Failed updating private service connection ranges."
        Write-Ok "Private service connection updated."
        return
    }

    throw ("Failed establishing private service connection.`n{0}" -f $connectDetails.Trim())
}

function Get-GcloudAccessToken {
    param([string]$GcloudCli)
    $result = Invoke-External -FilePath $GcloudCli -Arguments @("auth", "print-access-token")
    if ($result.ExitCode -ne 0) {
        $details = ($result.Output -join [Environment]::NewLine).Trim()
        if ([string]::IsNullOrWhiteSpace($details)) {
            throw "Failed obtaining gcloud access token."
        }
        throw ("Failed obtaining gcloud access token.`n{0}" -f $details)
    }

    $token = ($result.Output | Select-Object -First 1 | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "Failed obtaining gcloud access token: empty token returned."
    }
    return $token
}

function Invoke-GcpApiJson {
    param(
        [ValidateSet("GET", "POST", "DELETE", "PATCH")]
        [string]$Method,
        [string]$Uri,
        [string]$AccessToken,
        [object]$Body = $null
    )

    $headers = @{
        Authorization = "Bearer $AccessToken"
    }

    if ($Method -eq "GET" -or $Method -eq "DELETE") {
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers
    }

    $jsonBody = $null
    if ($null -ne $Body) {
        $jsonBody = ($Body | ConvertTo-Json -Depth 20)
    }
    return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -ContentType "application/json" -Body $jsonBody
}

function Get-GcpProjectNumber {
    param(
        [string]$GcloudCli,
        [string]$Project
    )

    $result = Invoke-External -FilePath $GcloudCli -Arguments @(
        "projects", "describe", $Project,
        "--format=value(projectNumber)"
    )
    if ($result.ExitCode -ne 0) {
        $details = ($result.Output -join [Environment]::NewLine).Trim()
        if ([string]::IsNullOrWhiteSpace($details)) {
            throw ("Failed resolving numeric project number for project '{0}'." -f $Project)
        }
        throw ("Failed resolving numeric project number for project '{0}'.`n{1}" -f $Project, $details)
    }

    $projectNumber = ($result.Output | Select-Object -First 1 | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($projectNumber)) {
        throw ("Failed resolving numeric project number for project '{0}': empty value returned." -f $Project)
    }

    return $projectNumber
}

function Find-ApiKeyByDisplayName {
    param(
        [string]$ProjectNumber,
        [string]$AccessToken,
        [string]$DisplayName
    )

    $baseUri = "https://apikeys.googleapis.com/v2/projects/{0}/locations/global/keys?pageSize=300" -f $ProjectNumber
    $uri = $baseUri
    while (-not [string]::IsNullOrWhiteSpace($uri)) {
        $response = Invoke-GcpApiJson -Method "GET" -Uri $uri -AccessToken $AccessToken
        $keys = @()
        if ($null -ne $response -and $response.PSObject.Properties.Match("keys").Count -gt 0) {
            $keys = @($response.keys)
        }
        foreach ($key in $keys) {
            if ([string]$key.displayName -eq $DisplayName) {
                return $key
            }
        }

        $nextToken = ""
        if ($null -ne $response -and $response.PSObject.Properties.Match("nextPageToken").Count -gt 0) {
            $nextToken = [string]$response.nextPageToken
        }
        if ([string]::IsNullOrWhiteSpace($nextToken)) {
            $uri = $null
        }
        else {
            $uri = "{0}&pageToken={1}" -f $baseUri, ([System.Uri]::EscapeDataString($nextToken))
        }
    }

    return $null
}

function Wait-GcpLongRunningOperation {
    param(
        [string]$AccessToken,
        [string]$OperationName,
        [int]$TimeoutSeconds = 420,
        [int]$SleepSeconds = 3
    )

    $operationPath = $OperationName.Trim()
    if ([string]::IsNullOrWhiteSpace($operationPath)) {
        throw "Cannot wait for an empty GCP operation name."
    }

    $operationUri = ""
    if ($operationPath.StartsWith("https://", [System.StringComparison]::OrdinalIgnoreCase)) {
        $operationUri = $operationPath
    }
    else {
        $operationUri = "https://apikeys.googleapis.com/v2/{0}" -f $operationPath.TrimStart("/")
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $operation = Invoke-GcpApiJson -Method "GET" -Uri $operationUri -AccessToken $AccessToken
        $isDone = $false
        if ($null -ne $operation -and $operation.PSObject.Properties.Match("done").Count -gt 0) {
            $isDone = [bool]$operation.done
        }

        if ($isDone) {
            if ($null -ne $operation -and $operation.PSObject.Properties.Match("error").Count -gt 0 -and $null -ne $operation.error) {
                $errorCode = ""
                if ($operation.error.PSObject.Properties.Match("code").Count -gt 0) {
                    $errorCode = [string]$operation.error.code
                }
                $errorMessage = ""
                if ($operation.error.PSObject.Properties.Match("message").Count -gt 0) {
                    $errorMessage = [string]$operation.error.message
                }
                if ([string]::IsNullOrWhiteSpace($errorMessage)) {
                    $errorMessage = "Operation returned an error."
                }
                if (-not [string]::IsNullOrWhiteSpace($errorCode)) {
                    throw ("GCP operation '{0}' failed (code {1}): {2}" -f $OperationName, $errorCode, $errorMessage)
                }
                throw ("GCP operation '{0}' failed: {1}" -f $OperationName, $errorMessage)
            }
            return $operation
        }

        Start-Sleep -Seconds $SleepSeconds
    }

    throw ("Timed out waiting for GCP operation '{0}' after {1} second(s)." -f $OperationName, $TimeoutSeconds)
}

function Get-ManagedGoogleMapsApiKey {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$AccessToken,
        [string]$DisplayName = "Tapne Places Server Key (managed)"
    )

    $projectNumber = Get-GcpProjectNumber -GcloudCli $GcloudCli -Project $Project
    $existingKey = Find-ApiKeyByDisplayName -ProjectNumber $projectNumber -AccessToken $AccessToken -DisplayName $DisplayName
    if ($null -eq $existingKey) {
        $createPayload = @{
            displayName  = $DisplayName
            restrictions = @{
                apiTargets = @(
                    @{ service = "places.googleapis.com" },
                    @{ service = "places-backend.googleapis.com" },
                    @{ service = "maps-backend.googleapis.com" }
                )
            }
        }
        $createOperation = Invoke-GcpApiJson -Method "POST" -Uri ("https://apikeys.googleapis.com/v2/projects/{0}/locations/global/keys" -f $projectNumber) -AccessToken $AccessToken -Body $createPayload
        $operationName = ""
        if ($null -ne $createOperation -and $createOperation.PSObject.Properties.Match("name").Count -gt 0) {
            $operationName = [string]$createOperation.name
        }
        if ([string]::IsNullOrWhiteSpace($operationName)) {
            throw "API Keys API did not return an operation name while creating the managed Google Maps key."
        }

        Write-Info ("Creating managed Google Maps API key '{0}'..." -f $DisplayName)
        $completedOperation = Wait-GcpLongRunningOperation -AccessToken $AccessToken -OperationName $operationName
        if ($null -ne $completedOperation -and $completedOperation.PSObject.Properties.Match("response").Count -gt 0) {
            $existingKey = $completedOperation.response
        }
        if ($null -eq $existingKey -or $existingKey.PSObject.Properties.Match("name").Count -eq 0 -or [string]::IsNullOrWhiteSpace([string]$existingKey.name)) {
            $existingKey = Find-ApiKeyByDisplayName -ProjectNumber $projectNumber -AccessToken $AccessToken -DisplayName $DisplayName
        }
        if ($null -eq $existingKey -or $existingKey.PSObject.Properties.Match("name").Count -eq 0 -or [string]::IsNullOrWhiteSpace([string]$existingKey.name)) {
            throw "Managed Google Maps API key creation completed, but the key resource could not be resolved."
        }
        Write-Ok ("Created managed Google Maps API key: {0}" -f [string]$existingKey.name)
    }
    else {
        Write-Info ("Reusing managed Google Maps API key: {0}" -f [string]$existingKey.name)
    }

    $keyName = [string]$existingKey.name
    $keyStringResponse = Invoke-GcpApiJson -Method "GET" -Uri ("https://apikeys.googleapis.com/v2/{0}/keyString" -f $keyName) -AccessToken $AccessToken
    $keyString = ""
    if ($null -ne $keyStringResponse -and $keyStringResponse.PSObject.Properties.Match("keyString").Count -gt 0) {
        $keyString = [string]$keyStringResponse.keyString
    }
    $keyString = $keyString.Trim()
    if ([string]::IsNullOrWhiteSpace($keyString)) {
        throw ("Managed Google Maps API key '{0}' was resolved, but getKeyString returned an empty value." -f $keyName)
    }

    return $keyString
}

function Find-UptimeCheckByDisplayName {
    param(
        [string]$Project,
        [string]$AccessToken,
        [string]$DisplayName
    )

    $baseUri = "https://monitoring.googleapis.com/v3/projects/{0}/uptimeCheckConfigs?pageSize=100" -f $Project
    $uri = $baseUri
    while (-not [string]::IsNullOrWhiteSpace($uri)) {
        $response = Invoke-GcpApiJson -Method "GET" -Uri $uri -AccessToken $AccessToken
        $uptimeConfigs = @()
        if ($null -ne $response -and $response.PSObject.Properties.Match("uptimeCheckConfigs").Count -gt 0) {
            $uptimeConfigs = @($response.uptimeCheckConfigs)
        }
        foreach ($cfg in $uptimeConfigs) {
            if ([string]$cfg.displayName -eq $DisplayName) {
                return $cfg
            }
        }
        $nextToken = ""
        if ($null -ne $response -and $response.PSObject.Properties.Match("nextPageToken").Count -gt 0) {
            $nextToken = [string]$response.nextPageToken
        }
        if ([string]::IsNullOrWhiteSpace($nextToken)) {
            $uri = $null
        }
        else {
            $uri = "{0}&pageToken={1}" -f $baseUri, ([System.Uri]::EscapeDataString($nextToken))
        }
    }
    return $null
}

function Set-UptimeCheck {
    param(
        [string]$Project,
        [string]$AccessToken,
        [string]$DisplayName,
        [string]$CheckHost,
        [string]$Path
    )

    $existing = Find-UptimeCheckByDisplayName -Project $Project -AccessToken $AccessToken -DisplayName $DisplayName
    $mustRecreate = $false
    if ($null -ne $existing) {
        $existingHost = [string]($existing.monitoredResource.labels.host)
        $existingPath = [string]($existing.httpCheck.path)
        if ($existingHost -eq $CheckHost -and $existingPath -eq $Path) {
            Write-Ok ("Uptime check already configured: {0}" -f $DisplayName)
            return [string]$existing.name
        }
        $mustRecreate = $true
    }

    if ($mustRecreate) {
        Invoke-GcpApiJson -Method "DELETE" -Uri ("https://monitoring.googleapis.com/v3/{0}" -f [string]$existing.name) -AccessToken $AccessToken | Out-Null
        Write-Info ("Recreating uptime check due to config drift: {0}" -f $DisplayName)
    }

    $payload = @{
        displayName       = $DisplayName
        period            = "60s"
        timeout           = "10s"
        selectedRegions   = @("USA", "ASIA_PACIFIC", "EUROPE")
        monitoredResource = @{
            type   = "uptime_url"
            labels = @{
                project_id = $Project
                host       = $CheckHost
            }
        }
        httpCheck         = @{
            requestMethod = "GET"
            useSsl        = $true
            validateSsl   = $true
            path          = $Path
            port          = 443
        }
    }

    $created = Invoke-GcpApiJson -Method "POST" -Uri ("https://monitoring.googleapis.com/v3/projects/{0}/uptimeCheckConfigs" -f $Project) -AccessToken $AccessToken -Body $payload
    Write-Ok ("Configured uptime check: {0}" -f $DisplayName)
    return [string]$created.name
}

function Find-AlertPolicyByDisplayName {
    param(
        [string]$Project,
        [string]$AccessToken,
        [string]$DisplayName
    )

    $baseUri = "https://monitoring.googleapis.com/v3/projects/{0}/alertPolicies?pageSize=100" -f $Project
    $uri = $baseUri
    while (-not [string]::IsNullOrWhiteSpace($uri)) {
        $response = Invoke-GcpApiJson -Method "GET" -Uri $uri -AccessToken $AccessToken
        $alertPolicies = @()
        if ($null -ne $response -and $response.PSObject.Properties.Match("alertPolicies").Count -gt 0) {
            $alertPolicies = @($response.alertPolicies)
        }
        foreach ($policy in $alertPolicies) {
            if ([string]$policy.displayName -eq $DisplayName) {
                return $policy
            }
        }
        $nextToken = ""
        if ($null -ne $response -and $response.PSObject.Properties.Match("nextPageToken").Count -gt 0) {
            $nextToken = [string]$response.nextPageToken
        }
        if ([string]::IsNullOrWhiteSpace($nextToken)) {
            $uri = $null
        }
        else {
            $uri = "{0}&pageToken={1}" -f $baseUri, ([System.Uri]::EscapeDataString($nextToken))
        }
    }
    return $null
}

function Set-UptimeAlertPolicy {
    param(
        [string]$Project,
        [string]$AccessToken,
        [string]$DisplayName,
        [string]$UptimeCheckName,
        [string[]]$NotificationChannels
    )

    if ((@($NotificationChannels)).Count -eq 0) {
        Write-Info "Skipping alert policy creation because no monitoring notification channels were provided."
        return
    }

    $checkId = (($UptimeCheckName -split "/") | Select-Object -Last 1)
    if ([string]::IsNullOrWhiteSpace($checkId)) {
        Write-Warning "Cannot configure alert policy: uptime check ID is empty."
        return
    }

    $existing = Find-AlertPolicyByDisplayName -Project $Project -AccessToken $AccessToken -DisplayName $DisplayName
    if ($null -ne $existing) {
        Invoke-GcpApiJson -Method "DELETE" -Uri ("https://monitoring.googleapis.com/v3/{0}" -f [string]$existing.name) -AccessToken $AccessToken | Out-Null
        Write-Info ("Recreating alert policy due to config drift: {0}" -f $DisplayName)
    }

    $filter = "metric.type=`"monitoring.googleapis.com/uptime_check/check_passed`" AND resource.type=`"uptime_url`" AND metric.label.`"check_id`"=`"$checkId`""
    $payload = @{
        displayName          = $DisplayName
        combiner             = "OR"
        enabled              = $true
        notificationChannels = $NotificationChannels
        alertStrategy        = @{
            autoClose = "1800s"
        }
        conditions           = @(
            @{
                displayName        = "Uptime check failing"
                conditionThreshold = @{
                    filter          = $filter
                    comparison      = "COMPARISON_LT"
                    thresholdValue  = 1
                    duration        = "120s"
                    trigger         = @{ count = 1 }
                    aggregations    = @(
                        @{
                            alignmentPeriod  = "120s"
                            perSeriesAligner = "ALIGN_NEXT_OLDER"
                        }
                    )
                }
            }
        )
    }
    Invoke-GcpApiJson -Method "POST" -Uri ("https://monitoring.googleapis.com/v3/projects/{0}/alertPolicies" -f $Project) -AccessToken $AccessToken -Body $payload | Out-Null
    Write-Ok ("Configured alert policy: {0}" -f $DisplayName)
}

function New-RandomToken {
    param([int]$Length = 32)

    $alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    $bytes = New-Object byte[] $Length
    $builder = New-Object System.Text.StringBuilder
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        foreach ($byte in $bytes) {
            [void]$builder.Append($alphabet[$byte % $alphabet.Length])
        }
    }
    finally {
        $rng.Dispose()
    }
    return $builder.ToString()
}

function Get-SecretLatestValue {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$SecretName
    )

    $result = Invoke-External -FilePath $GcloudCli -Arguments @(
        "secrets", "versions", "access", "latest",
        "--secret", $SecretName,
        "--project", $Project
    )
    if ($result.ExitCode -ne 0) {
        return $null
    }
    return ($result.Output -join [Environment]::NewLine).TrimEnd("`r", "`n")
}

function Set-SecretValue {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$SecretName,
        [string]$SecretValue
    )

    $describe = Invoke-External -FilePath $GcloudCli -Arguments @("secrets", "describe", $SecretName, "--project", $Project)
    $currentValue = Get-SecretLatestValue -GcloudCli $GcloudCli -Project $Project -SecretName $SecretName
    if ($null -ne $currentValue -and $currentValue -eq $SecretValue) {
        Write-Info ("Secret unchanged, skipping new version: {0}" -f $SecretName)
        return
    }

    $tmp = New-TemporaryFile
    try {
        Set-Content -Path $tmp.FullName -Value $SecretValue -Encoding utf8NoBOM -NoNewline
        if ($describe.ExitCode -eq 0) {
            Invoke-Required -FilePath $GcloudCli -Arguments @(
                "secrets", "versions", "add", $SecretName,
                "--project", $Project,
                "--data-file", $tmp.FullName
            ) -FailureMessage ("Failed adding secret version: {0}" -f $SecretName)
            Write-Ok ("Updated secret: {0}" -f $SecretName)
        }
        else {
            Invoke-Required -FilePath $GcloudCli -Arguments @(
                "secrets", "create", $SecretName,
                "--project", $Project,
                "--replication-policy=automatic",
                "--data-file", $tmp.FullName
            ) -FailureMessage ("Failed creating secret: {0}" -f $SecretName)
            Write-Ok ("Created secret: {0}" -f $SecretName)
        }
    }
    finally {
        Remove-Item -Path $tmp.FullName -Force -ErrorAction SilentlyContinue
    }
}

function Get-CloudSqlConnectionNameFromDatabaseUrl {
    param([string]$DatabaseUrl)

    if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
        return ""
    }

    if ($DatabaseUrl -match '[?&]host=/cloudsql/(?<connection>[^&]+)') {
        return [System.Uri]::UnescapeDataString([string]$Matches["connection"])
    }

    return ""
}

function Get-CloudSqlInstanceNameFromConnectionName {
    param([string]$ConnectionName)

    if ([string]::IsNullOrWhiteSpace($ConnectionName)) {
        return ""
    }

    $segments = @($ConnectionName.Trim() -split ":")
    if ($segments.Count -lt 3) {
        return ""
    }

    return [string]$segments[-1]
}

function Get-CloudSqlDiskTypeName {
    param([string]$StorageType)

    $normalizedStorageType = ""
    if ($null -ne $StorageType) {
        $normalizedStorageType = $StorageType.Trim().ToUpperInvariant()
    }

    switch ($normalizedStorageType) {
        "HDD" { return "PD_HDD" }
        default { return "PD_SSD" }
    }
}

function Get-CloudSqlSafeNameComponent {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    $normalized = $Value.Trim().ToLowerInvariant()
    $normalized = $normalized -replace '^db-', ''
    $normalized = $normalized -replace '[^a-z0-9]+', '-'
    $normalized = $normalized.Trim('-')
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return "instance"
    }
    return $normalized
}

function Get-DesiredCloudSqlReplacementInstanceName {
    param(
        [string]$BaseInstanceName,
        [string]$Tier,
        [string]$StorageType,
        [int]$StorageGb,
        [string]$ExplicitReplacementInstance
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitReplacementInstance)) {
        return $ExplicitReplacementInstance.Trim()
    }

    $tierToken = Get-CloudSqlSafeNameComponent -Value $Tier
    $storageToken = Get-CloudSqlSafeNameComponent -Value ("{0}{1}" -f $StorageType, $StorageGb)
    $candidate = ("{0}-{1}-{2}" -f $BaseInstanceName.Trim(), $tierToken, $storageToken).ToLowerInvariant()
    $candidate = $candidate -replace '[^a-z0-9-]+', '-'
    $candidate = $candidate.Trim('-')
    if ($candidate.Length -gt 98) {
        $candidate = $candidate.Substring(0, 98).TrimEnd('-')
    }
    return $candidate
}

function Get-CloudSqlInstanceInfo {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$InstanceName
    )

    if ([string]::IsNullOrWhiteSpace($InstanceName)) {
        return $null
    }

    $describe = Invoke-External -FilePath $GcloudCli -Arguments @(
        "sql", "instances", "describe", $InstanceName,
        "--project", $Project,
        "--format=json"
    )
    if ($describe.ExitCode -ne 0) {
        return $null
    }

    $rawJson = ($describe.Output -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($rawJson)) {
        return $null
    }

    try {
        $instance = $rawJson | ConvertFrom-Json -Depth 100
    }
    catch {
        throw ("Failed parsing Cloud SQL instance JSON for '{0}': {1}" -f $InstanceName, $_.Exception.Message)
    }

    $storageSize = 0
    $storageSizeText = ""
    if ($null -ne $instance.settings -and $null -ne $instance.settings.dataDiskSizeGb) {
        $storageSizeText = [string]$instance.settings.dataDiskSizeGb
        [void][int]::TryParse($storageSizeText, [ref]$storageSize)
    }

    return [pscustomobject]@{
        Name                       = [string]$instance.name
        Tier                       = [string]$instance.settings.tier
        StorageSizeGb              = $storageSize
        StorageType                = [string]$instance.settings.dataDiskType
        PrivateNetwork             = [string]$instance.settings.ipConfiguration.privateNetwork
        Ipv4Enabled                = [bool]$instance.settings.ipConfiguration.ipv4Enabled
        BackupEnabled              = [bool]$instance.settings.backupConfiguration.enabled
        BackupStartTime            = [string]$instance.settings.backupConfiguration.startTime
        PointInTimeRecoveryEnabled = [bool]$instance.settings.backupConfiguration.pointInTimeRecoveryEnabled
        ConnectionName             = [string]$instance.connectionName
        ServiceAccountEmailAddress = [string]$instance.serviceAccountEmailAddress
        Region                     = [string]$instance.region
        DatabaseVersion            = [string]$instance.databaseVersion
    }
}

function Set-CloudSqlInstance {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$Region,
        [string]$InstanceName,
        [string]$DatabaseVersion,
        [string]$Tier,
        [int]$StorageGb,
        [string]$StorageType,
        [bool]$UsePrivateIp,
        [string]$Network,
        [bool]$EnableBackups,
        [string]$BackupStartTime,
        [bool]$EnablePointInTimeRecovery
    )

    $instanceInfo = Get-CloudSqlInstanceInfo -GcloudCli $GcloudCli -Project $Project -InstanceName $InstanceName
    $wasCreated = $false

    if ($null -eq $instanceInfo) {
        $sqlCreateArgs = @(
            "sql", "instances", "create", $InstanceName,
            "--project", $Project,
            "--region", $Region,
            "--database-version", $DatabaseVersion,
            "--tier", $Tier,
            "--storage-size", $StorageGb,
            "--storage-type", $StorageType,
            "--storage-auto-increase"
        )
        if ($UsePrivateIp) {
            $sqlCreateArgs += @(
                "--network", $Network,
                "--no-assign-ip"
            )
        }
        else {
            $sqlCreateArgs += "--assign-ip"
        }
        if ($EnableBackups) {
            $sqlCreateArgs += @("--backup-start-time", $BackupStartTime)
        }
        else {
            $sqlCreateArgs += "--no-backup"
        }
        if ($EnablePointInTimeRecovery) {
            $sqlCreateArgs += "--enable-point-in-time-recovery"
        }
        $sqlCreateArgs += "--quiet"

        Invoke-RequiredWithCloudSqlWait -GcloudCli $GcloudCli -Arguments $sqlCreateArgs -Project $Project -FailureMessage ("Failed creating Cloud SQL instance '{0}'." -f $InstanceName)
        Write-Ok ("Created Cloud SQL instance: {0}" -f $InstanceName)
        $wasCreated = $true
        $instanceInfo = Get-CloudSqlInstanceInfo -GcloudCli $GcloudCli -Project $Project -InstanceName $InstanceName
        if ($null -eq $instanceInfo) {
            throw ("Cloud SQL instance '{0}' could not be described after creation." -f $InstanceName)
        }
    }
    else {
        Write-Ok ("Cloud SQL instance already exists: {0}" -f $InstanceName)
        $expectedDiskType = Get-CloudSqlDiskTypeName -StorageType $StorageType
        $needsPatch = $false
        $sqlPatchArgs = @(
            "sql", "instances", "patch", $InstanceName,
            "--project", $Project
        )

        if ($instanceInfo.Tier -ne $Tier) {
            $sqlPatchArgs += @("--tier", $Tier)
            $needsPatch = $true
        }
        if ($instanceInfo.StorageSizeGb -lt $StorageGb) {
            $sqlPatchArgs += @("--storage-size", $StorageGb)
            $needsPatch = $true
        }
        elseif ($instanceInfo.StorageSizeGb -gt $StorageGb) {
            Write-Info ("Cloud SQL storage is {0} GB but requested minimum is {1} GB. Cloud SQL doesn't support shrinking storage in place, so the existing disk size will be kept." -f $instanceInfo.StorageSizeGb, $StorageGb)
        }
        if (-not [string]::IsNullOrWhiteSpace($instanceInfo.StorageType) -and $instanceInfo.StorageType -ne $expectedDiskType) {
            Write-Info ("Cloud SQL storage type is {0}. Existing storage type will be kept because in-place disk-type migration isn't handled by this deploy script." -f $instanceInfo.StorageType)
        }

        if ($UsePrivateIp) {
            if ([string]::IsNullOrWhiteSpace($instanceInfo.PrivateNetwork) -or $instanceInfo.Ipv4Enabled) {
                $sqlPatchArgs += @(
                    "--network", $Network,
                    "--no-assign-ip"
                )
                $needsPatch = $true
            }
        }
        elseif (-not $instanceInfo.Ipv4Enabled) {
            $sqlPatchArgs += "--assign-ip"
            $needsPatch = $true
        }

        if ($EnableBackups) {
            if (-not $instanceInfo.BackupEnabled -or $instanceInfo.BackupStartTime -ne $BackupStartTime) {
                $sqlPatchArgs += @("--backup-start-time", $BackupStartTime)
                $needsPatch = $true
            }
        }
        elseif ($instanceInfo.BackupEnabled) {
            $sqlPatchArgs += "--no-backup"
            $needsPatch = $true
        }

        if ($EnablePointInTimeRecovery -and -not $instanceInfo.PointInTimeRecoveryEnabled) {
            $sqlPatchArgs += "--enable-point-in-time-recovery"
            $needsPatch = $true
        }

        if ($needsPatch) {
            $sqlPatchArgs += "--quiet"
            Invoke-RequiredWithCloudSqlWait -GcloudCli $GcloudCli -Arguments $sqlPatchArgs -Project $Project -FailureMessage ("Failed patching Cloud SQL instance '{0}'." -f $InstanceName)
            Write-Ok ("Cloud SQL settings ensured for instance: {0}" -f $InstanceName)
            $instanceInfo = Get-CloudSqlInstanceInfo -GcloudCli $GcloudCli -Project $Project -InstanceName $InstanceName
        }
        else {
            Write-Ok ("Cloud SQL settings already match desired state for instance: {0}" -f $InstanceName)
        }
    }

    return [pscustomobject]@{
        Info    = $instanceInfo
        Created = $wasCreated
    }
}

function Set-CloudSqlDatabaseAndUser {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$InstanceName,
        [string]$DatabaseName,
        [string]$UserName,
        [securestring]$Password
    )

    $passwordBstr = [IntPtr]::Zero
    $passwordPlainText = ""
    try {
        if ($null -ne $Password) {
            $passwordBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
            $passwordPlainText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordBstr)
        }

        $dbList = Invoke-Required -FilePath $GcloudCli -Arguments @(
            "sql", "databases", "list",
            "--instance", $InstanceName,
            "--project", $Project,
            "--format=value(name)"
        ) -FailureMessage ("Failed listing Cloud SQL databases for instance '{0}'." -f $InstanceName) -PassThru

        if ($dbList -contains $DatabaseName) {
            Write-Ok ("Database already exists: {0}" -f $DatabaseName)
        }
        else {
            Invoke-Required -FilePath $GcloudCli -Arguments @(
                "sql", "databases", "create", $DatabaseName,
                "--instance", $InstanceName,
                "--project", $Project,
                "--quiet"
            ) -FailureMessage ("Failed creating Cloud SQL database '{0}' on instance '{1}'." -f $DatabaseName, $InstanceName)
            Write-Ok ("Created database: {0}" -f $DatabaseName)
        }

        $userList = Invoke-Required -FilePath $GcloudCli -Arguments @(
            "sql", "users", "list",
            "--instance", $InstanceName,
            "--project", $Project,
            "--format=value(name)"
        ) -FailureMessage ("Failed listing Cloud SQL users for instance '{0}'." -f $InstanceName) -PassThru

        if ($userList -contains $UserName) {
            Invoke-Required -FilePath $GcloudCli -Arguments @(
                "sql", "users", "set-password", $UserName,
                "--instance", $InstanceName,
                "--project", $Project,
                "--password", $passwordPlainText,
                "--quiet"
            ) -FailureMessage ("Failed setting password for user '{0}' on instance '{1}'." -f $UserName, $InstanceName)
            Write-Ok ("Updated password for DB user: {0}" -f $UserName)
        }
        else {
            Invoke-Required -FilePath $GcloudCli -Arguments @(
                "sql", "users", "create", $UserName,
                "--instance", $InstanceName,
                "--project", $Project,
                "--password", $passwordPlainText,
                "--quiet"
            ) -FailureMessage ("Failed creating DB user '{0}' on instance '{1}'." -f $UserName, $InstanceName)
            Write-Ok ("Created DB user: {0}" -f $UserName)
        }
    }
    finally {
        if ($passwordBstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordBstr)
        }
    }
}

function Add-BucketIamBinding {
    param(
        [string]$GcloudCli,
        [string]$BucketRef,
        [string]$Member,
        [string]$Role
    )

    Invoke-Required -FilePath $GcloudCli -Arguments @(
        "storage", "buckets", "add-iam-policy-binding", $BucketRef,
        "--member", $Member,
        "--role", $Role,
        "--quiet"
    ) -FailureMessage ("Failed binding {0} on bucket {1}." -f $Role, $BucketRef)
}

function Grant-CloudSqlBucketAccess {
    param(
        [string]$GcloudCli,
        [string]$BucketRef,
        [string]$ServiceAccountEmail
    )

    if ([string]::IsNullOrWhiteSpace($ServiceAccountEmail)) {
        throw "Cloud SQL service account email is required for import/export bucket access."
    }

    Add-BucketIamBinding -GcloudCli $GcloudCli -BucketRef $BucketRef -Member ("serviceAccount:{0}" -f $ServiceAccountEmail) -Role "roles/storage.objectAdmin"
    Write-Ok ("Bucket access ensured for Cloud SQL service account: {0}" -f $ServiceAccountEmail)
}

function Export-CloudSqlDatabase {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$InstanceName,
        [string]$DatabaseName,
        [string]$DestinationUri
    )

    Invoke-RequiredWithCloudSqlWait -GcloudCli $GcloudCli -Arguments @(
        "sql", "export", "sql", $InstanceName, $DestinationUri,
        "--project", $Project,
        "--database", $DatabaseName,
        "--offload",
        "--quiet"
    ) -Project $Project -FailureMessage ("Failed exporting Cloud SQL database '{0}' from instance '{1}'." -f $DatabaseName, $InstanceName)
}

function Import-CloudSqlDatabase {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$InstanceName,
        [string]$DatabaseName,
        [string]$UserName,
        [string]$SourceUri
    )

    Invoke-RequiredWithCloudSqlWait -GcloudCli $GcloudCli -Arguments @(
        "sql", "import", "sql", $InstanceName, $SourceUri,
        "--project", $Project,
        "--database", $DatabaseName,
        "--user", $UserName,
        "--quiet"
    ) -Project $Project -FailureMessage ("Failed importing Cloud SQL database '{0}' into instance '{1}'." -f $DatabaseName, $InstanceName)
}

function Remove-CloudSqlInstance {
    param(
        [string]$GcloudCli,
        [string]$Project,
        [string]$InstanceName
    )

    if ([string]::IsNullOrWhiteSpace($InstanceName)) {
        return $false
    }

    $instanceInfo = Get-CloudSqlInstanceInfo -GcloudCli $GcloudCli -Project $Project -InstanceName $InstanceName
    if ($null -eq $instanceInfo) {
        Write-Info ("Cloud SQL instance already absent, skipping delete: {0}" -f $InstanceName)
        return $false
    }

    Invoke-RequiredWithCloudSqlWait -GcloudCli $GcloudCli -Arguments @(
        "sql", "instances", "delete", $InstanceName,
        "--project", $Project,
        "--quiet"
    ) -Project $Project -FailureMessage ("Failed deleting Cloud SQL instance '{0}'." -f $InstanceName)

    Write-Ok ("Deleted Cloud SQL instance: {0}" -f $InstanceName)
    return $true
}

function Get-RedisInstanceReferences {
    param(
        [string]$GcloudCli,
        [string]$Project
    )

    $regionsResult = Invoke-Required -FilePath $GcloudCli -Arguments @(
        "redis", "regions", "list",
        "--project", $Project,
        "--format=value(name)"
    ) -FailureMessage "Failed listing Redis regions." -PassThru

    $regionRefs = @($regionsResult | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($regionRefs.Count -eq 0) {
        return @()
    }

    $references = New-Object System.Collections.Generic.List[object]
    foreach ($regionRef in $regionRefs) {
        $fullRegionRef = ([string]$regionRef).Trim()
        if ([string]::IsNullOrWhiteSpace($fullRegionRef)) {
            continue
        }

        $regionSegments = @($fullRegionRef -split "/")
        $regionName = [string]($regionSegments | Select-Object -Last 1)
        if ([string]::IsNullOrWhiteSpace($regionName)) {
            continue
        }

        $listResult = Invoke-Required -FilePath $GcloudCli -Arguments @(
            "redis", "instances", "list",
            "--project", $Project,
            "--region", $regionName,
            "--format=json(name,state)"
        ) -FailureMessage ("Failed listing Redis instances in region {0}." -f $regionName) -PassThru

        $rawJson = ($listResult -join [Environment]::NewLine).Trim()
        if ([string]::IsNullOrWhiteSpace($rawJson) -or $rawJson -eq "[]") {
            continue
        }

        try {
            $instances = @($rawJson | ConvertFrom-Json -Depth 20)
        }
        catch {
            throw ("Failed parsing Redis instance list JSON for region {0}: {1}" -f $regionName, $_.Exception.Message)
        }

        foreach ($instance in @($instances)) {
            $fullName = ""
            if ($null -ne $instance -and $null -ne $instance.name) {
                $fullName = [string]$instance.name
            }
            $fullName = $fullName.Trim()
            if ([string]::IsNullOrWhiteSpace($fullName)) {
                continue
            }

            $segments = @($fullName -split "/")
            if ($segments.Count -lt 6) {
                continue
            }

            $instanceRegion = [string]$segments[3]
            $instanceName = [string]$segments[5]
            $instanceState = ""
            if ($null -ne $instance -and $null -ne $instance.state) {
                $instanceState = [string]$instance.state
            }

            if ([string]::IsNullOrWhiteSpace($instanceRegion) -or [string]::IsNullOrWhiteSpace($instanceName)) {
                continue
            }

            [void]$references.Add([pscustomobject]@{
                Name     = $instanceName
                Region   = $instanceRegion
                State    = $instanceState.Trim()
                FullName = $fullName
            })
        }
    }

    return $references.ToArray()
}

function Wait-ForState {
    param(
        [scriptblock]$ReadState,
        [string]$Expected,
        [string]$Label,
        [int]$TimeoutSeconds = 900,
        [int]$SleepSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $state = [string](& $ReadState)
        Write-Verbose ("{0} state: {1}" -f $Label, $state)
        if ($state -eq $Expected) {
            Write-Ok ("{0} is {1}" -f $Label, $Expected)
            return
        }
        Start-Sleep -Seconds $SleepSeconds
    }

    throw ("Timed out waiting for {0} to become {1}." -f $Label, $Expected)
}

function Add-RequirementLine {
    param(
        [string]$FilePath,
        [string]$RequiredLine,
        [bool]$AutoFix
    )

    if (-not (Test-Path -Path $FilePath -PathType Leaf)) {
        throw ("Missing requirements file: {0}" -f $FilePath)
    }

    $raw = Get-Content -Path $FilePath -Raw
    $escaped = [regex]::Escape($RequiredLine)
    if ($raw -match "(?m)^$escaped\s*$") {
        Write-Ok ("Dependency is present: {0}" -f $RequiredLine)
        return
    }

    if (-not $AutoFix) {
        throw ("Missing required dependency '{0}'. Add it to requirements.txt and rerun, or set -AutoFixGcsDependency `$true." -f $RequiredLine)
    }

    Add-Content -Path $FilePath -Value $RequiredLine
    Write-Ok ("Added dependency to requirements.txt: {0}" -f $RequiredLine)
}
$gcloudCli = "gcloud"
$gcloudCmdCandidate = Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue
if ($null -ne $gcloudCmdCandidate) {
    $gcloudCli = $gcloudCmdCandidate.Source
}

Write-Verbose (
    "Run options => ProjectId={0}; Region={1}; ServiceName={2}; ImageTag={3}; BucketName={4}; BuildAndPushImage={5}; DisableBuildAttestations={6}; DisableContainerVulnerabilityScanning={7}; SkipMigrations={8}; RunBootstrapRuntime={9}; SkipSmokeTest={10}; PrivateCloudSqlIp={11}; CloudRunConcurrency={12}; CloudRunIngress={13}; GcsSignedUrls={14}; ConfigureMonitoring={15}; EnableRedis={16}; DjangoAllowedHosts={17}; CsrfTrustedOrigins={18}; CanonicalHost={19}; SmokeBaseUrl={20}; UptimeCheckHost={21}; UptimeCheckPath={22}" -f
    $ProjectId, $Region, $ServiceName, $ImageTag, $BucketName, $BuildAndPushImage, $DisableBuildAttestations, $DisableContainerVulnerabilityScanning, $SkipMigrations, $RunBootstrapRuntime, $SkipSmokeTest, $UsePrivateCloudSqlIp, $CloudRunConcurrency, $CloudRunIngress, $EnableGcsSignedUrls, $ConfigureMonitoring, $EnableRedis, ($DjangoAllowedHosts -join ","), ($CsrfTrustedOrigins -join ","), $CanonicalHost, $SmokeBaseUrl, $UptimeCheckHost, $UptimeCheckPath
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

Invoke-Required -FilePath $gcloudCli -Arguments @("config", "set", "project", $ProjectId) -FailureMessage ("Failed to set gcloud project to '{0}'." -f $ProjectId)
Invoke-Required -FilePath $gcloudCli -Arguments @("config", "set", "run/region", $Region) -FailureMessage ("Failed to set gcloud run/region to '{0}'." -f $Region)
Write-Ok ("gcloud project/region configured: {0}/{1}" -f $ProjectId, $Region)

if ($ValidateOnly) {
    Write-Host ""
    Write-Ok "Validate-only mode complete. Preflight checks passed; no cloud resources were changed."
    return
}

Write-Step "Ensuring required APIs are enabled"
Invoke-Required -FilePath $gcloudCli -Arguments @(
    "services", "enable",
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "redis.googleapis.com",
    "vpcaccess.googleapis.com",
    "compute.googleapis.com",
    "artifactregistry.googleapis.com",
    "servicenetworking.googleapis.com",
    "iamcredentials.googleapis.com",
    "monitoring.googleapis.com",
    "apikeys.googleapis.com",
    "maps-backend.googleapis.com",
    "places-backend.googleapis.com",
    "places.googleapis.com",
    "--project", $ProjectId
) -FailureMessage "Failed enabling one or more required APIs."
Write-Ok "Required APIs are enabled."

Write-Step "Ensuring runtime service account and project IAM bindings"
$saDescribe = Invoke-External -FilePath $gcloudCli -Arguments @(
    "iam", "service-accounts", "describe", $serviceAccountEmail,
    "--project", $ProjectId
)
if ($saDescribe.ExitCode -ne 0) {
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "iam", "service-accounts", "create", $ServiceAccountName,
        "--project", $ProjectId,
        "--display-name", "Tapne Cloud Run runtime"
    ) -FailureMessage "Failed to create runtime service account."
    Write-Ok ("Created service account: {0}" -f $serviceAccountEmail)
}
else {
    Write-Ok ("Service account already exists: {0}" -f $serviceAccountEmail)
}

Invoke-Required -FilePath $gcloudCli -Arguments @(
    "projects", "add-iam-policy-binding", $ProjectId,
    "--member", ("serviceAccount:{0}" -f $serviceAccountEmail),
    "--role", "roles/cloudsql.client",
    "--quiet"
) -FailureMessage "Failed to bind roles/cloudsql.client."

Invoke-Required -FilePath $gcloudCli -Arguments @(
    "projects", "add-iam-policy-binding", $ProjectId,
    "--member", ("serviceAccount:{0}" -f $serviceAccountEmail),
    "--role", "roles/secretmanager.secretAccessor",
    "--quiet"
) -FailureMessage "Failed to bind roles/secretmanager.secretAccessor."

Invoke-Required -FilePath $gcloudCli -Arguments @(
    "iam", "service-accounts", "add-iam-policy-binding", $serviceAccountEmail,
    "--project", $ProjectId,
    "--member", ("serviceAccount:{0}" -f $serviceAccountEmail),
    "--role", "roles/iam.serviceAccountTokenCreator",
    "--quiet"
) -FailureMessage "Failed to bind roles/iam.serviceAccountTokenCreator for signed URL support."

Write-Ok "Project IAM bindings ensured for Cloud SQL, Secret Manager, and signed URL access."
if ($UsePrivateCloudSqlIp) {
    Write-Step "Ensuring private service networking for Cloud SQL"
    Set-PrivateServiceConnection -GcloudCli $gcloudCli -Project $ProjectId -Network $Network -RangeName $PrivateServiceRangeName -PrefixLength $PrivateServiceRangePrefixLength
}

Write-Step "Ensuring Cloud SQL Postgres instance/database/user"
$existingDbUrlFromSecret = Get-SecretLatestValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.DatabaseUrl
$dbPassword = ""
if (-not [string]::IsNullOrWhiteSpace($existingDbUrlFromSecret)) {
    if ($existingDbUrlFromSecret -match '^postgresql://[^:]+:(?<password>[^@]+)@/') {
        $dbPassword = [System.Uri]::UnescapeDataString([string]$Matches["password"])
    }
}
if ([string]::IsNullOrWhiteSpace($dbPassword)) {
    $dbPassword = New-RandomToken -Length 28
}
$dbPasswordSecure = New-Object System.Security.SecureString
foreach ($dbPasswordChar in $dbPassword.ToCharArray()) {
    $dbPasswordSecure.AppendChar($dbPasswordChar)
}
$dbPasswordSecure.MakeReadOnly()

$currentSecretConnectionName = Get-CloudSqlConnectionNameFromDatabaseUrl -DatabaseUrl $existingDbUrlFromSecret
$currentSecretInstanceName = Get-CloudSqlInstanceNameFromConnectionName -ConnectionName $currentSecretConnectionName
$previousCloudSqlInstance = ""
$previousCloudSqlConnectionName = $currentSecretConnectionName
$cloudSqlSourceInstance = ""
$cloudSqlTargetInstance = ""
$cloudSqlInstanceToDeleteAfterSuccessfulCutover = ""
$deletedCloudSqlInstance = ""
$pendingCloudSqlMigration = $false
$stagedDatabaseUrl = ""
$cloudSqlMigrationExportUri = ""
$currentDatabaseUrlForRollback = $existingDbUrlFromSecret
$currentCloudSqlInstanceName = $CloudSqlInstance
$currentCloudSqlInstanceInfo = $null
if (-not [string]::IsNullOrWhiteSpace($currentSecretInstanceName)) {
    $currentCloudSqlInstanceName = $currentSecretInstanceName
    $currentCloudSqlInstanceInfo = Get-CloudSqlInstanceInfo -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $currentCloudSqlInstanceName
}
if ($null -eq $currentCloudSqlInstanceInfo -and $currentCloudSqlInstanceName -ne $CloudSqlInstance) {
    $currentCloudSqlInstanceName = $CloudSqlInstance
    $currentCloudSqlInstanceInfo = Get-CloudSqlInstanceInfo -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $currentCloudSqlInstanceName
}

if (
    $null -ne $currentCloudSqlInstanceInfo -and
    -not [string]::IsNullOrWhiteSpace($currentCloudSqlInstanceInfo.Name) -and
    $currentCloudSqlInstanceInfo.Name -ne $CloudSqlInstance
) {
    $normalizedCurrentCloudSqlInstanceName = $currentCloudSqlInstanceInfo.Name.Trim().ToLowerInvariant()
    $normalizedRequestedCloudSqlInstanceName = $CloudSqlInstance.Trim().ToLowerInvariant()
    if ($normalizedCurrentCloudSqlInstanceName.StartsWith($normalizedRequestedCloudSqlInstanceName + "-")) {
        $obsoleteCloudSqlBaseInstanceInfo = Get-CloudSqlInstanceInfo -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $CloudSqlInstance
        if ($null -ne $obsoleteCloudSqlBaseInstanceInfo -and $obsoleteCloudSqlBaseInstanceInfo.Name -ne $currentCloudSqlInstanceInfo.Name) {
            $cloudSqlInstanceToDeleteAfterSuccessfulCutover = $obsoleteCloudSqlBaseInstanceInfo.Name
            Write-Info ("A previous Cloud SQL instance remains from an earlier replacement cutover and will be deleted after a successful deploy: {0}" -f $cloudSqlInstanceToDeleteAfterSuccessfulCutover)
        }
    }
}

$requestedDiskType = Get-CloudSqlDiskTypeName -StorageType $CloudSqlStorageType
$requiresSafeCloudSqlReplacement = $false
if ($null -ne $currentCloudSqlInstanceInfo) {
    $requiresSafeCloudSqlReplacement = (
        $currentCloudSqlInstanceInfo.Tier -ne $CloudSqlTier -or
        $currentCloudSqlInstanceInfo.StorageType -ne $requestedDiskType -or
        $currentCloudSqlInstanceInfo.StorageSizeGb -gt $CloudSqlStorageGb
    )
}

if ($null -eq $currentCloudSqlInstanceInfo) {
    $ensureResult = Set-CloudSqlInstance `
        -GcloudCli $gcloudCli `
        -Project $ProjectId `
        -Region $Region `
        -InstanceName $CloudSqlInstance `
        -DatabaseVersion $CloudSqlDatabaseVersion `
        -Tier $CloudSqlTier `
        -StorageGb $CloudSqlStorageGb `
        -StorageType $CloudSqlStorageType `
        -UsePrivateIp $UsePrivateCloudSqlIp `
        -Network $Network `
        -EnableBackups $EnableCloudSqlBackups `
        -BackupStartTime $CloudSqlBackupStartTime `
        -EnablePointInTimeRecovery $EnableCloudSqlPointInTimeRecovery
    Set-CloudSqlDatabaseAndUser -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $CloudSqlInstance -DatabaseName $CloudSqlDatabase -UserName $CloudSqlUser -Password $dbPasswordSecure
    $currentCloudSqlInstanceInfo = $ensureResult.Info
    $currentCloudSqlInstanceName = $currentCloudSqlInstanceInfo.Name
    $cloudSqlConnectionName = $currentCloudSqlInstanceInfo.ConnectionName
    $CloudSqlInstance = $currentCloudSqlInstanceInfo.Name
}
elseif ($requiresSafeCloudSqlReplacement) {
    $replacementInstanceName = Get-DesiredCloudSqlReplacementInstanceName -BaseInstanceName $CloudSqlInstance -Tier $CloudSqlTier -StorageType $CloudSqlStorageType -StorageGb $CloudSqlStorageGb -ExplicitReplacementInstance $CloudSqlReplacementInstance
    $replacementInfo = Get-CloudSqlInstanceInfo -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $replacementInstanceName
    if ($null -ne $replacementInfo -and $replacementInfo.Name -ne $currentCloudSqlInstanceInfo.Name) {
        throw ("Replacement Cloud SQL instance '{0}' already exists. To avoid overwriting an unknown database, choose a different -CloudSqlReplacementInstance or delete the stale replacement instance first." -f $replacementInstanceName)
    }

    $ensureReplacement = Set-CloudSqlInstance `
        -GcloudCli $gcloudCli `
        -Project $ProjectId `
        -Region $Region `
        -InstanceName $replacementInstanceName `
        -DatabaseVersion $CloudSqlDatabaseVersion `
        -Tier $CloudSqlTier `
        -StorageGb $CloudSqlStorageGb `
        -StorageType $CloudSqlStorageType `
        -UsePrivateIp $UsePrivateCloudSqlIp `
        -Network $Network `
        -EnableBackups $EnableCloudSqlBackups `
        -BackupStartTime $CloudSqlBackupStartTime `
        -EnablePointInTimeRecovery $EnableCloudSqlPointInTimeRecovery

    if (-not $ensureReplacement.Created -and $ensureReplacement.Info.Name -ne $currentCloudSqlInstanceInfo.Name) {
        throw ("Replacement Cloud SQL instance '{0}' already existed before this run. For the lowest-risk migration path, the script only imports into a newly created replacement instance." -f $replacementInstanceName)
    }

    Set-CloudSqlDatabaseAndUser -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $replacementInstanceName -DatabaseName $CloudSqlDatabase -UserName $CloudSqlUser -Password $dbPasswordSecure

    $previousCloudSqlInstance = $currentCloudSqlInstanceInfo.Name
    $cloudSqlSourceInstance = $currentCloudSqlInstanceInfo.Name
    $cloudSqlTargetInstance = $ensureReplacement.Info.Name
    $cloudSqlConnectionName = $ensureReplacement.Info.ConnectionName
    $CloudSqlInstance = $ensureReplacement.Info.Name
    $cloudSqlInstanceToDeleteAfterSuccessfulCutover = $previousCloudSqlInstance
    $pendingCloudSqlMigration = $true

    Write-Info ("Preparing safe Cloud SQL replacement migration from '{0}' to '{1}'." -f $cloudSqlSourceInstance, $cloudSqlTargetInstance)
}
else {
    $ensureResult = Set-CloudSqlInstance `
        -GcloudCli $gcloudCli `
        -Project $ProjectId `
        -Region $Region `
        -InstanceName $currentCloudSqlInstanceName `
        -DatabaseVersion $CloudSqlDatabaseVersion `
        -Tier $CloudSqlTier `
        -StorageGb $CloudSqlStorageGb `
        -StorageType $CloudSqlStorageType `
        -UsePrivateIp $UsePrivateCloudSqlIp `
        -Network $Network `
        -EnableBackups $EnableCloudSqlBackups `
        -BackupStartTime $CloudSqlBackupStartTime `
        -EnablePointInTimeRecovery $EnableCloudSqlPointInTimeRecovery
    Set-CloudSqlDatabaseAndUser -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $currentCloudSqlInstanceName -DatabaseName $CloudSqlDatabase -UserName $CloudSqlUser -Password $dbPasswordSecure
    $currentCloudSqlInstanceInfo = $ensureResult.Info
    $cloudSqlConnectionName = $currentCloudSqlInstanceInfo.ConnectionName
    $CloudSqlInstance = $currentCloudSqlInstanceInfo.Name
}

if ([string]::IsNullOrWhiteSpace($cloudSqlConnectionName)) {
    throw "Cloud SQL connection name is empty."
}
Write-Ok ("Cloud SQL connection: {0}" -f $cloudSqlConnectionName)

$redisHost = ""
$redisPort = ""
if ($EnableRedis) {
    Write-Step "Ensuring Memorystore Redis"
    $redisDescribe = Invoke-External -FilePath $gcloudCli -Arguments @(
        "redis", "instances", "describe", $RedisInstance,
        "--project", $ProjectId,
        "--region", $Region,
        "--format=value(name)"
    )
    if ($redisDescribe.ExitCode -ne 0) {
        Invoke-Required -FilePath $gcloudCli -Arguments @(
            "redis", "instances", "create", $RedisInstance,
            "--project", $ProjectId,
            "--region", $Region,
            "--network", $Network,
            "--size", $RedisSizeGb,
            "--tier", "basic",
            "--quiet"
        ) -FailureMessage "Failed creating Redis instance."
        Write-Ok ("Created Redis instance: {0}" -f $RedisInstance)
    }
    else {
        Write-Ok ("Redis instance already exists: {0}" -f $RedisInstance)
    }

    Wait-ForState -Label ("Redis instance {0}" -f $RedisInstance) -Expected "READY" -ReadState {
        (Invoke-Required -FilePath $gcloudCli -Arguments @(
            "redis", "instances", "describe", $RedisInstance,
            "--project", $ProjectId,
            "--region", $Region,
            "--format=value(state)"
        ) -FailureMessage "Failed reading Redis state." -PassThru | Select-Object -First 1).Trim()
    } -TimeoutSeconds 1800 -SleepSeconds 10

    $redisHost = (Invoke-Required -FilePath $gcloudCli -Arguments @(
        "redis", "instances", "describe", $RedisInstance,
        "--project", $ProjectId,
        "--region", $Region,
        "--format=value(host)"
    ) -FailureMessage "Failed reading Redis host." -PassThru | Select-Object -First 1).Trim()

    $redisPort = (Invoke-Required -FilePath $gcloudCli -Arguments @(
        "redis", "instances", "describe", $RedisInstance,
        "--project", $ProjectId,
        "--region", $Region,
        "--format=value(port)"
    ) -FailureMessage "Failed reading Redis port." -PassThru | Select-Object -First 1).Trim()

    if ([string]::IsNullOrWhiteSpace($redisHost) -or [string]::IsNullOrWhiteSpace($redisPort)) {
        throw "Redis host/port could not be resolved."
    }
    Write-Ok ("Redis endpoint: {0}:{1}" -f $redisHost, $redisPort)
}
else {
    Write-Info "Skipping Memorystore Redis provisioning because -EnableRedis is false."
}

Write-Step "Ensuring Serverless VPC Access connector"
$connectorDescribe = Invoke-External -FilePath $gcloudCli -Arguments @(
    "compute", "networks", "vpc-access", "connectors", "describe", $VpcConnector,
    "--project", $ProjectId,
    "--region", $Region,
    "--format=value(name)"
)
if ($connectorDescribe.ExitCode -ne 0) {
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "compute", "networks", "vpc-access", "connectors", "create", $VpcConnector,
        "--project", $ProjectId,
        "--region", $Region,
        "--network", $Network,
        "--range", $VpcConnectorRange,
        "--min-instances", "2",
        "--max-instances", "3",
        "--quiet"
    ) -FailureMessage "Failed creating VPC connector."
    Write-Ok ("Created VPC connector: {0}" -f $VpcConnector)
}
else {
    Write-Ok ("VPC connector already exists: {0}" -f $VpcConnector)
}

Wait-ForState -Label ("VPC connector {0}" -f $VpcConnector) -Expected "READY" -ReadState {
    (Invoke-Required -FilePath $gcloudCli -Arguments @(
        "compute", "networks", "vpc-access", "connectors", "describe", $VpcConnector,
        "--project", $ProjectId,
        "--region", $Region,
        "--format=value(state)"
    ) -FailureMessage "Failed reading VPC connector state." -PassThru | Select-Object -First 1).Trim()
} -TimeoutSeconds 1200 -SleepSeconds 10

Write-Step "Ensuring GCS bucket and IAM"
$bucketDescribe = Invoke-External -FilePath $gcloudCli -Arguments @(
    "storage", "buckets", "describe", $bucketRef,
    "--project", $ProjectId
)
if ($bucketDescribe.ExitCode -ne 0) {
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "storage", "buckets", "create", $bucketRef,
        "--project", $ProjectId,
        "--location", $Region,
        "--uniform-bucket-level-access",
        "--public-access-prevention",
        "--quiet"
    ) -FailureMessage ("Failed creating bucket '{0}'." -f $bucketRef)
    Write-Ok ("Created bucket: {0}" -f $bucketRef)
}
else {
    Write-Ok ("Bucket already exists: {0}" -f $bucketRef)
}

Invoke-Required -FilePath $gcloudCli -Arguments @(
    "storage", "buckets", "add-iam-policy-binding", $bucketRef,
    "--member", ("serviceAccount:{0}" -f $serviceAccountEmail),
    "--role", "roles/storage.objectUser",
    "--quiet"
) -FailureMessage "Failed binding roles/storage.objectUser on bucket."

Invoke-Required -FilePath $gcloudCli -Arguments @(
    "storage", "buckets", "add-iam-policy-binding", $bucketRef,
    "--member", ("serviceAccount:{0}" -f $serviceAccountEmail),
    "--role", "roles/storage.bucketViewer",
    "--quiet"
) -FailureMessage "Failed binding roles/storage.bucketViewer on bucket."

Remove-BucketIamBindingIfPresent -GcloudCli $gcloudCli -BucketRef $bucketRef -Member ("serviceAccount:{0}" -f $serviceAccountEmail) -Role "roles/storage.objectAdmin"
Remove-BucketIamBindingIfPresent -GcloudCli $gcloudCli -BucketRef $bucketRef -Member ("serviceAccount:{0}" -f $serviceAccountEmail) -Role "roles/storage.legacyBucketReader"

Write-Ok "Bucket IAM bindings ensured for runtime service account (least-privilege profile)."

if ($pendingCloudSqlMigration) {
    Write-Step "Safely migrating Cloud SQL data to replacement instance"

    $sourceCloudSqlInfo = Get-CloudSqlInstanceInfo -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $cloudSqlSourceInstance
    $targetCloudSqlInfo = Get-CloudSqlInstanceInfo -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $CloudSqlInstance
    if ($null -eq $sourceCloudSqlInfo) {
        throw ("Cloud SQL source instance '{0}' could not be described for migration." -f $cloudSqlSourceInstance)
    }
    if ($null -eq $targetCloudSqlInfo) {
        throw ("Cloud SQL target instance '{0}' could not be described for migration." -f $CloudSqlInstance)
    }

    Grant-CloudSqlBucketAccess -GcloudCli $gcloudCli -BucketRef $bucketRef -ServiceAccountEmail $sourceCloudSqlInfo.ServiceAccountEmailAddress
    Grant-CloudSqlBucketAccess -GcloudCli $gcloudCli -BucketRef $bucketRef -ServiceAccountEmail $targetCloudSqlInfo.ServiceAccountEmailAddress

    $cloudSqlMigrationExportUri = "{0}/cloudsql-migrations/{1}/{2}-{3}.sql.gz" -f $bucketRef, $cloudSqlSourceInstance, (Get-Date -Format "yyyyMMddHHmmss"), $CloudSqlDatabase
    Export-CloudSqlDatabase -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $cloudSqlSourceInstance -DatabaseName $CloudSqlDatabase -DestinationUri $cloudSqlMigrationExportUri
    Write-Ok ("Exported Cloud SQL database to: {0}" -f $cloudSqlMigrationExportUri)

    Import-CloudSqlDatabase -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $CloudSqlInstance -DatabaseName $CloudSqlDatabase -UserName $CloudSqlUser -SourceUri $cloudSqlMigrationExportUri
    Write-Ok ("Imported Cloud SQL database into replacement instance: {0}" -f $CloudSqlInstance)
}

Write-Step "Ensuring required GCS dependency"
Add-RequirementLine -FilePath $requirementsPath -RequiredLine "google-cloud-storage>=2.18,<3.0" -AutoFix $AutoFixGcsDependency

if ($BuildAndPushImage) {
    Write-Step "Building and pushing image"
    if (-not (Test-Path -Path $pushScriptPath -PathType Leaf)) {
        throw ("Missing push script: {0}" -f $pushScriptPath)
    }

    & $pushScriptPath `
        -ProjectId $ProjectId `
        -Region $Region `
        -Repository $Repository `
        -ImageName $ImageName `
        -ImageTag $ImageTag `
        -DisableBuildAttestations $DisableBuildAttestations `
        -DisableContainerVulnerabilityScanning $DisableContainerVulnerabilityScanning `
        -SkipAuthLogin:$SkipAuthLogin `
        -Verbose:$($VerbosePreference -eq "Continue")

    if ($LASTEXITCODE -ne 0) {
        throw "Image build/push script failed."
    }
}
else {
    Write-Info ("Skipping image build/push. Using existing image: {0}" -f $imageRef)
}

Write-Step "Verifying image can import GCS bindings"
Invoke-Required -FilePath "docker" -Arguments @(
    "run", "--rm", $imageRef,
    "python", "-c", "import storages.backends.gcloud, google.cloud.storage; print('gcs deps ok')"
) -FailureMessage "Image is missing GCS dependencies. Ensure requirements include google-cloud-storage and rebuild."

Write-Ok "Image import check passed."
Write-Step "Upserting secrets"
$existingDjangoSecret = Get-SecretLatestValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.SecretKey
$existingGoogleMapsApiSecret = Get-SecretLatestValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.GoogleMapsApiKey
if ([string]::IsNullOrWhiteSpace($existingDjangoSecret)) {
    $existingDjangoSecret = (python -c "import secrets; print(secrets.token_urlsafe(48))")
}

$databaseUrl = "postgresql://{0}:{1}@/{2}?host=/cloudsql/{3}" -f $CloudSqlUser, $dbPassword, $CloudSqlDatabase, $cloudSqlConnectionName

Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.SecretKey -SecretValue $existingDjangoSecret
if ($pendingCloudSqlMigration) {
    Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.DatabaseUrlCandidate -SecretValue $databaseUrl
    $stagedDatabaseUrl = $databaseUrl
    Write-Info ("Staged replacement DATABASE_URL in secret: {0}" -f $secretNames.DatabaseUrlCandidate)
}
else {
    Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.DatabaseUrl -SecretValue $databaseUrl
}
if ($EnableRedis) {
    $redisUrl = "redis://{0}:{1}/0" -f $redisHost, $redisPort
    $celeryBrokerUrl = "redis://{0}:{1}/1" -f $redisHost, $redisPort
    $celeryResultBackend = "redis://{0}:{1}/2" -f $redisHost, $redisPort

    Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.RedisUrl -SecretValue $redisUrl
    Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.CeleryBrokerUrl -SecretValue $celeryBrokerUrl
    Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.CeleryResultStore -SecretValue $celeryResultBackend
}

$requestedAllowedHosts = @(Split-CommaList -Values $DjangoAllowedHosts)
$requestedCsrfTrustedOrigins = @(Split-CommaList -Values $CsrfTrustedOrigins)
$existingServiceEnv = Get-CloudRunServiceEnvMap -GcloudCli $gcloudCli -Project $ProjectId -Region $Region -ServiceName $ServiceName
$requestedCanonicalHost = ""
if (-not [string]::IsNullOrWhiteSpace($CanonicalHost)) {
    $requestedCanonicalHost = (Resolve-HostName -Candidate $CanonicalHost -FallbackHost $CanonicalHost -ParameterName "CanonicalHost").ToLowerInvariant()
}

$inferredLoadBalancerDomains = @()
$preferredInferredDomain = ""
$shouldInferCustomDomain = (
    $CloudRunIngress -eq "internal-and-cloud-load-balancing" -and
    (
        [string]::IsNullOrWhiteSpace($SmokeBaseUrl) -or
        [string]::IsNullOrWhiteSpace($UptimeCheckHost) -or
        $requestedAllowedHosts.Count -eq 0 -or
        $requestedCsrfTrustedOrigins.Count -eq 0
    )
)
if ($shouldInferCustomDomain) {
    $inferredLoadBalancerDomains = @(Get-CloudRunLoadBalancerDomains -GcloudCli $gcloudCli -Project $ProjectId -Region $Region -ServiceName $ServiceName)
    if ($inferredLoadBalancerDomains.Count -gt 0) {
        Write-Info ("Auto-discovered load balancer domain(s): {0}" -f ($inferredLoadBalancerDomains -join ", "))
    }
    else {
        Write-Info "Could not auto-discover a custom domain from load balancer resources; falling back to current parameter/default behavior."
    }
    $preferredInferredDomain = Select-PreferredCustomDomain -Domains $inferredLoadBalancerDomains
}

$existingAllowedHosts = ""
$existingCsrfTrustedOrigins = ""
$existingCanonicalHost = ""
$existingGoogleMapsApiKey = ""
if ($null -ne $existingServiceEnv) {
    if ($existingServiceEnv.ContainsKey("DJANGO_ALLOWED_HOSTS")) {
        $existingAllowedHosts = [string]$existingServiceEnv["DJANGO_ALLOWED_HOSTS"]
    }
    if ($existingServiceEnv.ContainsKey("CSRF_TRUSTED_ORIGINS")) {
        $existingCsrfTrustedOrigins = [string]$existingServiceEnv["CSRF_TRUSTED_ORIGINS"]
    }
    if ($existingServiceEnv.ContainsKey("CANONICAL_HOST")) {
        $existingCanonicalHost = [string]$existingServiceEnv["CANONICAL_HOST"]
    }
    if ($existingServiceEnv.ContainsKey("GOOGLE_MAPS_API_KEY")) {
        $existingGoogleMapsApiKey = [string]$existingServiceEnv["GOOGLE_MAPS_API_KEY"]
    }
}

$resolvedAllowedHosts = ""
if ($requestedAllowedHosts.Count -gt 0) {
    $resolvedAllowedHosts = ($requestedAllowedHosts -join ",")
}
elseif (-not [string]::IsNullOrWhiteSpace($existingAllowedHosts)) {
    $resolvedAllowedHosts = $existingAllowedHosts
}
if ($requestedAllowedHosts.Count -eq 0 -and $inferredLoadBalancerDomains.Count -gt 0) {
    $mergedAllowedHosts = New-Object System.Collections.Generic.List[string]
    foreach ($candidateHost in @(Split-CommaList -Values @($resolvedAllowedHosts))) {
        if (-not $mergedAllowedHosts.Contains($candidateHost)) {
            [void]$mergedAllowedHosts.Add($candidateHost)
        }
    }
    foreach ($candidateHost in @($inferredLoadBalancerDomains)) {
        if (-not $mergedAllowedHosts.Contains($candidateHost)) {
            [void]$mergedAllowedHosts.Add($candidateHost)
        }
    }
    if ($mergedAllowedHosts.Count -gt 0) {
        $resolvedAllowedHosts = ($mergedAllowedHosts -join ",")
    }
}

$resolvedCsrfTrustedOrigins = ""
if ($requestedCsrfTrustedOrigins.Count -gt 0) {
    $resolvedCsrfTrustedOrigins = ($requestedCsrfTrustedOrigins -join ",")
}
elseif (-not [string]::IsNullOrWhiteSpace($existingCsrfTrustedOrigins)) {
    $resolvedCsrfTrustedOrigins = $existingCsrfTrustedOrigins
}
if ($requestedCsrfTrustedOrigins.Count -eq 0 -and $inferredLoadBalancerDomains.Count -gt 0) {
    $mergedCsrfOrigins = New-Object System.Collections.Generic.List[string]
    foreach ($origin in @(Split-CommaList -Values @($resolvedCsrfTrustedOrigins))) {
        if (-not $mergedCsrfOrigins.Contains($origin)) {
            [void]$mergedCsrfOrigins.Add($origin)
        }
    }
    foreach ($domain in @($inferredLoadBalancerDomains)) {
        $origin = "https://{0}" -f $domain
        if (-not $mergedCsrfOrigins.Contains($origin)) {
            [void]$mergedCsrfOrigins.Add($origin)
        }
    }
    if ($mergedCsrfOrigins.Count -gt 0) {
        $resolvedCsrfTrustedOrigins = ($mergedCsrfOrigins -join ",")
    }
}

$resolvedCanonicalHost = ""
if (-not [string]::IsNullOrWhiteSpace($requestedCanonicalHost)) {
    $resolvedCanonicalHost = $requestedCanonicalHost
}
elseif (-not [string]::IsNullOrWhiteSpace($preferredInferredDomain)) {
    $resolvedCanonicalHost = $preferredInferredDomain.ToLowerInvariant()
}
elseif (-not [string]::IsNullOrWhiteSpace($existingCanonicalHost)) {
    $resolvedCanonicalHost = (Resolve-HostName -Candidate $existingCanonicalHost -FallbackHost $existingCanonicalHost -ParameterName "ExistingCanonicalHost").ToLowerInvariant()
}
if (-not [string]::IsNullOrWhiteSpace($resolvedCanonicalHost)) {
    Write-Info ("Using canonical host redirect target: {0}" -f $resolvedCanonicalHost)
}
else {
    Write-Info "Canonical host redirect is not configured for this deploy run."
}

$resolvedGoogleMapsApiKey = ""
$autoProvisionedGoogleMapsApiKey = $false
if (-not [string]::IsNullOrWhiteSpace($GoogleMapsApiKey)) {
    $resolvedGoogleMapsApiKey = $GoogleMapsApiKey.Trim()
}
elseif (-not [string]::IsNullOrWhiteSpace($env:GOOGLE_MAPS_API_KEY)) {
    $resolvedGoogleMapsApiKey = $env:GOOGLE_MAPS_API_KEY.Trim()
}
elseif (-not [string]::IsNullOrWhiteSpace($env:GOOGLE_PLACES_API_KEY)) {
    $resolvedGoogleMapsApiKey = $env:GOOGLE_PLACES_API_KEY.Trim()
}
elseif (-not [string]::IsNullOrWhiteSpace($existingGoogleMapsApiSecret)) {
    $resolvedGoogleMapsApiKey = $existingGoogleMapsApiSecret.Trim()
}
elseif (-not [string]::IsNullOrWhiteSpace($existingGoogleMapsApiKey)) {
    $resolvedGoogleMapsApiKey = $existingGoogleMapsApiKey.Trim()
}
if ([string]::IsNullOrWhiteSpace($resolvedGoogleMapsApiKey)) {
    Write-Info "GOOGLE_MAPS_API_KEY was not provided. Auto-provisioning a managed server key via API Keys API."
    $apiKeysAccessToken = Get-GcloudAccessToken -GcloudCli $gcloudCli
    $resolvedGoogleMapsApiKey = Get-ManagedGoogleMapsApiKey -GcloudCli $gcloudCli -Project $ProjectId -AccessToken $apiKeysAccessToken -DisplayName "Tapne Places Server Key (managed)"
    $autoProvisionedGoogleMapsApiKey = -not [string]::IsNullOrWhiteSpace($resolvedGoogleMapsApiKey)
}
if (-not [string]::IsNullOrWhiteSpace($GoogleMapsApiKey)) {
    Write-Info "Applying GOOGLE_MAPS_API_KEY from script parameter."
}
elseif (-not [string]::IsNullOrWhiteSpace($env:GOOGLE_MAPS_API_KEY)) {
    Write-Info "Applying GOOGLE_MAPS_API_KEY from process environment."
}
elseif (-not [string]::IsNullOrWhiteSpace($env:GOOGLE_PLACES_API_KEY)) {
    Write-Info "Applying GOOGLE_MAPS_API_KEY from GOOGLE_PLACES_API_KEY process environment."
}
elseif (-not [string]::IsNullOrWhiteSpace($existingGoogleMapsApiSecret)) {
    Write-Info "Preserving GOOGLE_MAPS_API_KEY from Secret Manager."
}
elseif ($autoProvisionedGoogleMapsApiKey) {
    Write-Info "Applying auto-provisioned managed GOOGLE_MAPS_API_KEY from API Keys API."
}
elseif (-not [string]::IsNullOrWhiteSpace($resolvedGoogleMapsApiKey)) {
    Write-Info "Preserving existing GOOGLE_MAPS_API_KEY from the current Cloud Run service."
}
else {
    Write-Info "GOOGLE_MAPS_API_KEY is not set. Destination autocomplete/map will stay disabled."
}
if (-not [string]::IsNullOrWhiteSpace($resolvedGoogleMapsApiKey)) {
    Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.GoogleMapsApiKey -SecretValue $resolvedGoogleMapsApiKey
}

$bootstrapHostCsrfFromServiceUrl = [string]::IsNullOrWhiteSpace($resolvedAllowedHosts) -and [string]::IsNullOrWhiteSpace($resolvedCsrfTrustedOrigins)
if ($requestedAllowedHosts.Count -gt 0 -or $requestedCsrfTrustedOrigins.Count -gt 0) {
    Write-Info "Applying DJANGO_ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS from script parameters."
}
elseif ($inferredLoadBalancerDomains.Count -gt 0) {
    Write-Info "Auto-applying DJANGO_ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS from discovered load balancer domain(s)."
}
elseif (-not [string]::IsNullOrWhiteSpace($resolvedAllowedHosts) -or -not [string]::IsNullOrWhiteSpace($resolvedCsrfTrustedOrigins)) {
    Write-Info "Preserving existing DJANGO_ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS from the current Cloud Run service."
}
else {
    Write-Info "No existing host/csrf envs found. Will bootstrap to deployed service host once after deploy."
}

$baseEnv = @(
    "APP_ENV=prod",
    "DEBUG=false",
    ("WEB_CONCURRENCY={0}" -f $WebConcurrency),
    ("GUNICORN_TIMEOUT={0}" -f $GunicornTimeout),
    "STORAGE_BACKEND=gcs",
    ("GCS_BUCKET_NAME={0}" -f $BucketName),
    ("GCS_QUERYSTRING_AUTH={0}" -f (ConvertTo-BoolString -Value $EnableGcsSignedUrls)),
    ("GOOGLE_CLOUD_PROJECT={0}" -f $ProjectId),
    "USE_X_FORWARDED_PROTO=true",
    "CANONICAL_SCHEME=https",
    "SECURE_SSL_REDIRECT=true",
    "SESSION_COOKIE_SECURE=true",
    "CSRF_COOKIE_SECURE=true"
)
if (-not [string]::IsNullOrWhiteSpace($resolvedAllowedHosts)) {
    $baseEnv += ("DJANGO_ALLOWED_HOSTS={0}" -f $resolvedAllowedHosts)
}
if (-not [string]::IsNullOrWhiteSpace($resolvedCsrfTrustedOrigins)) {
    $baseEnv += ("CSRF_TRUSTED_ORIGINS={0}" -f $resolvedCsrfTrustedOrigins)
}
if (-not [string]::IsNullOrWhiteSpace($resolvedCanonicalHost)) {
    $baseEnv += ("CANONICAL_HOST={0}" -f $resolvedCanonicalHost)
    $baseEnv += "CANONICAL_HOST_REDIRECT_ENABLED=true"
}
else {
    $baseEnv += "CANONICAL_HOST_REDIRECT_ENABLED=false"
}
$webEnv = @($baseEnv + @("COLLECTSTATIC_ON_BOOT=true"))
$jobEnv = @($baseEnv + @("COLLECTSTATIC_ON_BOOT=false"))
$webEnvArg = ConvertTo-GcloudDictArg -Entries $webEnv
$jobEnvArg = ConvertTo-GcloudDictArg -Entries $jobEnv
$jobDatabaseSecretName = $secretNames.DatabaseUrl
if ($pendingCloudSqlMigration) {
    $jobDatabaseSecretName = $secretNames.DatabaseUrlCandidate
}
$jobSecretMap = @(
    ("SECRET_KEY={0}:latest" -f $secretNames.SecretKey),
    ("DATABASE_URL={0}:latest" -f $jobDatabaseSecretName)
)
$webSecretMap = @(
    ("SECRET_KEY={0}:latest" -f $secretNames.SecretKey),
    ("DATABASE_URL={0}:latest" -f $secretNames.DatabaseUrl)
)
if ($EnableRedis) {
    $redisSecretEntries = @(
        ("REDIS_URL={0}:latest" -f $secretNames.RedisUrl),
        ("CELERY_BROKER_URL={0}:latest" -f $secretNames.CeleryBrokerUrl),
        ("CELERY_RESULT_BACKEND={0}:latest" -f $secretNames.CeleryResultStore)
    )
    $jobSecretMap += $redisSecretEntries
    $webSecretMap += $redisSecretEntries
}
if (-not [string]::IsNullOrWhiteSpace($resolvedGoogleMapsApiKey)) {
    $googleMapsSecretEntry = ("GOOGLE_MAPS_API_KEY={0}:latest" -f $secretNames.GoogleMapsApiKey)
    $jobSecretMap += $googleMapsSecretEntry
    $webSecretMap += $googleMapsSecretEntry
}

if (-not $SkipMigrations) {
    Write-Step "Deploying and executing migration job"
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "run", "jobs", "deploy", "tapne-migrate",
        "--project", $ProjectId,
        "--region", $Region,
        "--image", $imageRef,
        "--service-account", $serviceAccountEmail,
        "--set-cloudsql-instances", $cloudSqlConnectionName,
        "--vpc-connector", $VpcConnector,
        "--vpc-egress", "private-ranges-only",
        "--set-secrets", ($jobSecretMap -join ","),
        "--set-env-vars", $jobEnvArg,
        "--command", "python",
        "--args", "manage.py,migrate,--noinput",
        "--tasks", "1",
        "--max-retries", "1",
        "--task-timeout", "1800",
        "--quiet"
    ) -FailureMessage "Failed deploying migration job."

    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "run", "jobs", "execute", "tapne-migrate",
        "--project", $ProjectId,
        "--region", $Region,
        "--wait"
    ) -FailureMessage "Migration job execution failed."

    Write-Ok "Migration job completed."
}
else {
    Write-Info "Skipping migrations as requested (-SkipMigrations)."
}

$databaseUrlCutoverApplied = $false
try {
if ($pendingCloudSqlMigration) {
    if ([string]::IsNullOrWhiteSpace($stagedDatabaseUrl)) {
        throw "Cloud SQL migration staged database URL is empty."
    }
    Write-Step "Promoting staged Cloud SQL DATABASE_URL for web cutover"
    Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.DatabaseUrl -SecretValue $stagedDatabaseUrl
    $databaseUrlCutoverApplied = $true
    Write-Info ("Primary DATABASE_URL secret now points to replacement Cloud SQL instance: {0}" -f $CloudSqlInstance)
}

Write-Step "Deploying Cloud Run web service"
$deployArgs = @(
    "run", "deploy", $ServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--image", $imageRef,
    "--service-account", $serviceAccountEmail,
    "--port", "8080",
    "--cpu", $CloudRunCpu,
    "--memory", $CloudRunMemory,
    "--concurrency", $CloudRunConcurrency,
    "--ingress", $CloudRunIngress,
    "--timeout", $CloudRunTimeoutSeconds,
    "--min-instances", $CloudRunMinInstances,
    "--max-instances", $CloudRunMaxInstances,
    "--set-cloudsql-instances", $cloudSqlConnectionName,
    "--vpc-connector", $VpcConnector,
    "--vpc-egress", "private-ranges-only",
    "--set-secrets", ($webSecretMap -join ","),
    "--set-env-vars", $webEnvArg,
    "--quiet"
)
if ($AllowUnauthenticated) {
    $deployArgs += "--allow-unauthenticated"
}
else {
    $deployArgs += "--no-allow-unauthenticated"
}
Invoke-Required -FilePath $gcloudCli -Arguments $deployArgs -FailureMessage "Cloud Run deploy failed."

$serviceUrl = (Invoke-Required -FilePath $gcloudCli -Arguments @(
    "run", "services", "describe", $ServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--format=value(status.url)"
) -FailureMessage "Failed reading Cloud Run service URL." -PassThru | Select-Object -First 1).Trim()
if ([string]::IsNullOrWhiteSpace($serviceUrl)) {
    throw "Cloud Run service URL is empty."
}
$serviceHost = ([System.Uri]$serviceUrl).Host
Write-Ok ("Deployed service URL: {0}" -f $serviceUrl)

$smokeBaseUrlCandidate = $SmokeBaseUrl
if ([string]::IsNullOrWhiteSpace($smokeBaseUrlCandidate) -and -not [string]::IsNullOrWhiteSpace($preferredInferredDomain)) {
    $smokeBaseUrlCandidate = "https://{0}" -f $preferredInferredDomain
    Write-Info ("Auto-setting SmokeBaseUrl from discovered custom domain: {0}" -f $smokeBaseUrlCandidate)
}
$uptimeCheckHostCandidate = $UptimeCheckHost
if ([string]::IsNullOrWhiteSpace($uptimeCheckHostCandidate) -and -not [string]::IsNullOrWhiteSpace($preferredInferredDomain)) {
    $uptimeCheckHostCandidate = $preferredInferredDomain
    Write-Info ("Auto-setting UptimeCheckHost from discovered custom domain: {0}" -f $uptimeCheckHostCandidate)
}

$smokeBaseUrlResolved = Resolve-BaseUrl -Candidate $smokeBaseUrlCandidate -Fallback $serviceUrl -ParameterName "SmokeBaseUrl"
$smokeHealthPathResolved = Resolve-HttpPath -PathValue $SmokeHealthPath -DefaultPath "/runtime/health/"
$smokeCssPathResolved = Resolve-HttpPath -PathValue $SmokeCssPath -DefaultPath "/static/css/tapne.css"
$smokeJsPathResolved = Resolve-HttpPath -PathValue $SmokeJsPath -DefaultPath "/static/js/tapne-ui.js"
$smokeBaseHostResolved = ([System.Uri]$smokeBaseUrlResolved).Host
$uptimeCheckHostResolved = Resolve-HostName -Candidate $uptimeCheckHostCandidate -FallbackHost $smokeBaseHostResolved -ParameterName "UptimeCheckHost"
$uptimeCheckPathResolved = Resolve-HttpPath -PathValue $UptimeCheckPath -DefaultPath "/runtime/health/"

if (
    -not $SkipSmokeTest -and
    $CloudRunIngress -eq "internal-and-cloud-load-balancing" -and
    $smokeBaseHostResolved -eq $serviceHost
) {
    throw "CloudRunIngress is internal-and-cloud-load-balancing, but SmokeBaseUrl resolves to the direct Cloud Run host. Set -SmokeBaseUrl to your load balancer/custom-domain URL (or use -SkipSmokeTest)."
}

if (
    $ConfigureMonitoring -and
    $CloudRunIngress -eq "internal-and-cloud-load-balancing" -and
    $uptimeCheckHostResolved -eq $serviceHost
) {
    throw "CloudRunIngress is internal-and-cloud-load-balancing, but UptimeCheckHost resolves to the direct Cloud Run host. Set -UptimeCheckHost to your load balancer/custom-domain host."
}

$effectiveAllowedHosts = $resolvedAllowedHosts
$effectiveCsrfTrustedOrigins = $resolvedCsrfTrustedOrigins
if ($bootstrapHostCsrfFromServiceUrl) {
    $effectiveAllowedHosts = $serviceHost
    $effectiveCsrfTrustedOrigins = ("https://{0}" -f $serviceHost)
    Write-Step "Bootstrapping host/csrf envs from deployed service URL"
    $hostCsrfUpdateArg = ConvertTo-GcloudDictArg -Entries @(
        ("DJANGO_ALLOWED_HOSTS={0}" -f $effectiveAllowedHosts),
        ("CSRF_TRUSTED_ORIGINS={0}" -f $effectiveCsrfTrustedOrigins)
    )
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "run", "services", "update", $ServiceName,
        "--project", $ProjectId,
        "--region", $Region,
        "--update-env-vars", $hostCsrfUpdateArg,
        "--quiet"
    ) -FailureMessage "Failed bootstrapping host/csrf env vars."
}
else {
    Write-Info "Keeping configured DJANGO_ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS (no forced run.app overwrite)."
}

if ($RunBootstrapRuntime) {
    Write-Step "Deploying and running optional bootstrap_runtime job"
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "run", "jobs", "deploy", "tapne-bootstrap-runtime",
        "--project", $ProjectId,
        "--region", $Region,
        "--image", $imageRef,
        "--service-account", $serviceAccountEmail,
        "--set-cloudsql-instances", $cloudSqlConnectionName,
        "--vpc-connector", $VpcConnector,
        "--vpc-egress", "private-ranges-only",
        "--set-secrets", ($webSecretMap -join ","),
        "--set-env-vars", $jobEnvArg,
        "--command", "python",
        "--args", "manage.py,bootstrap_runtime,--verbose",
        "--tasks", "1",
        "--max-retries", "1",
        "--task-timeout", "1800",
        "--quiet"
    ) -FailureMessage "Failed deploying bootstrap job."

    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "run", "jobs", "execute", "tapne-bootstrap-runtime",
        "--project", $ProjectId,
        "--region", $Region,
        "--wait"
    ) -FailureMessage "bootstrap_runtime job execution failed."

    Write-Ok "bootstrap_runtime job completed."
}

if (-not $SkipSmokeTest) {
    Write-Step "Running post-deploy smoke tests"

    $healthUrl = "{0}{1}" -f $smokeBaseUrlResolved, $smokeHealthPathResolved
    $cssUrl = "{0}{1}" -f $smokeBaseUrlResolved, $smokeCssPathResolved
    $jsUrl = "{0}{1}" -f $smokeBaseUrlResolved, $smokeJsPathResolved

    $healthResponse = $null
    $attempts = 15
    for ($attempt = 1; $attempt -le $attempts; $attempt++) {
        try {
            $healthResponse = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -Method Get -TimeoutSec 30
            if ($healthResponse.StatusCode -eq 200) {
                break
            }
        }
        catch {
            Write-Verbose ("Health probe attempt {0}/{1} failed: {2}" -f $attempt, $attempts, $_.Exception.Message)
        }
        Start-Sleep -Seconds 4
    }

    if ($null -eq $healthResponse -or $healthResponse.StatusCode -ne 200) {
        throw ("Health check failed: {0}" -f $healthUrl)
    }

    $cssResponse = Invoke-WebRequest -UseBasicParsing -Uri $cssUrl -Method Head -TimeoutSec 30
    $jsResponse = Invoke-WebRequest -UseBasicParsing -Uri $jsUrl -Method Head -TimeoutSec 30
    if ($cssResponse.StatusCode -ne 200) {
        throw ("Static CSS check failed ({0}): {1}" -f $cssResponse.StatusCode, $cssUrl)
    }
    if ($jsResponse.StatusCode -ne 200) {
        throw ("Static JS check failed ({0}): {1}" -f $jsResponse.StatusCode, $jsUrl)
    }

    Write-Ok ("Smoke tests passed: {0}; {1}; {2}" -f $healthUrl, $cssUrl, $jsUrl)
}
else {
    Write-Info "Skipping smoke tests as requested (-SkipSmokeTest)."
}
}
catch {
    if ($databaseUrlCutoverApplied -and -not [string]::IsNullOrWhiteSpace($currentDatabaseUrlForRollback)) {
        Write-Warning "Cloud SQL cutover failed after promoting the new DATABASE_URL. Restoring the previous database secret and attempting a rollback deploy."
        try {
            Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.DatabaseUrl -SecretValue $currentDatabaseUrlForRollback
            if (-not [string]::IsNullOrWhiteSpace($previousCloudSqlConnectionName)) {
                $rollbackDeployArgs = @(
                    "run", "deploy", $ServiceName,
                    "--project", $ProjectId,
                    "--region", $Region,
                    "--image", $imageRef,
                    "--service-account", $serviceAccountEmail,
                    "--port", "8080",
                    "--cpu", $CloudRunCpu,
                    "--memory", $CloudRunMemory,
                    "--concurrency", $CloudRunConcurrency,
                    "--ingress", $CloudRunIngress,
                    "--timeout", $CloudRunTimeoutSeconds,
                    "--min-instances", $CloudRunMinInstances,
                    "--max-instances", $CloudRunMaxInstances,
                    "--set-cloudsql-instances", $previousCloudSqlConnectionName,
                    "--vpc-connector", $VpcConnector,
                    "--vpc-egress", "private-ranges-only",
                    "--set-secrets", ($webSecretMap -join ","),
                    "--set-env-vars", $webEnvArg,
                    "--quiet"
                )
                if ($AllowUnauthenticated) {
                    $rollbackDeployArgs += "--allow-unauthenticated"
                }
                else {
                    $rollbackDeployArgs += "--no-allow-unauthenticated"
                }
                Invoke-Required -FilePath $gcloudCli -Arguments $rollbackDeployArgs -FailureMessage "Rollback Cloud Run deploy failed."
                Write-Ok ("Rollback Cloud Run deploy completed against previous Cloud SQL connection: {0}" -f $previousCloudSqlConnectionName)
            }
        }
        catch {
            Write-Warning ("Rollback attempt failed: {0}" -f $_.Exception.Message)
        }
    }
    throw
}

if (-not [string]::IsNullOrWhiteSpace($cloudSqlInstanceToDeleteAfterSuccessfulCutover)) {
    if ($cloudSqlInstanceToDeleteAfterSuccessfulCutover -eq $CloudSqlInstance) {
        throw ("Refusing to delete the active Cloud SQL instance '{0}'." -f $CloudSqlInstance)
    }

    Write-Step "Deleting replaced Cloud SQL instance after successful cutover"
    $deletedInstance = Remove-CloudSqlInstance -GcloudCli $gcloudCli -Project $ProjectId -InstanceName $cloudSqlInstanceToDeleteAfterSuccessfulCutover
    if ($deletedInstance) {
        $deletedCloudSqlInstance = $cloudSqlInstanceToDeleteAfterSuccessfulCutover
    }
}

if (-not $EnableRedis) {
    Write-Step "Removing existing Memorystore Redis instances"
    $redisInstancesToDelete = @(Get-RedisInstanceReferences -GcloudCli $gcloudCli -Project $ProjectId)
    if ($redisInstancesToDelete.Count -eq 0) {
        Write-Info "No Redis instances found to delete."
    }
    else {
        foreach ($redisInstanceRef in $redisInstancesToDelete) {
            $instanceName = [string]$redisInstanceRef.Name
            $instanceRegion = [string]$redisInstanceRef.Region
            $instanceState = [string]$redisInstanceRef.State

            if ($instanceState -eq "DELETING") {
                Write-Info ("Redis instance already deleting: {0} ({1})" -f $instanceName, $instanceRegion)
                continue
            }

            Write-Info ("Deleting Redis instance {0} in {1}" -f $instanceName, $instanceRegion)
            Invoke-Required -FilePath $gcloudCli -Arguments @(
                "redis", "instances", "delete", $instanceName,
                "--project", $ProjectId,
                "--region", $instanceRegion,
                "--quiet"
            ) -FailureMessage ("Failed deleting Redis instance {0} in {1}." -f $instanceName, $instanceRegion)
            Write-Ok ("Deleted Redis instance: {0} ({1})" -f $instanceName, $instanceRegion)
        }
    }
}

if ($ConfigureMonitoring) {
    Write-Step "Ensuring Cloud Monitoring uptime checks"
    try {
        $monitoringToken = Get-GcloudAccessToken -GcloudCli $gcloudCli
        $uptimeDisplayName = "tapne-web uptime ({0})" -f $ServiceName
        $uptimeConfigName = Set-UptimeCheck -Project $ProjectId -AccessToken $monitoringToken -DisplayName $uptimeDisplayName -CheckHost $uptimeCheckHostResolved -Path $uptimeCheckPathResolved
        $alertDisplayName = "tapne-web uptime alert ({0})" -f $ServiceName
        Set-UptimeAlertPolicy -Project $ProjectId -AccessToken $monitoringToken -DisplayName $alertDisplayName -UptimeCheckName $uptimeConfigName -NotificationChannels $MonitoringNotificationChannels
    }
    catch {
        Write-Warning ("Monitoring setup failed (deploy still succeeded): {0}" -f $_.Exception.Message)
    }
}
else {
    Write-Info "Skipping monitoring setup because -ConfigureMonitoring is false."
}

Write-Host ""
Write-Host "Deploy summary:" -ForegroundColor Cyan
Write-Host ("  Project:        {0}" -f $ProjectId)
Write-Host ("  Region:         {0}" -f $Region)
Write-Host ("  Service:        {0}" -f $ServiceName)
Write-Host ("  Image:          {0}" -f $imageRef)
Write-Host ("  Service URL:    {0}" -f $serviceUrl)
Write-Host ("  SQL Instance:   {0} ({1})" -f $CloudSqlInstance, $cloudSqlConnectionName)
if ($pendingCloudSqlMigration) {
    Write-Host ("  SQL Previous:   {0}" -f $previousCloudSqlInstance)
    if (-not [string]::IsNullOrWhiteSpace($cloudSqlMigrationExportUri)) {
        Write-Host ("  SQL Export:     {0}" -f $cloudSqlMigrationExportUri)
    }
}
if (-not [string]::IsNullOrWhiteSpace($deletedCloudSqlInstance)) {
    Write-Host ("  SQL Deleted:    {0}" -f $deletedCloudSqlInstance)
}
if ($EnableRedis) {
    Write-Host ("  Redis:          {0}:{1}" -f $redisHost, $redisPort)
}
else {
    Write-Host "  Redis:          disabled"
}
Write-Host ("  Bucket:         {0}" -f $bucketRef)
Write-Host ("  VPC Connector:  {0}" -f $VpcConnector)
Write-Host ("  Allowed Hosts:  {0}" -f $effectiveAllowedHosts)
Write-Host ("  CSRF Origins:   {0}" -f $effectiveCsrfTrustedOrigins)
Write-Host ("  Canonical Host: {0}" -f $resolvedCanonicalHost)
Write-Host ("  Smoke Base URL: {0}" -f $smokeBaseUrlResolved)
Write-Host ("  Uptime Target:  https://{0}{1}" -f $uptimeCheckHostResolved, $uptimeCheckPathResolved)
Write-Host ("  Concurrency:    {0}" -f $CloudRunConcurrency)
Write-Host ("  Ingress:        {0}" -f $CloudRunIngress)
Write-Host ("  Signed URLs:    {0}" -f (ConvertTo-BoolString -Value $EnableGcsSignedUrls))
Write-Host ("  SQL Private IP: {0}" -f (ConvertTo-BoolString -Value $UsePrivateCloudSqlIp))
Write-Host ""
Write-Ok "Cloud Run deployment workflow completed."
