# Downloads the ffmpeg build that gets bundled into Squish.exe (gyan.dev "essentials", GPL).
# Run from anywhere: powershell -ExecutionPolicy Bypass -File desktop\get_ffmpeg.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin = Join-Path $here "bin"
New-Item -ItemType Directory -Force $bin | Out-Null
$zip = Join-Path $env:TEMP "ffmpeg-release-essentials.zip"
Write-Host "Downloading ffmpeg (about 115 MB)..."
Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zip
$tmp = Join-Path $env:TEMP "ffmpeg-extract"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
Expand-Archive -Path $zip -DestinationPath $tmp
$exe = Get-ChildItem -Path $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1
Copy-Item $exe.FullName (Join-Path $bin "ffmpeg.exe") -Force
$lic = Get-ChildItem -Path $tmp -Recurse -Filter LICENSE | Select-Object -First 1
if ($lic) { Copy-Item $lic.FullName (Join-Path $bin "FFMPEG_LICENSE.txt") -Force }
Remove-Item -Recurse -Force $tmp
Remove-Item -Force $zip
Write-Host "ffmpeg.exe is in $bin"
