param(
    [string]$HostName = $env:MYSTMON_BUILD_HOST,
    [string]$UserName = $env:MYSTMON_BUILD_USER,
    [string]$RemoteDir = $env:MYSTMON_DEV_DIR,
    [switch]$Start
)

if ([string]::IsNullOrWhiteSpace($HostName)) {
    $HostName = "192.168.1.72"
}

if ([string]::IsNullOrWhiteSpace($RemoteDir)) {
    $RemoteDir = "/mnt/ssd/mystmon-dev"
}

$target = $HostName
if (-not [string]::IsNullOrWhiteSpace($UserName)) {
    $target = "$UserName@$HostName"
}

$archive = Join-Path $env:TEMP "mystmon-build.tar"
git archive --format=tar --output=$archive HEAD
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create git archive. Commit or stage the build inputs first."
}

ssh $target "mkdir -p $RemoteDir"
if ($LASTEXITCODE -ne 0) {
    throw "SSH connection failed for $target."
}

scp $archive "${target}:$RemoteDir/mystmon-build.tar"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to copy archive to $target."
}

ssh $target "cd $RemoteDir && tar -xf mystmon-build.tar && if [ ! -f .env ]; then cp .env.example .env; fi && docker compose -f docker-compose.yml -f docker-compose.dev.yml build mystmon-dev"
if ($LASTEXITCODE -ne 0) {
    throw "Remote Docker dev build failed on $target."
}

if ($Start) {
    ssh $target "cd $RemoteDir && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d mystmon-dev && MYSTMON_BASE_URL=http://127.0.0.1:8073 MYSTMON_DATA_DIR=$RemoteDir/data ./ops/validate-mystmon.sh"
    if ($LASTEXITCODE -ne 0) {
        throw "Remote Docker start failed on $target."
    }
}

Write-Host "MystMon install completed on $target in $RemoteDir"
