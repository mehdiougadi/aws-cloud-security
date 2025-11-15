<powershell>
Set-MpPreference -DisableRealtimeMonitoring $false
Update-MpSignature

Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True

New-NetFirewallRule -DisplayName "Allow MSSQL" -Direction Inbound -Protocol TCP -LocalPort 1433 -Action Allow
New-NetFirewallRule -DisplayName "Allow MySQL" -Direction Inbound -Protocol TCP -LocalPort 3306 -Action Allow
New-NetFirewallRule -DisplayName "Allow PostgreSQL" -Direction Inbound -Protocol TCP -LocalPort 5432 -Action Allow
New-NetFirewallRule -DisplayName "Allow OSSEC" -Direction Inbound -Protocol TCP -LocalPort 1514 -Action Allow

New-Item -ItemType Directory -Path "C:\Logs" -Force
"DB Server init completed at $(Get-Date)" | Out-File "C:\Logs\init.log"
</powershell>