# Tiny Rogues 简体中文汉化

适用于 Steam 版《Tiny Rogues》的非官方简体中文汉化补丁，覆盖菜单、职业、物品、技能、特质、教程、动态状态和多数剧情文本。

当前版本：`1.5.18`

## 1.5.18 版本亮点

- 补齐特质选择、士气状态、同伴装备、骰子奖励和分段教学文本中的英文残留
- 修复彩色逐字富文本导致的物品名称与属性漏翻
- 扩大地面未拾取/待购买物品详情框，身上装备界面保持原样
- 发布前审计结果：控制符问题 0、运行时未覆盖 0、英文残留 0

## 功能

- 菜单、职业、物品、技能、精通、余烬、世界层和多数剧情文本汉化
- 支持 TextMesh Pro 富文本、颜色标签、图标、变量和占位符
- 针对逐字显示的教程与 NPC 对话提供运行时前缀匹配
- 不修改 `Tiny Rogues_Data`、`GameAssembly.dll` 或游戏可执行文件

## 安装

1. 从 GitHub Releases 下载发布压缩包。
2. 退出游戏。
3. 将压缩包内容解压到 Tiny Rogues 游戏根目录。
4. 启动游戏。首次启动 BepInEx 可能需要等待一段时间。

默认游戏目录通常为：

```text
...\SteamLibrary\steamapps\common\Tiny Rogues
```

补丁依赖 BepInEx 6 IL2CPP 和 XUnity.AutoTranslator。发布压缩包已包含经过验证的版本。

## 卸载

如果没有安装其他 BepInEx 模组，可删除本补丁添加的 `BepInEx`、`dotnet`、`doorstop_config.ini`、`.doorstop_version`、`winhttp.dll` 和 `arialuni_sdf_u2019`。

如果还在使用其他 BepInEx 模组，请仅删除：

```text
BepInEx\plugins\TinyRogues.TmpFallback
BepInEx\Translation\zh
BepInEx\config\AutoTranslatorConfig.ini
arialuni_sdf_u2019
```

## 从源码构建

要求：

- PowerShell 5.1 或更高版本
- .NET SDK
- 已完成首次初始化的 BepInEx 6 IL2CPP 游戏目录
- BepInEx `be.759` 压缩包
- XUnity.AutoTranslator `5.6.1` IL2CPP 压缩包
- 可显示中文的 TextMesh Pro 字体 AssetBundle

编译运行时插件：

```powershell
dotnet build .\TinyRogues.TmpFallback\TinyRogues.TmpFallback.csproj `
  -c Release `
  -p:TinyRoguesDir="D:\SteamLibrary\steamapps\common\Tiny Rogues"
```

生成补丁目录：

```powershell
.\build_patch.ps1 `
  -FontBundlePath "C:\path\to\arialuni_sdf_u2019"
```

输出目录为 `TinyRogues_zh_patch`。

## 翻译数据

主词库为 `translations_zh.csv`，保留原文 key、来源路径和行号。运行时补充规则位于：

- `runtime_overrides_zh.txt`
- `runtime_plugin_overrides_zh.txt`
- `runtime_regex_zh.txt`
- `runtime_fragments_zh.txt`
- `runtime_item_fragments_zh.txt`
- `runtime_dialogue_overrides_zh.txt`

翻译时不得改动变量、控制符、颜色代码、换行符、图标标签和占位符。

完整版本记录见 [CHANGELOG.md](CHANGELOG.md)。

## 说明

这是社区制作的非官方汉化，与游戏开发者或发行商无关。游戏更新后可能出现新增文本或匹配失效，请通过 Issue 提交截图和出现位置。
