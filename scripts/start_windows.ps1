# Start FinAlly. Usage: scripts\start_windows.ps1 [-Build] [-Open] [-StartDocker]
param([switch]$Build, [switch]$Open, [switch]$StartDocker)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker_check.ps1')
Set-Location (Join-Path $PSScriptRoot '..')
$name = 'finally'; $image = 'finally'; $volume = 'finally-data'

Assert-Docker -StartDocker:$StartDocker

if (-not (Test-Path .env) -and (Test-Path .env.example)) {
  Copy-Item .env.example .env
  Write-Host 'Created .env from .env.example (edit it to add OPENROUTER_API_KEY).'
}
$exists = ((Invoke-Docker image inspect $image) -eq 0)
if ($Build -or -not $exists) {
  if ((Invoke-Docker build -t $image .) -ne 0) { Write-Host 'docker build failed (run "docker build -t finally ." to see the error).'; exit 1 }
}
Invoke-Docker rm -f $name | Out-Null
if ((Invoke-Docker run -d --name $name -v "${volume}:/app/db" -p 8000:8000 --env-file .env $image) -ne 0) {
  Write-Host 'docker run failed (is port 8000 in use?).'; exit 1
}
$url = 'http://localhost:8000'
Write-Host "FinAlly running at $url"
if ($Open) { Start-Process $url }
