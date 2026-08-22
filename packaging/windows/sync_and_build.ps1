[CmdletBinding()]
param(
    [switch]$NoPush,
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$packagingBranch = "release/nuitka-windows-installer"

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed with exit code ${LASTEXITCODE}: git $($Arguments -join ' ')"
    }
}

Set-Location $repoRoot
$branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $packagingBranch) {
    throw "Run this from the '$packagingBranch' worktree. Current branch: '$branch'"
}

$dirty = @(& git status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect the packaging worktree."
}
if ($dirty.Count -gt 0) {
    throw "The packaging worktree has uncommitted files. Commit or remove them before synchronizing."
}

Invoke-Git -Arguments @("fetch", "origin", "main")
$mainCommit = (& git rev-parse "origin/main").Trim()
$beforeCommit = (& git rev-parse "HEAD").Trim()
$beforeVersion = (Get-Content -Raw (Join-Path $repoRoot "VERSION.txt")).Trim()

& git merge --no-edit "origin/main"
if ($LASTEXITCODE -ne 0) {
    & git merge --abort 2>$null
    throw "origin/main could not be merged cleanly. The attempted merge was aborted."
}

& git merge-base --is-ancestor "origin/main" "HEAD"
if ($LASTEXITCODE -ne 0) {
    throw "Synchronization check failed: the packaging branch does not contain origin/main."
}

$afterVersion = (Get-Content -Raw (Join-Path $repoRoot "VERSION.txt")).Trim()
Write-Host "Synchronized packaging branch:" -ForegroundColor Cyan
Write-Host "  previous HEAD: $beforeCommit (v$beforeVersion)"
Write-Host "  origin/main:  $mainCommit"
Write-Host "  packaged as:  v$afterVersion"

$buildArguments = @()
if ($Clean) {
    $buildArguments += "-Clean"
}
& (Join-Path $PSScriptRoot "build_release.ps1") @buildArguments
if ($LASTEXITCODE -ne 0) {
    throw "The synchronized game compiled unsuccessfully; the branch was not pushed."
}

if (-not $NoPush) {
    Invoke-Git -Arguments @("push", "--set-upstream", "origin", $packagingBranch)
    Write-Host "The synchronized packaging branch was pushed after a successful build." -ForegroundColor Green
} else {
    Write-Host "Build passed. Push was skipped because -NoPush was supplied." -ForegroundColor Yellow
}
