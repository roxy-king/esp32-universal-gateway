param([switch]$CheckOnly)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Test-Python($exe) {
 if(!$exe -or !(Test-Path -LiteralPath $exe)){return $false}
 try { & $exe -c "import sys,venv,ensurepip;sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>$null; return $LASTEXITCODE -eq 0 } catch {return $false}
}
function Find-Python {
 $paths=@()
 if(Get-Command py -ErrorAction SilentlyContinue){try {$paths+= & py -3 -c 'import sys;print(sys.executable)' 2>$null} catch {}}
 $paths+= @(Get-Command python.exe -All -ErrorAction SilentlyContinue | Where-Object {$_.Source -notlike '*WindowsApps*'} | ForEach-Object {$_.Source})
 foreach($base in @("$env:LOCALAPPDATA/Programs/Python","$env:ProgramFiles")){
  if(Test-Path $base){$paths+=Get-ChildItem $base -Directory -Filter 'Python*' | ForEach-Object {Join-Path $_.FullName 'python.exe'}}
 }
 foreach($p in $paths){if(Test-Python $p){return $p}}
 return $null
}
try {
 $python=Join-Path (Get-Location) '.venv/Scripts/python.exe'
 if(!(Test-Python $python)){
  $basePython=Find-Python
  if(!$basePython){
   if($CheckOnly){throw 'Python 3.11+ is missing.'}
   if(!(Get-Command winget -ErrorAction SilentlyContinue)){throw 'Install Windows App Installer (winget) from Microsoft Store, then retry; or install Python 3.11+ from https://www.python.org/downloads/windows/.'}
   Write-Host 'Installing Python 3.13 for the current user...'
   & winget install --id Python.Python.3.13 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
   if($LASTEXITCODE -ne 0){throw "Python installation failed: $LASTEXITCODE. Check network and retry."}
   $basePython=Find-Python
   if(!$basePython){throw 'Close this window and run start-demo.cmd again to detect the installed Python.'}
  }
  if($CheckOnly){Write-Host "Python ready: $basePython. Launch will create the project environment.";exit 0}
  if(Test-Path '.venv'){
   $backup='.venv-backup-'+[Guid]::NewGuid().ToString('N')
   Move-Item -LiteralPath (Join-Path (Get-Location) '.venv') -Destination (Join-Path (Get-Location) $backup)
   Write-Host "Unusable environment preserved as $backup"
  }
  & $basePython -m venv .venv
  if($LASTEXITCODE -ne 0){throw 'Failed to create Python environment.'}
 }
 Write-Host "Python ready: $python"
 try {
  & $python -c "import importlib.metadata as m,pathlib,sys;lines=pathlib.Path('requirements.txt').read_text().splitlines();sys.exit(0 if all(m.version(s.split('==')[0])==s.split('==')[1] for s in lines if s.strip() and not s.startswith('#')) else 1)" 2>$null
  $ready=$LASTEXITCODE -eq 0
 } catch {$ready=$false}
 if($ready){& $python -m pip check; $ready=$LASTEXITCODE -eq 0}
 if(!$ready){
  if($CheckOnly){throw 'Dependencies missing. Run start-demo.cmd.'}
  Write-Host 'Installing dependencies...'
  & $python -m pip install --disable-pip-version-check --timeout 30 --retries 2 -r requirements.txt
  if($LASTEXITCODE -ne 0){throw 'Dependency installation failed. Check network and retry.'}
  & $python -m pip check
  if($LASTEXITCODE -ne 0){throw 'Dependency validation failed.'}
 }
 if($CheckOnly){Write-Host 'Environment check passed.';exit 0}
 Write-Host 'Open http://127.0.0.1:8880  Login: demo / demo1234  Stop: Ctrl+C'
 & $python tools/project.py demo
 exit $LASTEXITCODE
} catch {Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red;exit 1}
