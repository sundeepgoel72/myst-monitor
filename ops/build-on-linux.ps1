param(
    [string]$HostName = $env:MYSTMON_BUILD_HOST,
    [string]$UserName = $env:MYSTMON_BUILD_USER,
    [string]$RemoteDir = $env:MYSTMON_REMOTE_DIR,
    [switch]$Start
)

if ([string]::IsNullOrWhiteSpace($HostName)) {
    throw "Set MYSTMON_BUILD_HOST to the SSH host."
}

if ([string]::IsNullOrWhiteSpace($RemoteDir)) {
    throw "Set MYSTMON_REMOTE_DIR to the remote install path."
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

ssh $target "cd $RemoteDir && tar -xf mystmon-build.tar && if [ ! -f .env ]; then cp .env.example .env; fi && if [ \"${env:MYSTMON_SKIP_PULL}\" != '1' ]; then docker compose pull mystmon-prod; fi"
if ($LASTEXITCODE -ne 0) {
    throw "Remote Docker image pull failed on $target."
}

if ($Start) {
    ssh $target "cd $RemoteDir && docker compose up -d mystmon-prod && for i in 1 2 3 4 5 6 7 8 9 10; do status=\$(docker inspect -f '{{.State.Health.Status}}' mystmon-prod 2>/dev/null || true); if [ \"\$status\" = healthy ]; then break; fi; if [ \"\$status\" = unhealthy ]; then docker compose ps mystmon-prod; exit 1; fi; sleep 3; done"
    if ($LASTEXITCODE -ne 0) {
        throw "Remote Docker start failed on $target."
    }
}

Write-Host "MystMon install completed on $target in $RemoteDir"
