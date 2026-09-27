<#
.SYNOPSIS
  Schedule the retention sweep to run daily on this Windows machine.

.DESCRIPTION
  The consent screen tells every participant their data "is kept for N days
  and then deleted". server/retention.py does the deleting, but only when run;
  this makes it run without anyone remembering. It registers a task for the
  current user (no administrator rights needed) that runs

      node tools/py.mjs server/retention.py sweep --apply --record

  daily. StartWhenAvailable is on, so a laptop asleep at the scheduled time
  runs the sweep when it next wakes rather than skipping the day. Each run
  appends a line to out/retention_runs.jsonl; the researcher app reads it at
  startup and warns if no sweep has been recorded in 48 hours.

  Only this repo's own data is touched, under the rules in retention.py:
  sessions with no recorded retention period are never deleted, media roots
  and out/ are never deleted, and every deletion leaves a tombstone.

  npm run retention:schedule                      daily at 03:00
  npm run retention:schedule -- -At 04:30         another time
  npm run retention:unschedule                    remove it
#>
param(
  [string]$At = '03:00',
  [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$TaskName = 'myimotions retention sweep'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if ($Remove) {
  if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "  removed '$TaskName'"
  } else {
    Write-Output "  no task named '$TaskName'"
  }
  exit 0
}

$node = (Get-Command node -ErrorAction Stop).Source
$action = New-ScheduledTaskAction -Execute $node `
  -Argument 'tools/py.mjs server/retention.py sweep --apply --record' `
  -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
  -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$task = Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Description "Deletes study data past the retention period each participant was shown ($Repo). See server/retention.py." `
  -Force

$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Output ""
Write-Output "  scheduled   '$TaskName', daily at $At (runs late if the machine was off)"
Write-Output "  runs        $node tools/py.mjs server/retention.py sweep --apply --record"
Write-Output "  in          $Repo"
Write-Output "  next run    $($info.NextRunTime)"
Write-Output "  check       out/retention_runs.jsonl, or the researcher app's startup lines"
Write-Output ""
