param([switch]$InstallDependencies)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$cli=Join-Path $PSScriptRoot 'tools/arduino-cli.exe'
$config=Join-Path $PSScriptRoot 'tools/arduino-cli.yaml'
$base=$PSScriptRoot.Replace('\','/')
@"
directories:
  data: $base/tools/arduino-data
  downloads: $base/tools/downloads
  user: $base/tools/arduino-user
board_manager:
  additional_urls:
    - https://espressif.github.io/arduino-esp32/package_esp32_index.json
"@ | Set-Content -LiteralPath $config -Encoding utf8
if($InstallDependencies){
 & $cli --config-file $config core update-index
 if($LASTEXITCODE -ne 0){throw 'Core index failed'}
 & $cli --config-file $config core install esp32:esp32@3.3.2
 if($LASTEXITCODE -ne 0){throw 'Core installation failed'}
}
& $cli --config-file $config compile --build-path ./build/compile --fqbn 'esp32:esp32:esp32s3:FlashSize=16M,PSRAM=disabled,PartitionScheme=app3M_fat9M_16MB,CDCOnBoot=default' --build-property build.flash_freq=40m --build-property compiler.cpp.extra_flags=-DNETWORK_EVENTS_MUTEX --output-dir ./firmware_release ./firmware/UniversalGateway
if($LASTEXITCODE -ne 0){throw 'Build failed'}
$manifest=Join-Path $PSScriptRoot 'SHA256SUMS.txt'
if(Test-Path -LiteralPath $manifest){
 $lines=Get-Content -LiteralPath $manifest | ForEach-Object {
  if($_ -match '^[0-9a-f]{64}  (firmware_release/[^/]+\.bin)$'){
   $relative=$Matches[1]
   $hash=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
   "$hash  $relative"
  }else{$_}
 }
 $lines | Set-Content -LiteralPath $manifest -Encoding utf8
}
Write-Host 'Build complete. Portal.h is already embedded; after HTML edits run python embed_portal.py first.'
