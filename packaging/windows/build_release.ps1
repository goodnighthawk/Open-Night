[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$SkipDependencyInstall,
    [switch]$SkipInstaller,
    [switch]$SkipSmokeTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$buildRoot = Join-Path $repoRoot "build\windows"
$venvRoot = Join-Path $repoRoot "build\nuitka-venv"
$nuitkaOutput = Join-Path $buildRoot "nuitka"
$releaseRoot = Join-Path $repoRoot "dist\windows"
$splashPath = Join-Path $repoRoot "assets\branding\snakepit_splash.png"
$iconPath = Join-Path $buildRoot "snakepit.ico"
$entryPoint = Join-Path $repoRoot "open_night_windows_client.py"
$version = (Get-Content -Raw (Join-Path $repoRoot "VERSION.txt")).Trim()

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath"
    }
}

function Remove-GeneratedPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $rootPrefix = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\') + '\'
    $target = [IO.Path]::GetFullPath($Path)
    if (-not $target.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the repository: $target"
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

function Find-InnoCompiler {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    return $null
}

if ($Clean) {
    Remove-GeneratedPath -Path $buildRoot
    Remove-GeneratedPath -Path $releaseRoot
}

foreach ($required in @($splashPath, $entryPoint)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required packaging input is missing: $required"
    }
}

New-Item -ItemType Directory -Force -Path $buildRoot, $nuitkaOutput, $releaseRoot | Out-Null

$venvPython = Join-Path $venvRoot "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    $bootstrapPython = if ($env:OPEN_NIGHT_BUILD_PYTHON) {
        $env:OPEN_NIGHT_BUILD_PYTHON
    } else {
        (Get-Command "python.exe" -ErrorAction Stop).Source
    }
    Invoke-Checked -FilePath $bootstrapPython -ArgumentList @("-m", "venv", $venvRoot)
}

if (-not $SkipDependencyInstall) {
    Invoke-Checked -FilePath $venvPython -ArgumentList @(
        "-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $repoRoot "requirements.txt"),
        "-r", (Join-Path $PSScriptRoot "requirements-build.txt")
    )
}

Invoke-Checked -FilePath $venvPython -ArgumentList @(
    (Join-Path $PSScriptRoot "make_icon.py"), $splashPath, $iconPath
)

$versionParts = @($version.Split('.') | ForEach-Object { if ($_ -match '^\d+$') { [int]$_ } else { 0 } })
while ($versionParts.Count -lt 4) {
    $versionParts += 0
}
$versionQuad = ($versionParts[0..3] -join '.')

$nuitkaArgs = @(
    "-m", "nuitka",
    "--mode=onefile",
    "--assume-yes-for-downloads",
    "--windows-console-mode=disable",
    "--onefile-windows-splash-screen-image=$splashPath",
    "--windows-icon-from-ico=$iconPath",
    "--company-name=Snakepit LLC",
    "--product-name=Open Night",
    "--file-description=Open Night Game Client",
    "--file-version=$versionQuad",
    "--product-version=$versionQuad",
    "--copyright=Copyright (C) 2026 Snakepit LLC",
    "--include-package-data=pygame",
    "--include-package-data=imageio_ffmpeg",
    "--include-data-dir=$(Join-Path $repoRoot 'assets')=assets",
    "--include-data-dir=$(Join-Path $repoRoot 'mapfiles\data')=mapfiles/data",
    "--include-data-dir=$(Join-Path $repoRoot 'config')=config",
    "--include-data-file=$(Join-Path $repoRoot 'VERSION.txt')=VERSION.txt",
    "--output-dir=$nuitkaOutput",
    "--output-filename=OpenNight.exe",
    "--remove-output",
    $entryPoint
)
Invoke-Checked -FilePath $venvPython -ArgumentList $nuitkaArgs

$builtExe = Join-Path $nuitkaOutput "OpenNight.exe"
if (-not (Test-Path -LiteralPath $builtExe)) {
    throw "Nuitka completed without producing $builtExe"
}
$clientExe = Join-Path $releaseRoot "OpenNight.exe"
Copy-Item -LiteralPath $builtExe -Destination $clientExe -Force

$installerPath = $null
if (-not $SkipInstaller) {
    $iscc = Find-InnoCompiler
    if (-not $iscc) {
        throw "Inno Setup 6 was not found. Install it with 'winget install JRSoftware.InnoSetup', then rerun this script."
    }
    $issPath = Join-Path $PSScriptRoot "OpenNight.iss"
    Invoke-Checked -FilePath $iscc -ArgumentList @(
        "/DMyAppVersion=$version",
        "/DMyVersionQuad=$versionQuad",
        "/DSourceExe=$clientExe",
        "/DOutputDir=$releaseRoot",
        "/DSetupIcon=$iconPath",
        $issPath
    )
    $installerPath = Join-Path $releaseRoot "OpenNight-Setup-$version.exe"
    if (-not (Test-Path -LiteralPath $installerPath)) {
        throw "Inno Setup completed without producing $installerPath"
    }
}

$artifacts = @($clientExe)
if ($installerPath) {
    $artifacts += $installerPath
}
$checksumLines = foreach ($artifact in $artifacts) {
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $artifact
    "$($hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($artifact))"
}
$checksumPath = Join-Path $releaseRoot "SHA256SUMS.txt"
Set-Content -LiteralPath $checksumPath -Value $checksumLines -Encoding ascii

$smokeReport = Join-Path $releaseRoot "PACKAGE_SMOKE_TEST.txt"
if (-not $SkipSmokeTest) {
    $previousSmoke = $env:OPEN_NIGHT_PACKAGE_SMOKE_TEST
    $previousReport = $env:OPEN_NIGHT_SMOKE_REPORT
    try {
        $env:OPEN_NIGHT_PACKAGE_SMOKE_TEST = "1"
        $env:OPEN_NIGHT_SMOKE_REPORT = $smokeReport
        $process = Start-Process -FilePath $clientExe -Wait -PassThru -WindowStyle Hidden
        if ($process.ExitCode -ne 0) {
            throw "Packaged-client smoke test failed with exit code $($process.ExitCode). See $smokeReport"
        }
        if (-not (Test-Path -LiteralPath $smokeReport)) {
            throw "Packaged-client smoke test did not produce $smokeReport"
        }
        $smokeResult = Get-Content -LiteralPath $smokeReport | Where-Object { $_ -like "result=*" }
        if ($smokeResult -ne "result=PASS") {
            throw "Packaged-client smoke test did not pass. See $smokeReport"
        }
    } finally {
        $env:OPEN_NIGHT_PACKAGE_SMOKE_TEST = $previousSmoke
        $env:OPEN_NIGHT_SMOKE_REPORT = $previousReport
    }
}

Write-Host ""
Write-Host "Open Night Windows release is ready:" -ForegroundColor Green
foreach ($artifact in $artifacts) {
    $sizeMb = [Math]::Round((Get-Item -LiteralPath $artifact).Length / 1MB, 1)
    Write-Host "  $artifact ($sizeMb MB)"
}
Write-Host "  $checksumPath"
if (Test-Path -LiteralPath $smokeReport) {
    Write-Host "  $smokeReport"
}
