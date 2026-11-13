# Stop and remove the container; the finally-data volume is kept.
param([switch]$StartDocker)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker_check.ps1')
Assert-Docker -StartDocker:$StartDocker
Invoke-Docker rm -f finally | Out-Null
Write-Host 'FinAlly stopped (volume finally-data preserved).'
