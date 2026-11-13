# Shared helpers for the Windows scripts (dot-sourced). Safe under $ErrorActionPreference='Stop'
# in Windows PowerShell 5.1: native stderr is never redirected while 'Stop' is active.
function Invoke-Docker {
  $prev = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & docker @args 2>&1 | Out-Null } finally { $ErrorActionPreference = $prev }
  return $LASTEXITCODE
}

function Test-DockerDaemon { return ((Invoke-Docker info) -eq 0) }

function Assert-Docker {
  param([switch]$StartDocker)
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host 'Docker is not installed or not on PATH. Install Docker Desktop first.'
    exit 1
  }
  if (Test-DockerDaemon) { return }
  $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
  if ($StartDocker -and (Test-Path $exe)) {
    Write-Host 'Starting Docker Desktop (waiting up to 90s)...'
    Start-Process $exe
    for ($i = 0; $i -lt 30; $i++) {
      Start-Sleep -Seconds 3
      if (Test-DockerDaemon) { return }
    }
  }
  Write-Host "Docker Desktop isn't running. Start it, wait until it says Engine running, then re-run."
  if (-not $StartDocker -and (Test-Path $exe)) { Write-Host 'Tip: re-run with -StartDocker to launch it automatically.' }
  exit 1
}
