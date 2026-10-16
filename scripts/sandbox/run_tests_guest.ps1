$ErrorActionPreference = 'Stop'
if ($env:USERNAME -ne 'WDAGUtilityAccount') { throw 'Windows Sandbox account required.' }
$root = 'C:\BuildOutput\controller-private\unit-tests-' + [guid]::NewGuid().ToString('N')
New-Item -ItemType Directory -Path $root -Force | Out-Null
$manifest = Get-Content C:\BuildInput\controller-tests\manifest.json -Raw | ConvertFrom-Json
$results = @()
# Upstream's weave acceptance harness is a separate, destructive VM workflow.
$env:WINDOWS_MCP_ACC = '0'
foreach ($entry in $manifest) {
    $binary = Join-Path 'C:\BuildInput\controller-tests' $entry.Binary
    if ((Get-FileHash -LiteralPath $binary).Hash -ne $entry.Sha256) { throw 'Test binary hash mismatch.' }
    $working = Join-Path 'C:\BuildInput\controller-source' $entry.Package
    $name = $entry.Package.Replace('/','-')
    $stdout = Join-Path $root ($name + '-stdout.txt')
    $stderr = Join-Path $root ($name + '-stderr.txt')
    $process = Start-Process -FilePath $binary -ArgumentList '-test.v','-test.timeout=120s' -WorkingDirectory $working -NoNewWindow -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $null = $process.Handle # Retain the native handle before a short-lived test exits.
    $timedOut = -not $process.WaitForExit(125000)
    if ($timedOut) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
    $process.WaitForExit()
    if ($null -eq $process.ExitCode) { throw 'Test exited without a readable native exit status.' }
    $log = [IO.File]::ReadAllText($stdout)
    $results += [ordered]@{Package=$entry.Package;ExitCode=$process.ExitCode;TimedOut=$timedOut;
        PassCount=[regex]::Matches($log,'(?m)^\s*--- PASS:').Count;
        SkipCount=[regex]::Matches($log,'(?m)^\s*--- SKIP:').Count;
        FailCount=[regex]::Matches($log,'(?m)^\s*--- FAIL:').Count}
    [ordered]@{User=$env:USERNAME;Computer=$env:COMPUTERNAME;RunDirectory=$root;Results=$results} |
        ConvertTo-Json -Depth 5 | Set-Content (Join-Path $root 'results.json') -Encoding UTF8
}
Copy-Item -LiteralPath (Join-Path $root 'results.json') -Destination 'C:\BuildOutput\controller-private\unit-tests-latest.json' -Force
if (@($results | Where-Object { $_.ExitCode -ne 0 -or $_.TimedOut }).Count) { exit 1 }
