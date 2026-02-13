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
    [string]$CloudSqlTier = "db-custom-1-3840",

    [ValidateRange(10, 65536)]
    [int]$CloudSqlStorageGb = 20,

    [ValidateNotNullOrEmpty()]
    [string]$CloudSqlDatabaseVersion = "POSTGRES_15",

    [ValidateNotNullOrEmpty()]
    [string]$RedisInstance = "tapne-redis",

    [ValidateRange(1, 300)]
    [int]$RedisSizeGb = 1,

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
    [bool]$AutoFixGcsDependency = $true,
    [bool]$AllowUnauthenticated = $true,

    [string[]]$DjangoAllowedHosts = @(),
    [string[]]$CsrfTrustedOrigins = @(),
    [string]$CanonicalHost = "",

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
    RedisUrl          = "tapne-redis-url"
    CeleryBrokerUrl   = "tapne-celery-broker-url"
    CeleryResultStore = "tapne-celery-result-backend"
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
    "Run options => ProjectId={0}; Region={1}; ServiceName={2}; ImageTag={3}; BucketName={4}; BuildAndPushImage={5}; SkipMigrations={6}; RunBootstrapRuntime={7}; SkipSmokeTest={8}; PrivateCloudSqlIp={9}; CloudRunConcurrency={10}; CloudRunIngress={11}; GcsSignedUrls={12}; ConfigureMonitoring={13}; DjangoAllowedHosts={14}; CsrfTrustedOrigins={15}; CanonicalHost={16}; SmokeBaseUrl={17}; UptimeCheckHost={18}; UptimeCheckPath={19}" -f
    $ProjectId, $Region, $ServiceName, $ImageTag, $BucketName, $BuildAndPushImage, $SkipMigrations, $RunBootstrapRuntime, $SkipSmokeTest, $UsePrivateCloudSqlIp, $CloudRunConcurrency, $CloudRunIngress, $EnableGcsSignedUrls, $ConfigureMonitoring, ($DjangoAllowedHosts -join ","), ($CsrfTrustedOrigins -join ","), $CanonicalHost, $SmokeBaseUrl, $UptimeCheckHost, $UptimeCheckPath
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
$sqlDescribe = Invoke-External -FilePath $gcloudCli -Arguments @(
    "sql", "instances", "describe", $CloudSqlInstance,
    "--project", $ProjectId,
    "--format=value(name)"
)
if ($sqlDescribe.ExitCode -ne 0) {
    $sqlCreateArgs = @(
        "sql", "instances", "create", $CloudSqlInstance,
        "--project", $ProjectId,
        "--region", $Region,
        "--database-version", $CloudSqlDatabaseVersion,
        "--tier", $CloudSqlTier,
        "--storage-size", $CloudSqlStorageGb,
        "--storage-auto-increase"
    )
    if ($UsePrivateCloudSqlIp) {
        $sqlCreateArgs += @(
            "--network", $Network,
            "--no-assign-ip"
        )
    }
    else {
        $sqlCreateArgs += "--assign-ip"
    }
    if ($EnableCloudSqlBackups) {
        $sqlCreateArgs += @("--backup-start-time", $CloudSqlBackupStartTime)
    }
    else {
        $sqlCreateArgs += "--no-backup"
    }
    if ($EnableCloudSqlPointInTimeRecovery) {
        $sqlCreateArgs += "--enable-point-in-time-recovery"
    }
    $sqlCreateArgs += "--quiet"

    Invoke-RequiredWithCloudSqlWait -GcloudCli $gcloudCli -Arguments $sqlCreateArgs -Project $ProjectId -FailureMessage "Failed creating Cloud SQL instance."
    Write-Ok ("Created Cloud SQL instance: {0}" -f $CloudSqlInstance)
}
else {
    Write-Ok ("Cloud SQL instance already exists: {0}" -f $CloudSqlInstance)
    $currentPrivateNetwork = ([string](Invoke-Required -FilePath $gcloudCli -Arguments @(
        "sql", "instances", "describe", $CloudSqlInstance,
        "--project", $ProjectId,
        "--format=value(settings.ipConfiguration.privateNetwork)"
    ) -FailureMessage "Failed reading Cloud SQL private network setting." -PassThru | Select-Object -First 1)).Trim()
    $currentIpv4Enabled = ([string](Invoke-Required -FilePath $gcloudCli -Arguments @(
        "sql", "instances", "describe", $CloudSqlInstance,
        "--project", $ProjectId,
        "--format=value(settings.ipConfiguration.ipv4Enabled)"
    ) -FailureMessage "Failed reading Cloud SQL public IP setting." -PassThru | Select-Object -First 1)).Trim().ToLowerInvariant()
    $currentBackupEnabled = ([string](Invoke-Required -FilePath $gcloudCli -Arguments @(
        "sql", "instances", "describe", $CloudSqlInstance,
        "--project", $ProjectId,
        "--format=value(settings.backupConfiguration.enabled)"
    ) -FailureMessage "Failed reading Cloud SQL backup setting." -PassThru | Select-Object -First 1)).Trim().ToLowerInvariant()
    $currentBackupStart = ([string](Invoke-Required -FilePath $gcloudCli -Arguments @(
        "sql", "instances", "describe", $CloudSqlInstance,
        "--project", $ProjectId,
        "--format=value(settings.backupConfiguration.startTime)"
    ) -FailureMessage "Failed reading Cloud SQL backup start time." -PassThru | Select-Object -First 1)).Trim()
    $currentPitrEnabled = ([string](Invoke-Required -FilePath $gcloudCli -Arguments @(
        "sql", "instances", "describe", $CloudSqlInstance,
        "--project", $ProjectId,
        "--format=value(settings.backupConfiguration.pointInTimeRecoveryEnabled)"
    ) -FailureMessage "Failed reading Cloud SQL PITR setting." -PassThru | Select-Object -First 1)).Trim().ToLowerInvariant()

    $needsPatch = $false
    if ($UsePrivateCloudSqlIp) {
        if ([string]::IsNullOrWhiteSpace($currentPrivateNetwork) -or $currentIpv4Enabled -ne "false") {
            $needsPatch = $true
        }
    }
    elseif ($currentIpv4Enabled -ne "true") {
        $needsPatch = $true
    }
    if ($EnableCloudSqlBackups) {
        if ($currentBackupEnabled -ne "true" -or $currentBackupStart -ne $CloudSqlBackupStartTime) {
            $needsPatch = $true
        }
    }
    elseif ($currentBackupEnabled -ne "false") {
        $needsPatch = $true
    }
    if ($EnableCloudSqlPointInTimeRecovery -and $currentPitrEnabled -ne "true") {
        $needsPatch = $true
    }

    if ($needsPatch) {
        $sqlPatchArgs = @(
            "sql", "instances", "patch", $CloudSqlInstance,
            "--project", $ProjectId
        )
        if ($UsePrivateCloudSqlIp) {
            $sqlPatchArgs += @(
                "--network", $Network,
                "--no-assign-ip"
            )
        }
        else {
            $sqlPatchArgs += "--assign-ip"
        }
        if ($EnableCloudSqlBackups) {
            $sqlPatchArgs += @("--backup-start-time", $CloudSqlBackupStartTime)
        }
        else {
            $sqlPatchArgs += "--no-backup"
        }
        if ($EnableCloudSqlPointInTimeRecovery) {
            $sqlPatchArgs += "--enable-point-in-time-recovery"
        }
        $sqlPatchArgs += "--quiet"

        Invoke-RequiredWithCloudSqlWait -GcloudCli $gcloudCli -Arguments $sqlPatchArgs -Project $ProjectId -FailureMessage "Failed applying Cloud SQL hardening settings."
        Write-Ok "Cloud SQL hardening settings ensured (network/IP/backup/PITR)."
    }
    else {
        Write-Ok "Cloud SQL hardening settings already match desired state."
    }
}

$dbList = Invoke-Required -FilePath $gcloudCli -Arguments @(
    "sql", "databases", "list",
    "--instance", $CloudSqlInstance,
    "--project", $ProjectId,
    "--format=value(name)"
) -FailureMessage "Failed listing Cloud SQL databases." -PassThru

if ($dbList -contains $CloudSqlDatabase) {
    Write-Ok ("Database already exists: {0}" -f $CloudSqlDatabase)
}
else {
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "sql", "databases", "create", $CloudSqlDatabase,
        "--instance", $CloudSqlInstance,
        "--project", $ProjectId,
        "--quiet"
    ) -FailureMessage "Failed creating Cloud SQL database."
    Write-Ok ("Created database: {0}" -f $CloudSqlDatabase)
}

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

$userList = Invoke-Required -FilePath $gcloudCli -Arguments @(
    "sql", "users", "list",
    "--instance", $CloudSqlInstance,
    "--project", $ProjectId,
    "--format=value(name)"
) -FailureMessage "Failed listing Cloud SQL users." -PassThru

if ($userList -contains $CloudSqlUser) {
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "sql", "users", "set-password", $CloudSqlUser,
        "--instance", $CloudSqlInstance,
        "--project", $ProjectId,
        "--password", $dbPassword,
        "--quiet"
    ) -FailureMessage ("Failed setting password for user '{0}'." -f $CloudSqlUser)
    Write-Ok ("Updated password for DB user: {0}" -f $CloudSqlUser)
}
else {
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "sql", "users", "create", $CloudSqlUser,
        "--instance", $CloudSqlInstance,
        "--project", $ProjectId,
        "--password", $dbPassword,
        "--quiet"
    ) -FailureMessage ("Failed creating DB user '{0}'." -f $CloudSqlUser)
    Write-Ok ("Created DB user: {0}" -f $CloudSqlUser)
}

$cloudSqlConnectionName = (Invoke-Required -FilePath $gcloudCli -Arguments @(
    "sql", "instances", "describe", $CloudSqlInstance,
    "--project", $ProjectId,
    "--format=value(connectionName)"
) -FailureMessage "Failed reading Cloud SQL connection name." -PassThru | Select-Object -First 1).Trim()
if ([string]::IsNullOrWhiteSpace($cloudSqlConnectionName)) {
    throw "Cloud SQL connection name is empty."
}
Write-Ok ("Cloud SQL connection: {0}" -f $cloudSqlConnectionName)

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
if ([string]::IsNullOrWhiteSpace($existingDjangoSecret)) {
    $existingDjangoSecret = (python -c "import secrets; print(secrets.token_urlsafe(48))")
}

$databaseUrl = "postgresql://{0}:{1}@/{2}?host=/cloudsql/{3}" -f $CloudSqlUser, $dbPassword, $CloudSqlDatabase, $cloudSqlConnectionName
$redisUrl = "redis://{0}:{1}/0" -f $redisHost, $redisPort
$celeryBrokerUrl = "redis://{0}:{1}/1" -f $redisHost, $redisPort
$celeryResultBackend = "redis://{0}:{1}/2" -f $redisHost, $redisPort

Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.SecretKey -SecretValue $existingDjangoSecret
Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.DatabaseUrl -SecretValue $databaseUrl
Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.RedisUrl -SecretValue $redisUrl
Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.CeleryBrokerUrl -SecretValue $celeryBrokerUrl
Set-SecretValue -GcloudCli $gcloudCli -Project $ProjectId -SecretName $secretNames.CeleryResultStore -SecretValue $celeryResultBackend

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
$secretMap = @(
    ("SECRET_KEY={0}:latest" -f $secretNames.SecretKey),
    ("DATABASE_URL={0}:latest" -f $secretNames.DatabaseUrl),
    ("REDIS_URL={0}:latest" -f $secretNames.RedisUrl),
    ("CELERY_BROKER_URL={0}:latest" -f $secretNames.CeleryBrokerUrl),
    ("CELERY_RESULT_BACKEND={0}:latest" -f $secretNames.CeleryResultStore)
)

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
        "--set-secrets", ($secretMap -join ","),
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
    "--add-cloudsql-instances", $cloudSqlConnectionName,
    "--vpc-connector", $VpcConnector,
    "--vpc-egress", "private-ranges-only",
    "--set-secrets", ($secretMap -join ","),
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
        "--set-secrets", ($secretMap -join ","),
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
Write-Host ("  Redis:          {0}:{1}" -f $redisHost, $redisPort)
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
