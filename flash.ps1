param([string]$Port)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if(!$Port){$Port=Read-Host 'ESP32 COM port, e.g. COM5'}
if($Port -notmatch '^COM[0-9]+$'){throw 'Invalid COM port'}
$image=Join-Path $PSScriptRoot 'firmware_release/UniversalGateway.ino.merged.bin'
if(!(Test-Path -LiteralPath $image)){throw 'Firmware image missing'}
$manifest=Join-Path $PSScriptRoot 'SHA256SUMS.txt'
if(Test-Path -LiteralPath $manifest){
 $entry=Get-Content -LiteralPath $manifest | Where-Object {$_ -match '  firmware_release/UniversalGateway\.ino\.merged\.bin$'}
 if(!$entry -or (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Substring(0,64)){throw 'Firmware checksum mismatch; use a fresh release or rebuild the checksum manifest'}
}
Write-Host 'ESP32-S3 N16R8 only. This replaces ESP firmware and may clear its settings. Close serial monitors.'
$answer=Read-Host 'Type FLASH to continue'
if($answer -cne 'FLASH'){exit}
& ./tools/esptool.exe --chip esp32s3 --port $Port --baud 460800 write-flash 0x0 $image
if($LASTEXITCODE -ne 0){throw 'Flashing failed'}
Write-Host 'Flash verified. Reading the device hotspot information...'
try {
 & (Join-Path $PSScriptRoot 'read-hotspot.ps1') -Port $Port
} catch {
 Write-Warning ('Firmware was flashed successfully, but hotspot information could not be read: ' + $_.Exception.Message)
 Write-Host 'Run read-hotspot.cmd to retry reading only. Do not flash again just to read the password.'
}
