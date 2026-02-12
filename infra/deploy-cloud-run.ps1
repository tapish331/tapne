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

function Test-CommandExists {
    param([string]$CommandName)
    return [bool](Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function Invoke-External {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    Write-Verbose ("Running: {0} {1}" -f $FilePath, ($Arguments -join " "))
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
        [switch]$PassThru
    )

    $result = Invoke-External -FilePath $FilePath -Arguments $Arguments
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
    "Run options => ProjectId={0}; Region={1}; ServiceName={2}; ImageTag={3}; BucketName={4}; BuildAndPushImage={5}; SkipMigrations={6}; RunBootstrapRuntime={7}; SkipSmokeTest={8}; PrivateCloudSqlIp={9}; CloudRunConcurrency={10}; GcsSignedUrls={11}; ConfigureMonitoring={12}" -f
    $ProjectId, $Region, $ServiceName, $ImageTag, $BucketName, $BuildAndPushImage, $SkipMigrations, $RunBootstrapRuntime, $SkipSmokeTest, $UsePrivateCloudSqlIp, $CloudRunConcurrency, $EnableGcsSignedUrls, $ConfigureMonitoring
)

Write-Step "Preflight checks"
if (-not (Test-CommandExists -CommandName "gcloud")) {
    throw "gcloud CLI is not available on PATH."
}
if (-not (Test-CommandExists -CommandName "docker")) {
    throw "Docker CLI is not available on PATH."
}

Invoke-Required -FilePath $gcloudCli -Arguments @("--version") -FailureMessage "gcloud is installed but not functioning."
Invoke-Required -FilePath "docker" -Arguments @("version", "--format", "{{.Server.Version}}") -FailureMessage "Docker daemon is not reachable. Start Docker Desktop and retry."

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
    "SECURE_SSL_REDIRECT=true",
    "SESSION_COOKIE_SECURE=true",
    "CSRF_COOKIE_SECURE=true",
    "DJANGO_ALLOWED_HOSTS=.run.app",
    "CSRF_TRUSTED_ORIGINS=https://*.run.app"
)
$webEnv = @($baseEnv + @("COLLECTSTATIC_ON_BOOT=true"))
$jobEnv = @($baseEnv + @("COLLECTSTATIC_ON_BOOT=false"))
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
        "--set-env-vars", ($jobEnv -join ","),
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
    "--timeout", $CloudRunTimeoutSeconds,
    "--min-instances", $CloudRunMinInstances,
    "--max-instances", $CloudRunMaxInstances,
    "--add-cloudsql-instances", $cloudSqlConnectionName,
    "--vpc-connector", $VpcConnector,
    "--vpc-egress", "private-ranges-only",
    "--set-secrets", ($secretMap -join ","),
    "--set-env-vars", ($webEnv -join ","),
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

Write-Step "Tightening host/csrf envs to concrete run.app host"
Invoke-Required -FilePath $gcloudCli -Arguments @(
    "run", "services", "update", $ServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--update-env-vars", ("DJANGO_ALLOWED_HOSTS={0},CSRF_TRUSTED_ORIGINS=https://{0}" -f $serviceHost),
    "--quiet"
) -FailureMessage "Failed tightening host/csrf env vars."

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
        "--set-env-vars", ($jobEnv -join ","),
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

    $healthUrl = "{0}/runtime/health/" -f $serviceUrl.TrimEnd("/")
    $cssUrl = "{0}/static/css/tapne.css" -f $serviceUrl.TrimEnd("/")
    $jsUrl = "{0}/static/js/tapne-ui.js" -f $serviceUrl.TrimEnd("/")

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

    Write-Ok "Smoke tests passed: /runtime/health + static CSS/JS."
}
else {
    Write-Info "Skipping smoke tests as requested (-SkipSmokeTest)."
}

if ($ConfigureMonitoring) {
    Write-Step "Ensuring Cloud Monitoring uptime checks"
    try {
        $monitoringToken = Get-GcloudAccessToken -GcloudCli $gcloudCli
        $uptimeDisplayName = "tapne-web uptime ({0})" -f $ServiceName
        $uptimeConfigName = Set-UptimeCheck -Project $ProjectId -AccessToken $monitoringToken -DisplayName $uptimeDisplayName -CheckHost $serviceHost -Path "/runtime/health/"
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
Write-Host ("  Concurrency:    {0}" -f $CloudRunConcurrency)
Write-Host ("  Signed URLs:    {0}" -f (ConvertTo-BoolString -Value $EnableGcsSignedUrls))
Write-Host ("  SQL Private IP: {0}" -f (ConvertTo-BoolString -Value $UsePrivateCloudSqlIp))
Write-Host ""
Write-Ok "Cloud Run deployment workflow completed."
