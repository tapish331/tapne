<#
.SYNOPSIS
  Set up a custom domain front door for Cloud Run using an external HTTPS load balancer.

.DESCRIPTION
  Idempotent automation for Cloud Run custom-domain setup:
  - Enables required GCP APIs for load balancing and certificates
  - Creates/updates a Serverless NEG for the Cloud Run service
  - Creates/updates backend service, URL map, HTTPS proxy, static IP, and forwarding rule
  - Optionally creates HTTP(80) listener that redirects to HTTPS at the load balancer layer
  - Creates/uses a Google-managed SSL certificate for provided domain(s)
  - Optionally updates Cloudflare DNS records (A + CNAME) via API
  - Optionally hardens Cloud Run ingress to internal-and-cloud-load-balancing

  Supports both global and regional external Application Load Balancer modes.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateNotNullOrEmpty()]
    [string]$ProjectId = "tapne-487110",

    [ValidateNotNullOrEmpty()]
    [string]$Region = "asia-south1",

    [ValidateNotNullOrEmpty()]
    [string]$ServiceName = "tapne-web",

    [ValidateNotNullOrEmpty()]
    [string]$Domain = "tapnetravel.com",

    [string]$WwwDomain = "www.tapnetravel.com",

    [ValidateSet("global", "regional")]
    [string]$LoadBalancerScope = "global",

    [string]$ResourcePrefix = "",

    [ValidateNotNullOrEmpty()]
    [string]$Network = "default",

    [bool]$EnableHttp = $false,

    [bool]$UpdateCloudflareDns = $false,
    [string]$CloudflareApiToken = "",
    [string]$CloudflareZoneId = "",
    [bool]$CloudflareProxied = $false,

    [bool]$WaitForCertificate = $true,

    [ValidateRange(60, 7200)]
    [int]$CertificateWaitTimeoutSeconds = 1800,

    [ValidateRange(5, 120)]
    [int]$CertificatePollIntervalSeconds = 15,

    [bool]$HardenCloudRunIngress = $true,

    [ValidateSet("all", "internal", "internal-and-cloud-load-balancing")]
    [string]$CloudRunIngress = "internal-and-cloud-load-balancing",

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

function Get-LbScopeArgs {
    param(
        [string]$Scope,
        [string]$Region
    )
    if ($Scope -eq "global") {
        return @("--global")
    }
    return @("--region", $Region)
}

function ConvertTo-NameSegment {
    param([string]$Text)
    $normalized = ([string]$Text).ToLowerInvariant()
    $normalized = [regex]::Replace($normalized, "[^a-z0-9-]", "-")
    $normalized = [regex]::Replace($normalized, "-{2,}", "-")
    $normalized = $normalized.Trim("-")
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return "tapne"
    }
    return $normalized
}

function New-ResourceName {
    param(
        [string]$Base,
        [string]$Suffix,
        [int]$MaxLength = 63
    )

    $basePart = ConvertTo-NameSegment -Text $Base
    $suffixPart = ConvertTo-NameSegment -Text $Suffix

    if ([string]::IsNullOrWhiteSpace($suffixPart)) {
        if ($basePart.Length -le $MaxLength) {
            return $basePart
        }
        return $basePart.Substring(0, $MaxLength).TrimEnd("-")
    }

    $candidate = "{0}-{1}" -f $basePart, $suffixPart
    if ($candidate.Length -le $MaxLength) {
        return $candidate
    }

    $baseBudget = $MaxLength - $suffixPart.Length - 1
    if ($baseBudget -lt 1) {
        throw ("Unable to derive resource name within {0} characters for suffix '{1}'." -f $MaxLength, $suffixPart)
    }

    $truncatedBase = $basePart.Substring(0, [Math]::Min($baseBudget, $basePart.Length)).TrimEnd("-")
    if ([string]::IsNullOrWhiteSpace($truncatedBase)) {
        $truncatedBase = "x"
    }
    return ("{0}-{1}" -f $truncatedBase, $suffixPart)
}

function Invoke-CloudflareApi {
    param(
        [ValidateSet("GET", "POST", "PATCH", "DELETE")]
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $uri = "https://api.cloudflare.com/client/v4/zones/{0}{1}" -f $CloudflareZoneId, $Path
    $headers = @{
        Authorization = "Bearer $CloudflareApiToken"
    }

    if ($Method -eq "GET" -or $Method -eq "DELETE") {
        $response = Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
    }
    else {
        $jsonBody = if ($null -eq $Body) { "{}" } else { $Body | ConvertTo-Json -Depth 20 }
        $response = Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body $jsonBody
    }

    if ($null -eq $response) {
        throw ("Cloudflare API returned no response for {0} {1}." -f $Method, $Path)
    }

    if ($response.PSObject.Properties.Match("success").Count -gt 0 -and -not [bool]$response.success) {
        $errorMessages = @()
        if ($response.PSObject.Properties.Match("errors").Count -gt 0 -and $null -ne $response.errors) {
            foreach ($err in @($response.errors)) {
                if ($null -ne $err -and $err.PSObject.Properties.Match("message").Count -gt 0) {
                    $errorMessages += [string]$err.message
                }
            }
        }
        if ($errorMessages.Count -eq 0) {
            $errorMessages = @("Unknown Cloudflare API failure.")
        }
        throw ("Cloudflare API request failed ({0} {1}): {2}" -f $Method, $Path, ($errorMessages -join " | "))
    }

    return $response
}

function Set-CloudflareDnsRecord {
    param(
        [ValidateSet("A", "CNAME")]
        [string]$Type,
        [string]$Name,
        [string]$Content,
        [bool]$Proxied
    )

    $encodedType = [System.Uri]::EscapeDataString($Type)
    $encodedName = [System.Uri]::EscapeDataString($Name)
    $lookup = Invoke-CloudflareApi -Method "GET" -Path ("/dns_records?type={0}&name={1}&per_page=100" -f $encodedType, $encodedName)
    $records = @()
    if ($lookup.PSObject.Properties.Match("result").Count -gt 0 -and $null -ne $lookup.result) {
        $records = @($lookup.result)
    }

    if ($records.Count -gt 1) {
        Write-Warning ("Multiple Cloudflare records found for {0} {1}; updating the first match only." -f $Type, $Name)
    }

    $payload = @{
        type    = $Type
        name    = $Name
        content = $Content
        ttl     = 1
        proxied = $Proxied
    }

    if ($records.Count -gt 0) {
        $existing = $records[0]
        $recordId = [string]$existing.id
        if ([string]::IsNullOrWhiteSpace($recordId)) {
            throw ("Cloudflare record ID missing for {0} {1}." -f $Type, $Name)
        }
        Invoke-CloudflareApi -Method "PATCH" -Path ("/dns_records/{0}" -f $recordId) -Body $payload | Out-Null
        Write-Ok ("Updated Cloudflare DNS record: {0} {1} -> {2} (proxied={3})" -f $Type, $Name, $Content, (ConvertTo-BoolString -Value $Proxied))
        return
    }

    Invoke-CloudflareApi -Method "POST" -Path "/dns_records" -Body $payload | Out-Null
    Write-Ok ("Created Cloudflare DNS record: {0} {1} -> {2} (proxied={3})" -f $Type, $Name, $Content, (ConvertTo-BoolString -Value $Proxied))
}

function Get-FirstValueOrEmpty {
    param([string[]]$Lines)
    foreach ($line in @($Lines)) {
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            return ([string]$line).Trim()
        }
    }
    return ""
}

$gcloudCli = "gcloud"
$gcloudCmdCandidate = Get-Command "gcloud.cmd" -ErrorAction SilentlyContinue
if ($null -ne $gcloudCmdCandidate) {
    $gcloudCli = $gcloudCmdCandidate.Source
}

$Domain = ([string]$Domain).Trim().ToLowerInvariant()
$WwwDomain = ([string]$WwwDomain).Trim().ToLowerInvariant()
if ([string]::IsNullOrWhiteSpace($Domain)) {
    throw "Domain cannot be empty."
}

$domainList = New-Object System.Collections.Generic.List[string]
foreach ($candidate in @($Domain, $WwwDomain)) {
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        continue
    }
    if (-not $domainList.Contains($candidate)) {
        [void]$domainList.Add($candidate)
    }
}
if ($domainList.Count -eq 0) {
    throw "At least one domain must be provided."
}

if ([string]::IsNullOrWhiteSpace($ResourcePrefix)) {
    $ResourcePrefix = "{0}-{1}" -f $ServiceName, ($Domain -replace "\.", "-")
}
$ResourcePrefix = ConvertTo-NameSegment -Text $ResourcePrefix

$negName = New-ResourceName -Base $ResourcePrefix -Suffix "neg"
$backendServiceName = New-ResourceName -Base $ResourcePrefix -Suffix "bsvc"
$urlMapName = New-ResourceName -Base $ResourcePrefix -Suffix "umap"
$httpRedirectUrlMapName = New-ResourceName -Base $ResourcePrefix -Suffix "http-redirect-umap"
$certName = New-ResourceName -Base $ResourcePrefix -Suffix "cert"
$httpsProxyName = New-ResourceName -Base $ResourcePrefix -Suffix "https-proxy"
$httpProxyName = New-ResourceName -Base $ResourcePrefix -Suffix "http-proxy"
$addressName = New-ResourceName -Base $ResourcePrefix -Suffix "ip"
$httpsForwardingRuleName = New-ResourceName -Base $ResourcePrefix -Suffix "fr-443"
$httpForwardingRuleName = New-ResourceName -Base $ResourcePrefix -Suffix "fr-80"

$lbScopeArgs = Get-LbScopeArgs -Scope $LoadBalancerScope -Region $Region
$isGlobal = $LoadBalancerScope -eq "global"

Write-Verbose (
    "Run options => ProjectId={0}; Region={1}; ServiceName={2}; Domain={3}; WwwDomain={4}; Scope={5}; Prefix={6}; EnableHttp={7}; UpdateCloudflareDns={8}; CloudflareProxied={9}; WaitForCertificate={10}; HardenCloudRunIngress={11}; CloudRunIngress={12}" -f
    $ProjectId, $Region, $ServiceName, $Domain, $WwwDomain, $LoadBalancerScope, $ResourcePrefix, $EnableHttp, $UpdateCloudflareDns, $CloudflareProxied, $WaitForCertificate, $HardenCloudRunIngress, $CloudRunIngress
)

Write-Step "Preflight checks"
if (-not (Test-CommandExists -CommandName "gcloud")) {
    throw "gcloud CLI is not available on PATH."
}

Invoke-Required -FilePath $gcloudCli -Arguments @("--version") -FailureMessage "gcloud is installed but not functioning."

if ($UpdateCloudflareDns) {
    if ([string]::IsNullOrWhiteSpace($CloudflareApiToken)) {
        throw "Cloudflare API token is required when -UpdateCloudflareDns is true."
    }
    if ([string]::IsNullOrWhiteSpace($CloudflareZoneId)) {
        throw "Cloudflare zone ID is required when -UpdateCloudflareDns is true."
    }
}

$activeAccountResult = Invoke-External -FilePath $gcloudCli -Arguments @("auth", "list", "--filter=status:ACTIVE", "--format=value(account)")
$activeAccount = Get-FirstValueOrEmpty -Lines $activeAccountResult.Output
if ([string]::IsNullOrWhiteSpace($activeAccount)) {
    if ($SkipAuthLogin) {
        throw "No active gcloud account found and -SkipAuthLogin was set."
    }
    Write-Info "No active gcloud account detected. Launching interactive login..."
    Invoke-Required -FilePath $gcloudCli -Arguments @("auth", "login") -FailureMessage "gcloud auth login failed."

    $activeAccountResult = Invoke-External -FilePath $gcloudCli -Arguments @("auth", "list", "--filter=status:ACTIVE", "--format=value(account)")
    $activeAccount = Get-FirstValueOrEmpty -Lines $activeAccountResult.Output
}
if ([string]::IsNullOrWhiteSpace($activeAccount)) {
    throw "No active gcloud account found after login."
}
Write-Ok ("Using gcloud account: {0}" -f $activeAccount)

Invoke-Required -FilePath $gcloudCli -Arguments @("config", "set", "project", $ProjectId) -FailureMessage ("Failed to set gcloud project to '{0}'." -f $ProjectId)
Invoke-Required -FilePath $gcloudCli -Arguments @("config", "set", "run/region", $Region) -FailureMessage ("Failed to set gcloud run/region to '{0}'." -f $Region)
Invoke-Required -FilePath $gcloudCli -Arguments @("config", "set", "compute/region", $Region) -FailureMessage ("Failed to set gcloud compute/region to '{0}'." -f $Region)
Write-Ok ("gcloud project/region configured: {0}/{1}" -f $ProjectId, $Region)

$serviceUrl = Get-FirstValueOrEmpty -Lines (Invoke-Required -FilePath $gcloudCli -Arguments @(
    "run", "services", "describe", $ServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--format=value(status.url)"
) -FailureMessage ("Cloud Run service '{0}' not found." -f $ServiceName) -PassThru)

if ([string]::IsNullOrWhiteSpace($serviceUrl)) {
    throw "Cloud Run service URL is empty."
}
$runServiceHost = ([System.Uri]$serviceUrl).Host
Write-Ok ("Cloud Run service found: {0} ({1})" -f $ServiceName, $serviceUrl)

if ($ValidateOnly) {
    Write-Host ""
    Write-Host "Validate-only summary:" -ForegroundColor Cyan
    Write-Host ("  Scope:          {0}" -f $LoadBalancerScope)
    Write-Host ("  Domains:        {0}" -f ($domainList -join ", "))
    Write-Host ("  NEG:            {0}" -f $negName)
    Write-Host ("  Backend:        {0}" -f $backendServiceName)
    Write-Host ("  URL Map:        {0}" -f $urlMapName)
    Write-Host ("  Cert:           {0}" -f $certName)
    Write-Host ("  HTTPS Proxy:    {0}" -f $httpsProxyName)
    Write-Host ("  Address:        {0}" -f $addressName)
    Write-Host ("  ForwardingRule: {0}" -f $httpsForwardingRuleName)
    Write-Host ("  Ingress target: {0}" -f $CloudRunIngress)
    Write-Host ""
    Write-Ok "Validate-only mode complete. No cloud resources were changed."
    return
}

Write-Step "Ensuring required APIs are enabled"
Invoke-Required -FilePath $gcloudCli -Arguments @(
    "services", "enable",
    "run.googleapis.com",
    "compute.googleapis.com",
    "networkservices.googleapis.com",
    "certificatemanager.googleapis.com",
    "--project", $ProjectId
) -FailureMessage "Failed enabling one or more required APIs."
Write-Ok "Required APIs are enabled."

Write-Step "Ensuring serverless NEG for Cloud Run backend"
$negDescribe = Invoke-External -FilePath $gcloudCli -Arguments @(
    "compute", "network-endpoint-groups", "describe", $negName,
    "--project", $ProjectId,
    "--region", $Region,
    "--format=value(name)"
)
if ($negDescribe.ExitCode -ne 0) {
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "compute", "network-endpoint-groups", "create", $negName,
        "--project", $ProjectId,
        "--region", $Region,
        "--network-endpoint-type=serverless",
        "--cloud-run-service", $ServiceName
    ) -FailureMessage "Failed creating serverless NEG."
    Write-Ok ("Created serverless NEG: {0}" -f $negName)
}
else {
    Write-Ok ("Serverless NEG already exists: {0}" -f $negName)
}

Write-Step "Ensuring backend service and NEG attachment"
$backendDescribe = Invoke-External -FilePath $gcloudCli -Arguments (@(
    "compute", "backend-services", "describe", $backendServiceName,
    "--project", $ProjectId,
    "--format=json"
) + $lbScopeArgs)
if ($backendDescribe.ExitCode -ne 0) {
    Invoke-Required -FilePath $gcloudCli -Arguments (@(
        "compute", "backend-services", "create", $backendServiceName,
        "--project", $ProjectId,
        "--load-balancing-scheme=EXTERNAL_MANAGED",
        "--protocol=HTTP"
    ) + $lbScopeArgs) -FailureMessage "Failed creating backend service."
    Write-Ok ("Created backend service: {0}" -f $backendServiceName)
}
else {
    Write-Ok ("Backend service already exists: {0}" -f $backendServiceName)
}

$backendJsonRaw = (Invoke-Required -FilePath $gcloudCli -Arguments (@(
    "compute", "backend-services", "describe", $backendServiceName,
    "--project", $ProjectId,
    "--format=json"
) + $lbScopeArgs) -FailureMessage "Failed describing backend service." -PassThru) -join [Environment]::NewLine
$backendJson = $null
try {
    $backendJson = $backendJsonRaw | ConvertFrom-Json -Depth 100
}
catch {
    throw ("Failed parsing backend service JSON for '{0}': {1}" -f $backendServiceName, $_.Exception.Message)
}

$negAttached = $false
if ($null -ne $backendJson -and $backendJson.PSObject.Properties.Match("backends").Count -gt 0 -and $null -ne $backendJson.backends) {
    foreach ($entry in @($backendJson.backends)) {
        if ($null -eq $entry -or $entry.PSObject.Properties.Match("group").Count -eq 0) {
            continue
        }
        $groupRef = [string]$entry.group
        if ($groupRef -match ("/networkEndpointGroups/{0}$" -f [regex]::Escape($negName))) {
            $negAttached = $true
            break
        }
    }
}

if (-not $negAttached) {
    Invoke-Required -FilePath $gcloudCli -Arguments (@(
        "compute", "backend-services", "add-backend", $backendServiceName,
        "--project", $ProjectId
    ) + $lbScopeArgs + @(
        "--network-endpoint-group", $negName,
        "--network-endpoint-group-region", $Region
    )) -FailureMessage "Failed attaching serverless NEG to backend service."
    Write-Ok ("Attached NEG '{0}' to backend service '{1}'." -f $negName, $backendServiceName)
}
else {
    Write-Ok ("NEG '{0}' already attached to backend service '{1}'." -f $negName, $backendServiceName)
}

Write-Step "Ensuring URL map"
$urlMapDescribe = Invoke-External -FilePath $gcloudCli -Arguments (@(
    "compute", "url-maps", "describe", $urlMapName,
    "--project", $ProjectId,
    "--format=value(name)"
) + $lbScopeArgs)
if ($urlMapDescribe.ExitCode -ne 0) {
    Invoke-Required -FilePath $gcloudCli -Arguments (@(
        "compute", "url-maps", "create", $urlMapName,
        "--project", $ProjectId,
        "--default-service", $backendServiceName
    ) + $lbScopeArgs) -FailureMessage "Failed creating URL map."
    Write-Ok ("Created URL map: {0}" -f $urlMapName)
}
else {
    Write-Ok ("URL map already exists: {0}" -f $urlMapName)
}

Invoke-Required -FilePath $gcloudCli -Arguments (@(
    "compute", "url-maps", "set-default-service", $urlMapName,
    "--project", $ProjectId,
    "--default-service", $backendServiceName
) + $lbScopeArgs) -FailureMessage "Failed setting URL map default service."
Write-Ok ("URL map default service set to: {0}" -f $backendServiceName)

Write-Step "Ensuring managed SSL certificate"
$certScopeArgs = if ($isGlobal) { @("--global") } else { @("--region", $Region) }
$certDescribe = Invoke-External -FilePath $gcloudCli -Arguments (@(
    "compute", "ssl-certificates", "describe", $certName,
    "--project", $ProjectId,
    "--format=json"
) + $certScopeArgs)
if ($certDescribe.ExitCode -ne 0) {
    Invoke-Required -FilePath $gcloudCli -Arguments (@(
        "compute", "ssl-certificates", "create", $certName,
        "--project", $ProjectId,
        "--domains", ($domainList -join ",")
    ) + $certScopeArgs) -FailureMessage "Failed creating managed SSL certificate."
    Write-Ok ("Created managed SSL certificate: {0}" -f $certName)
}
else {
    $certJsonRaw = ($certDescribe.Output -join [Environment]::NewLine).Trim()
    $certJson = $null
    try {
        $certJson = $certJsonRaw | ConvertFrom-Json -Depth 100
    }
    catch {
        throw ("Failed parsing SSL certificate JSON for '{0}': {1}" -f $certName, $_.Exception.Message)
    }

    $existingManagedDomains = New-Object System.Collections.Generic.List[string]
    if ($null -ne $certJson -and $certJson.PSObject.Properties.Match("managed").Count -gt 0 -and $null -ne $certJson.managed) {
        if ($certJson.managed.PSObject.Properties.Match("domains").Count -gt 0 -and $null -ne $certJson.managed.domains) {
            foreach ($value in @($certJson.managed.domains)) {
                $candidateDomain = ([string]$value).Trim().ToLowerInvariant()
                if (-not [string]::IsNullOrWhiteSpace($candidateDomain) -and -not $existingManagedDomains.Contains($candidateDomain)) {
                    [void]$existingManagedDomains.Add($candidateDomain)
                }
            }
        }
    }

    $missingDomains = New-Object System.Collections.Generic.List[string]
    foreach ($requestedDomain in $domainList) {
        if (-not $existingManagedDomains.Contains($requestedDomain)) {
            [void]$missingDomains.Add($requestedDomain)
        }
    }
    if ($missingDomains.Count -gt 0) {
        throw ("Existing certificate '{0}' does not include required domain(s): {1}. Choose a different -ResourcePrefix/-cert name or replace the certificate." -f $certName, ($missingDomains -join ", "))
    }

    Write-Ok ("Managed SSL certificate already exists: {0}" -f $certName)
}

Write-Step "Ensuring HTTPS proxy"
$httpsProxyDescribe = Invoke-External -FilePath $gcloudCli -Arguments (@(
    "compute", "target-https-proxies", "describe", $httpsProxyName,
    "--project", $ProjectId,
    "--format=value(name)"
) + $lbScopeArgs)
if ($httpsProxyDescribe.ExitCode -ne 0) {
    $httpsCreateArgs = @(
        "compute", "target-https-proxies", "create", $httpsProxyName,
        "--project", $ProjectId,
        "--url-map", $urlMapName,
        "--ssl-certificates", $certName
    ) + $lbScopeArgs
    if ($isGlobal) {
        $httpsCreateArgs += @("--global-url-map", "--global-ssl-certificates")
    }
    else {
        $httpsCreateArgs += @("--url-map-region", $Region, "--ssl-certificates-region", $Region)
    }
    Invoke-Required -FilePath $gcloudCli -Arguments $httpsCreateArgs -FailureMessage "Failed creating HTTPS proxy."
    Write-Ok ("Created HTTPS proxy: {0}" -f $httpsProxyName)
}
else {
    Write-Ok ("HTTPS proxy already exists: {0}" -f $httpsProxyName)
}

$httpsUpdateArgs = @(
    "compute", "target-https-proxies", "update", $httpsProxyName,
    "--project", $ProjectId,
    "--url-map", $urlMapName,
    "--ssl-certificates", $certName
) + $lbScopeArgs
if ($isGlobal) {
    $httpsUpdateArgs += @("--global-url-map", "--global-ssl-certificates")
}
else {
    $httpsUpdateArgs += @("--url-map-region", $Region, "--ssl-certificates-region", $Region)
}
Invoke-Required -FilePath $gcloudCli -Arguments $httpsUpdateArgs -FailureMessage "Failed updating HTTPS proxy routing/certificate."
Write-Ok "HTTPS proxy wiring ensured."

Write-Step "Ensuring static external IP"
$addressScopeArgs = if ($isGlobal) { @("--global") } else { @("--region", $Region) }
$addressDescribe = Invoke-External -FilePath $gcloudCli -Arguments (@(
    "compute", "addresses", "describe", $addressName,
    "--project", $ProjectId,
    "--format=value(name)"
) + $addressScopeArgs)
if ($addressDescribe.ExitCode -ne 0) {
    Invoke-Required -FilePath $gcloudCli -Arguments (@(
        "compute", "addresses", "create", $addressName,
        "--project", $ProjectId
    ) + $addressScopeArgs) -FailureMessage "Failed creating static external IP."
    Write-Ok ("Created static external IP reservation: {0}" -f $addressName)
}
else {
    Write-Ok ("Static external IP already exists: {0}" -f $addressName)
}

$lbIp = Get-FirstValueOrEmpty -Lines (Invoke-Required -FilePath $gcloudCli -Arguments (@(
    "compute", "addresses", "describe", $addressName,
    "--project", $ProjectId,
    "--format=value(address)"
) + $addressScopeArgs) -FailureMessage "Failed reading static external IP." -PassThru)
if ([string]::IsNullOrWhiteSpace($lbIp)) {
    throw ("Failed resolving static external IP for address '{0}'." -f $addressName)
}
Write-Ok ("Load balancer IP: {0}" -f $lbIp)

Write-Step "Ensuring HTTPS forwarding rule"
$httpsRuleDescribe = Invoke-External -FilePath $gcloudCli -Arguments (@(
    "compute", "forwarding-rules", "describe", $httpsForwardingRuleName,
    "--project", $ProjectId,
    "--format=value(name)"
) + $lbScopeArgs)
if ($httpsRuleDescribe.ExitCode -ne 0) {
    $httpsRuleCreateArgs = @(
        "compute", "forwarding-rules", "create", $httpsForwardingRuleName,
        "--project", $ProjectId
    ) + $lbScopeArgs + @(
        "--load-balancing-scheme=EXTERNAL_MANAGED",
        "--address", $addressName,
        "--target-https-proxy", $httpsProxyName,
        "--ports", "443"
    )
    if ($isGlobal) {
        $httpsRuleCreateArgs += "--global-target-https-proxy"
    }
    else {
        $httpsRuleCreateArgs += @("--target-https-proxy-region", $Region, "--network", $Network)
    }

    Invoke-Required -FilePath $gcloudCli -Arguments $httpsRuleCreateArgs -FailureMessage "Failed creating HTTPS forwarding rule."
    Write-Ok ("Created HTTPS forwarding rule: {0}" -f $httpsForwardingRuleName)
}
else {
    Write-Ok ("HTTPS forwarding rule already exists: {0}" -f $httpsForwardingRuleName)
}

$httpsRuleSetTargetArgs = @(
    "compute", "forwarding-rules", "set-target", $httpsForwardingRuleName,
    "--project", $ProjectId
) + $lbScopeArgs + @(
    "--target-https-proxy", $httpsProxyName
)
if ($isGlobal) {
    $httpsRuleSetTargetArgs += "--global-target-https-proxy"
}
else {
    $httpsRuleSetTargetArgs += "--target-https-proxy-region"
    $httpsRuleSetTargetArgs += $Region
}
Invoke-Required -FilePath $gcloudCli -Arguments $httpsRuleSetTargetArgs -FailureMessage "Failed ensuring HTTPS forwarding rule target."
Write-Ok "HTTPS forwarding rule target ensured."

if ($EnableHttp) {
    Write-Step "Ensuring optional HTTP redirect URL map (HTTP -> HTTPS)"
    $httpRedirectUrlMapFile = New-TemporaryFile
    try {
        $httpRedirectUrlMapYaml = @(
            "kind: compute#urlMap",
            ("name: {0}" -f $httpRedirectUrlMapName),
            "defaultUrlRedirect:",
            "  httpsRedirect: true",
            "  redirectResponseCode: MOVED_PERMANENTLY_DEFAULT",
            "  stripQuery: false"
        ) -join "`n"
        Set-Content -Path $httpRedirectUrlMapFile.FullName -Value $httpRedirectUrlMapYaml -Encoding utf8NoBOM

        Invoke-Required -FilePath $gcloudCli -Arguments (@(
            "compute", "url-maps", "import", $httpRedirectUrlMapName,
            "--project", $ProjectId,
            "--source", $httpRedirectUrlMapFile.FullName
        ) + $lbScopeArgs) -FailureMessage "Failed creating/updating HTTP redirect URL map."
    }
    finally {
        Remove-Item -Path $httpRedirectUrlMapFile.FullName -Force -ErrorAction SilentlyContinue
    }
    Write-Ok ("HTTP redirect URL map ensured: {0}" -f $httpRedirectUrlMapName)

    Write-Step "Ensuring optional HTTP forwarding rule (port 80)"
    $httpProxyDescribe = Invoke-External -FilePath $gcloudCli -Arguments (@(
        "compute", "target-http-proxies", "describe", $httpProxyName,
        "--project", $ProjectId,
        "--format=value(name)"
    ) + $lbScopeArgs)
    if ($httpProxyDescribe.ExitCode -ne 0) {
        $httpProxyCreateArgs = @(
            "compute", "target-http-proxies", "create", $httpProxyName,
            "--project", $ProjectId,
            "--url-map", $httpRedirectUrlMapName
        ) + $lbScopeArgs
        if ($isGlobal) {
            $httpProxyCreateArgs += "--global-url-map"
        }
        else {
            $httpProxyCreateArgs += @("--url-map-region", $Region)
        }
        Invoke-Required -FilePath $gcloudCli -Arguments $httpProxyCreateArgs -FailureMessage "Failed creating HTTP proxy."
        Write-Ok ("Created HTTP proxy: {0}" -f $httpProxyName)
    }
    else {
        Write-Ok ("HTTP proxy already exists: {0}" -f $httpProxyName)
    }

    $httpProxyUpdateArgs = @(
        "compute", "target-http-proxies", "update", $httpProxyName,
        "--project", $ProjectId,
        "--url-map", $httpRedirectUrlMapName
    ) + $lbScopeArgs
    if ($isGlobal) {
        $httpProxyUpdateArgs += "--global-url-map"
    }
    else {
        $httpProxyUpdateArgs += @("--url-map-region", $Region)
    }
    Invoke-Required -FilePath $gcloudCli -Arguments $httpProxyUpdateArgs -FailureMessage "Failed updating HTTP proxy URL map."
    Write-Ok "HTTP proxy wiring ensured."

    $httpRuleDescribe = Invoke-External -FilePath $gcloudCli -Arguments (@(
        "compute", "forwarding-rules", "describe", $httpForwardingRuleName,
        "--project", $ProjectId,
        "--format=value(name)"
    ) + $lbScopeArgs)
    if ($httpRuleDescribe.ExitCode -ne 0) {
        $httpRuleCreateArgs = @(
            "compute", "forwarding-rules", "create", $httpForwardingRuleName,
            "--project", $ProjectId
        ) + $lbScopeArgs + @(
            "--load-balancing-scheme=EXTERNAL_MANAGED",
            "--address", $addressName,
            "--target-http-proxy", $httpProxyName,
            "--ports", "80"
        )
        if ($isGlobal) {
            $httpRuleCreateArgs += "--global-target-http-proxy"
        }
        else {
            $httpRuleCreateArgs += @("--target-http-proxy-region", $Region, "--network", $Network)
        }
        Invoke-Required -FilePath $gcloudCli -Arguments $httpRuleCreateArgs -FailureMessage "Failed creating HTTP forwarding rule."
        Write-Ok ("Created HTTP forwarding rule: {0}" -f $httpForwardingRuleName)
    }
    else {
        Write-Ok ("HTTP forwarding rule already exists: {0}" -f $httpForwardingRuleName)
    }

    $httpRuleSetTargetArgs = @(
        "compute", "forwarding-rules", "set-target", $httpForwardingRuleName,
        "--project", $ProjectId
    ) + $lbScopeArgs + @(
        "--target-http-proxy", $httpProxyName
    )
    if ($isGlobal) {
        $httpRuleSetTargetArgs += "--global-target-http-proxy"
    }
    else {
        $httpRuleSetTargetArgs += "--target-http-proxy-region"
        $httpRuleSetTargetArgs += $Region
    }
    Invoke-Required -FilePath $gcloudCli -Arguments $httpRuleSetTargetArgs -FailureMessage "Failed ensuring HTTP forwarding rule target."
    Write-Ok "HTTP forwarding rule target ensured."
}
else {
    Write-Info "Skipping HTTP port 80 forwarding rule (EnableHttp=false)."
}

if ($UpdateCloudflareDns) {
    Write-Step "Updating Cloudflare DNS records"
    Set-CloudflareDnsRecord -Type "A" -Name $Domain -Content $lbIp -Proxied $CloudflareProxied
    if (-not [string]::IsNullOrWhiteSpace($WwwDomain) -and $WwwDomain -ne $Domain) {
        Set-CloudflareDnsRecord -Type "CNAME" -Name $WwwDomain -Content $Domain -Proxied $CloudflareProxied
    }
    Write-Ok "Cloudflare DNS records upserted."
}
else {
    Write-Info "Skipping Cloudflare DNS changes (UpdateCloudflareDns=false)."
}

if ($WaitForCertificate) {
    Write-Step "Waiting for managed certificate to become ACTIVE"
    if (-not $UpdateCloudflareDns) {
        Write-Info "DNS updates are disabled in this run. Ensure your domain already points to the LB IP or certificate provisioning may time out."
    }

    $deadline = (Get-Date).AddSeconds($CertificateWaitTimeoutSeconds)
    $lastStatus = ""
    while ((Get-Date) -lt $deadline) {
        $certStatus = Get-FirstValueOrEmpty -Lines (Invoke-Required -FilePath $gcloudCli -Arguments (@(
            "compute", "ssl-certificates", "describe", $certName,
            "--project", $ProjectId,
            "--format=value(managed.status)"
        ) + $certScopeArgs) -FailureMessage "Failed reading managed certificate status." -PassThru)
        if ([string]::IsNullOrWhiteSpace($certStatus)) {
            $certStatus = "UNKNOWN"
        }
        if ($certStatus -ne $lastStatus) {
            Write-Info ("Managed certificate status: {0}" -f $certStatus)
            $lastStatus = $certStatus
        }

        if ($certStatus -eq "ACTIVE") {
            Write-Ok ("Managed certificate is ACTIVE: {0}" -f $certName)
            break
        }
        if ($certStatus -eq "PROVISIONING_FAILED" -or $certStatus -eq "FAILED") {
            throw ("Managed certificate provisioning failed for '{0}'. Check DNS A/CNAME and certificate/domain validation status in Cloud Console." -f $certName)
        }

        Start-Sleep -Seconds $CertificatePollIntervalSeconds
    }

    if ($lastStatus -ne "ACTIVE") {
        throw ("Timed out after {0}s waiting for certificate '{1}' to become ACTIVE." -f $CertificateWaitTimeoutSeconds, $certName)
    }
}
else {
    Write-Info "Skipping certificate readiness wait (WaitForCertificate=false)."
}

if ($HardenCloudRunIngress) {
    Write-Step "Hardening Cloud Run ingress"
    Invoke-Required -FilePath $gcloudCli -Arguments @(
        "run", "services", "update", $ServiceName,
        "--project", $ProjectId,
        "--region", $Region,
        "--ingress", $CloudRunIngress,
        "--quiet"
    ) -FailureMessage "Failed updating Cloud Run ingress."
    Write-Ok ("Cloud Run ingress set to: {0}" -f $CloudRunIngress)
}
else {
    Write-Info "Skipping Cloud Run ingress hardening (HardenCloudRunIngress=false)."
}

Write-Host ""
Write-Host "Custom domain setup summary:" -ForegroundColor Cyan
Write-Host ("  Project:              {0}" -f $ProjectId)
Write-Host ("  Region:               {0}" -f $Region)
Write-Host ("  Scope:                {0}" -f $LoadBalancerScope)
Write-Host ("  Service:              {0}" -f $ServiceName)
Write-Host ("  Cloud Run URL:        {0}" -f $serviceUrl)
Write-Host ("  Domains:              {0}" -f ($domainList -join ", "))
Write-Host ("  External IP:          {0}" -f $lbIp)
Write-Host ("  NEG:                  {0}" -f $negName)
Write-Host ("  Backend service:      {0}" -f $backendServiceName)
Write-Host ("  URL map:              {0}" -f $urlMapName)
Write-Host ("  SSL cert:             {0}" -f $certName)
Write-Host ("  HTTPS proxy:          {0}" -f $httpsProxyName)
Write-Host ("  HTTPS forwarding rule:{0}" -f $httpsForwardingRuleName)
if ($EnableHttp) {
    Write-Host ("  HTTP proxy:           {0}" -f $httpProxyName)
    Write-Host ("  HTTP forwarding rule: {0}" -f $httpForwardingRuleName)
}
Write-Host ("  Cloudflare DNS set:   {0}" -f (ConvertTo-BoolString -Value $UpdateCloudflareDns))
Write-Host ("  Ingress hardened:     {0}" -f (ConvertTo-BoolString -Value $HardenCloudRunIngress))
Write-Host ""
Write-Host "Next deploy command (host/csrf + monitoring/smoke on custom domain):" -ForegroundColor Cyan

$allowedHostList = New-Object System.Collections.Generic.List[string]
foreach ($candidateHost in @($Domain, $WwwDomain, $runServiceHost)) {
    if ([string]::IsNullOrWhiteSpace($candidateHost)) {
        continue
    }
    if (-not $allowedHostList.Contains($candidateHost)) {
        [void]$allowedHostList.Add($candidateHost)
    }
}

$csrfOriginList = New-Object System.Collections.Generic.List[string]
foreach ($candidateHost in @($Domain, $WwwDomain, $runServiceHost)) {
    if ([string]::IsNullOrWhiteSpace($candidateHost)) {
        continue
    }
    $origin = "https://{0}" -f $candidateHost
    if (-not $csrfOriginList.Contains($origin)) {
        [void]$csrfOriginList.Add($origin)
    }
}

foreach ($line in @(
    ".\infra\deploy-cloud-run.ps1",
    "  -BuildAndPushImage:`$false",
    "  -SkipMigrations",
    ("  -CloudRunIngress ""{0}""" -f $CloudRunIngress),
    ("  -DjangoAllowedHosts ""{0}""" -f ($allowedHostList -join ",")),
    ("  -CsrfTrustedOrigins ""{0}""" -f ($csrfOriginList -join ",")),
    ("  -SmokeBaseUrl ""https://{0}""" -f $Domain),
    ("  -UptimeCheckHost ""{0}""" -f $Domain)
)) {
    Write-Host $line
}
Write-Host ""
Write-Ok "Custom domain front door setup completed."
