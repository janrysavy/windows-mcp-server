param([Parameter(Mandatory=$true)][string]$InputRoot)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$testRoot = Join-Path $InputRoot 'controller-tests'
$sourceRoot = Join-Path $InputRoot 'controller-source'
New-Item -ItemType Directory -Path $testRoot,$sourceRoot -Force | Out-Null
$packages = @('internal/desktop','internal/psdata','internal/winmcp','pkg/windows','internal/acceptance')
$manifest = @()
Push-Location $repo
try {
    foreach ($package in $packages) {
        $name = $package.Replace('/','-') + '.test.exe'
        $binary = Join-Path $testRoot $name
        # Vet is run separately: Go 1.27.2 reports two unchanged upstream warnings.
        & go test -c -vet=off -o $binary ("./" + $package)
        if ($LASTEXITCODE -ne 0) { throw "Test compilation failed: $package" }
        $manifest += [ordered]@{Package=$package;Binary=$name;Sha256=(Get-FileHash $binary).Hash}
        New-Item -ItemType Directory -Path (Join-Path $sourceRoot $package) -Force | Out-Null
    }
    foreach ($directory in @('policy','journeys','schema')) {
        Copy-Item -LiteralPath (Join-Path $repo $directory) -Destination $sourceRoot -Recurse -Force
    }
    $manifest | ConvertTo-Json | Set-Content (Join-Path $testRoot 'manifest.json') -Encoding UTF8
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'run_tests_guest.ps1') -Destination $InputRoot -Force
} finally { Pop-Location }
