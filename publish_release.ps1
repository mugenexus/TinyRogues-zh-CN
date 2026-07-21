[CmdletBinding()]
param(
    [string]$Version,
    [string]$PackageDirectory = (Join-Path $PSScriptRoot 'TinyRogues_zh_patch'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist'),
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($Version)) {
    $readme = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Raw -Encoding UTF8
    $match = [regex]::Match($readme, '当前版本：`(?<version>\d+\.\d+\.\d+)`')
    if (-not $match.Success) {
        throw '无法从 README.md 读取当前版本。'
    }
    $Version = $match.Groups['version'].Value
}

$Version = $Version.TrimStart('v')
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "版本号格式无效：$Version"
}

$tag = "v$Version"
$title = "Tiny Rogues 简体中文汉化 $tag"
$package = [IO.Path]::GetFullPath($PackageDirectory)
$output = [IO.Path]::GetFullPath($OutputDirectory)
$requiredFiles = @(
    'manifest.csv',
    'winhttp.dll',
    '.doorstop_version',
    'BepInEx\plugins\TinyRogues.TmpFallback\TinyRogues.TmpFallback.dll'
)
foreach ($relativePath in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $package $relativePath) -PathType Leaf)) {
        throw "补丁目录缺少发布文件：$relativePath"
    }
}

$changelog = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'CHANGELOG.md') -Raw -Encoding UTF8
$sectionPattern = '(?ms)^##\s+' + [regex]::Escape($Version) + '\s+-\s+\d{4}-\d{2}-\d{2}\s*\r?\n(?<notes>.*?)(?=^##\s+|\z)'
$section = [regex]::Match($changelog, $sectionPattern)
if (-not $section.Success) {
    throw "CHANGELOG.md 中缺少 $Version 的发布记录。"
}

$releaseNotes = @"
# $title

## 更新内容

$($section.Groups['notes'].Value.Trim())

## 安装

1. 完全退出游戏。
2. 下载并解压发布压缩包。
3. 将压缩包内全部文件覆盖到《Tiny Rogues》游戏根目录。
4. 启动游戏；首次加载 BepInEx 可能需要稍候。

本补丁为社区非官方汉化，与游戏开发者及发行商无关。
"@

& git -C $PSScriptRoot diff --quiet HEAD -- . ':(exclude).gitignore'
if ($LASTEXITCODE -ne 0) {
    throw '存在尚未提交的发布文件，请先更新 Git。'
}
$head = (& git -C $PSScriptRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw '无法读取当前 Git 提交。'
}
& git -C $PSScriptRoot fetch origin main
if ($LASTEXITCODE -ne 0) {
    throw '无法同步 origin/main。'
}
$remoteHead = (& git -C $PSScriptRoot rev-parse origin/main).Trim()
if ($head -ne $remoteHead) {
    throw '当前提交尚未推送到 origin/main，请先更新 Git。'
}

$zipPath = Join-Path $output "TinyRogues_zh_CN_$tag.zip"
$notesPath = Join-Path $output "RELEASE_NOTES_$tag.md"
if ($DryRun) {
    Write-Output "发布检查通过：$title"
    Write-Output "提交：$head"
    Write-Output "压缩包：$zipPath"
    return
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw '未找到 GitHub CLI（gh）。'
}
& gh release view $tag --json url *> $null
if ($LASTEXITCODE -eq 0) {
    throw "GitHub Release 已存在：$tag"
}

New-Item -ItemType Directory -Path $output -Force | Out-Null
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
$archiveItems = @(Get-ChildItem -LiteralPath $package -Force)
Compress-Archive -LiteralPath $archiveItems.FullName -DestinationPath $zipPath -CompressionLevel Optimal
[IO.File]::WriteAllText($notesPath, $releaseNotes, (New-Object Text.UTF8Encoding($false)))

& gh release create $tag $zipPath `
    --target $head `
    --title $title `
    --notes-file $notesPath `
    --fail-on-no-commits `
    --latest
if ($LASTEXITCODE -ne 0) {
    throw "GitHub Release 创建失败：$tag"
}
