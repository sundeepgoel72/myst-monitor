param(
    [string]$Image = $env:MYSTMON_IMAGE,
    [string]$Tag = "0.73"
)

if ([string]::IsNullOrWhiteSpace($Image)) {
    throw "Set MYSTMON_IMAGE, for example docker.io/<user>/mystmon:<tag>"
}

docker build -t $Image .
if ($LASTEXITCODE -ne 0) {
    throw "Docker build failed."
}

docker push $Image
if ($LASTEXITCODE -ne 0) {
    throw "Docker push failed. Check docker login and registry permissions."
}

Write-Host "Published $Image"
