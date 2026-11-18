param([string]$KeilRoot='D:/Keil_v5', [ValidateSet(11059200,12000000)][int]$Clock=11059200)
$ErrorActionPreference='Stop'
$bin=Join-Path $KeilRoot 'C51/BIN'
if(!(Test-Path (Join-Path $bin 'C51.exe'))){throw '请通过 -KeilRoot 指定已安装的 Keil C51；模板不附带商业编译器。'}
$out=Join-Path $PSScriptRoot 'output'
New-Item -ItemType Directory -Force -Path $out | Out-Null
Push-Location $PSScriptRoot
try {
 foreach($source in @('main','logic')) {
  & "$bin/C51.exe" "$source.c" "DEFINE(SYSTEM_CLOCK=$Clock`UL)" "INCDIR($KeilRoot/C51/INC)" "OBJECT(output/$source.obj)" "PRINT(output/$source.lst)"
  if($LASTEXITCODE -ne 0){throw "编译失败：$source"}
 }
 & "$bin/BL51.exe" 'output/main.obj,output/logic.obj' TO 'output/ProjectDemo' 'RAMSIZE(256)'
 if($LASTEXITCODE -ne 0){throw '链接失败'}
 & "$bin/OH51.exe" 'output/ProjectDemo' "HEXFILE(output/ProjectDemo_$Clock.hex)"
 if($LASTEXITCODE -ne 0){throw 'HEX生成失败'}
 Write-Host "已生成 output/ProjectDemo_$Clock.hex，STC-ISP 频率必须一致。"
} finally {Pop-Location}
