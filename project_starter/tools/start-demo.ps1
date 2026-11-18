$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location $root
if(!(Test-Path '.venv/Scripts/python.exe')){
 if(Get-Command py -ErrorAction SilentlyContinue){& py -3 -m venv .venv}
 elseif(Get-Command python -ErrorAction SilentlyContinue){& python -m venv .venv}
 else{throw '请先安装 Python 3.11 或以上版本，并勾选加入 PATH。'}
 if($LASTEXITCODE -ne 0){throw '创建 Python 环境失败'}
}
& .venv/Scripts/python.exe -m pip install -r requirements.txt
if($LASTEXITCODE -ne 0){throw '依赖安装失败，请检查网络后重试'}
& .venv/Scripts/python.exe tools/project.py demo
