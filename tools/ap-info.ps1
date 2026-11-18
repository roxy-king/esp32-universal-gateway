function ConvertFrom-GatewayBootText {
    param([string]$Text)
    # Require a complete newline-terminated record: serial reads may split a password.
    $records = [regex]::Matches($Text, '(?m)^AP: (Gateway-Setup-[A-Za-z0-9_-]+) password: ([^\r\n]+)\r?\n')
    foreach ($record in $records) {
        $password = $record.Groups[2].Value
        if ($password.Length -ge 8 -and $password.Length -le 63) {
            return [pscustomobject]@{
                SSID = $record.Groups[1].Value
                Password = $password
                Address = 'http://192.168.4.1'
            }
        }
    }
    return $null
}
