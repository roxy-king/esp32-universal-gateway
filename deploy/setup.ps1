param([string]$Server,[int]$Port=22)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location $root
foreach($name in @('ssh','scp','tar')){if(!(Get-Command $name -ErrorAction SilentlyContinue)){throw "Missing $name. Enable Windows OpenSSH Client / tar first."}}
if(!$Server){$Server=Read-Host 'Server IP or hostname (root SSH login)'}
if($Server -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$' -or $Port -lt 1 -or $Port -gt 65535){throw 'Invalid SSH host or port'}
$id=[guid]::NewGuid().ToString('N')
$remote="/tmp/esp-gateway-$id"
$archive=Join-Path $env:TEMP "esp-gateway-$id.tar.gz"
try {
 & tar -czf $archive -C $root deploy/install.sh deploy/install.py server/server.py server/index.html server/requirements.txt server/gateway.service server/nginx.conf.example
 if($LASTEXITCODE -ne 0){throw 'Packaging failed'}
 Write-Host 'SSH may ask for host fingerprint confirmation and your server password. Credentials are not stored.'
 & ssh -p $Port "root@$Server" "mkdir -m 700 $remote"
 if($LASTEXITCODE -ne 0){throw 'SSH connection failed'}
 & scp -P $Port $archive "root@${Server}:$remote/source.tar.gz"
 if($LASTEXITCODE -ne 0){throw 'Upload failed'}
 & ssh -t -p $Port "root@$Server" "tar -xzf $remote/source.tar.gz -C $remote && bash $remote/deploy/install.sh"
 if($LASTEXITCODE -ne 0){throw 'Server setup incomplete. Resolve the reported error and rerun.'}
 $private=Join-Path $root 'private'
 New-Item -ItemType Directory -Force $private | Out-Null
 $pair=Join-Path $private 'pairing.json'
 if(Test-Path -LiteralPath $pair){Copy-Item -LiteralPath $pair -Destination (Join-Path $private "pairing-backup-$id.json")}
 & scp -P $Port "root@${Server}:/etc/esp-gateway/pairing.json" $pair
 if($LASTEXITCODE -ne 0){throw 'Pairing file download failed'}
 Write-Host 'Now connect this PC to the ESP32 Gateway-Setup hotspot. Leave this window open.'
 Read-Host 'Press Enter after connecting to the hotspot' | Out-Null
 if(Get-Command py -ErrorAction SilentlyContinue){& py -3 (Join-Path $root 'deploy/pair.py') $pair}
 elseif(Get-Command python -ErrorAction SilentlyContinue){& python (Join-Path $root 'deploy/pair.py') $pair}
 else{throw 'Install Python 3.11+ and rerun connect.cmd. Server deployment is already complete.'}
 if($LASTEXITCODE -ne 0){throw 'ESP pairing incomplete. You can retry connect.cmd without reinstalling the server.'}
}finally{
 # Only the exact temporary archive created by this run is removed; no recursive deletion.
 if(Test-Path -LiteralPath $archive){Remove-Item -LiteralPath $archive}
}
