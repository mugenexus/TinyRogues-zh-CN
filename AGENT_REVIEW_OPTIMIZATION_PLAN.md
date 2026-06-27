# Tiny Rogues 汉化复查与优化交接规划

本文档给后续 agent 使用。目标不是立刻重写补丁，而是按可复现步骤复查当前 `v1.5.12`，找出仍然漏翻、错译、混排和 UI 显示问题，并以低风险方式优化。

## 当前状态

- 当前补丁版本：`v1.5.12`
- 当前补丁目录：`C:\Users\Mugen\Documents\汉化\TinyRogues_zh_patch`
- 发布包：`C:\Users\Mugen\Documents\汉化\TinyRogues_zh_patch_v1.5.12.zip`
- 游戏目录：`D:\SteamLibrary\steamapps\common\Tiny Rogues`
- 运行时插件：`TinyRogues.TmpFallback`
- 关键策略：静态词库 + TMP 回退插件 + 正则动态文本 + 受控片段替换 + 运行时未命中日志。

## 已知问题回顾

1. 旧 BepInEx / Cpp2IL 不兼容新游戏元数据版本，曾出现 `Unsupported metadata version ... got 31`。后续应使用当前已安装的 BepInEx 6 be.759，不要回退旧补丁里的 BepInEx。
2. 大量文本不在静态资源直接生效路径里，需要运行时 TMP 插件处理，包括教程对话、奖励门、物品详情、升级特质、状态说明、职业说明和菜单。
3. 动态文本经常被短片段先替换，导致整句规则失配，例如 `Uncommon Item` 变成 `优秀 Item`、`Body Armor` 变成 `Body 护甲`、`Cursed Shrine` 变成 `诅咒 Shrine`。
4. 物品详情和特质详情包含数值、颜色、图标、换行和 `<indent>`，只靠片段翻译会产生中英混排和错位。
5. 逐字对话会产生中间态，必须用前缀消歧匹配，不能把半句话都当成漏翻。
6. 共享 Tooltip 被运行时循环改 `RectTransform.sizeDelta` 后会和游戏布局系统争夺尺寸，造成错位、异常放大和画面闪烁。`v1.5.12` 已移除此逻辑，后续不要重新引入。
7. 用户反馈集中在：漏翻、特质没汉化、物品属性混排、详情框过小或错位、提示框闪烁。

## 高优先级原则

- 不要直接覆盖原游戏资源文件，除非用户明确要求并说明风险。
- 不要在 `Update()` 或类似轮询里持续修改共享 UI 容器尺寸。
- 对富文本必须保留颜色代码、`<sprite>`、`<indent>`、换行、变量、占位符和数值。
- 动态文本优先用正则整句规则；片段替换只能作为最后兜底。
- 每次新增规则后，要同时考虑“原英文状态”和“部分已被片段翻译的中间状态”。
- 不要盲目缩小字号。优先改换行、整句译文长度和结构化翻译；UI 放大必须是一次性且稳定的方案。

## 复查阶段规划

### 阶段 1：建立当前基线

目标：确认当前安装的版本和日志来源，避免基于旧状态判断。

操作：

1. 检查插件版本：
   `D:\SteamLibrary\steamapps\common\Tiny Rogues\BepInEx\LogOutput.log`
   应看到 `Tiny Rogues TMP Translation Fallback 1.5.12`。
2. 读取运行时日志：
   `D:\SteamLibrary\steamapps\common\Tiny Rogues\BepInEx\Translation\zh\Text\_TmpUntranslated.txt`
   `D:\SteamLibrary\steamapps\common\Tiny Rogues\BepInEx\Translation\zh\Text\_TmpResidualEnglish.txt`
3. 检查构建产物是否和安装目录一致：
   `TinyRogues_zh_patch\BepInEx\plugins\TinyRogues.TmpFallback`

产出：

- 新增或更新 `findings.md`：记录当前真实未翻译和残留英文样例。
- 不要只凭截图修，必须找对应源字符串。

### 阶段 2：运行覆盖率审计

目标：用脚本发现“看起来已翻译但仍残留英文”的文本。

优先脚本：

- `audit_runtime_residuals.py`
- `audit_runtime_coverage.py`
- `audit_translations.py`

建议检查点：

- 完全未命中：整段英文仍未替换。
- 部分命中：译文中仍有英文名词、动词、类型、状态名。
- 误替换：如 `Lucky` 被拆成 `幸运y`、`Cursed` 被拆成 `诅咒d`。
- 标签破坏：颜色标签、sprite、indent 数量不一致。

产出：

- 按类别列出高频残留：物品详情、特质、状态、奖励门、菜单、对话。
- 每个残留至少保留：源文本、当前译文、对象名、日志时间。

### 阶段 3：动态文本规则补齐

目标：修复最容易反复漏翻的动态文本。

优先文件：

- `runtime_regex_zh.txt`：动态整句、带数值捕获的首选位置。
- `runtime_plugin_overrides_zh.txt`：精确富文本、标题和固定句。
- `runtime_item_fragments_zh.txt`：仅用于物品详情的安全片段。
- `runtime_fragments_zh.txt`：通用片段，必须保守。
- `runtime_dialogue_overrides_zh.txt`：对话人工覆盖。

推荐顺序：

1. 奖励门与房间门：
   `Guaranteed ...`、`Reward choices include at least ...`、`Requires Key to open`、`Price Gold`。
2. 物品详情：
   装备负重、武器类型、攻击伤害、攻击速度、套装、调谐、消耗品。
3. 升级特质：
   `Trait Description`、`On Hit`、`On Dash`、`Grants`、状态触发说明。
4. 状态与触发物：
   `Burn`、`Chill`、`Shock`、`Gloom`、`Taunt`、`Intimidate`、`Chain Lightning`。
5. 对话：
   教程逐字句、NPC 对话、黑市确认、职业解锁提示。

规则要求：

- 正则要同时兼容英文和已局部汉化的中间态，例如 `(?:Uncommon|优秀)`。
- 数值和图标用捕获组回填，不写死。
- 不要把短词片段放得过宽，例如 `in`、`to`、`Use` 这类容易污染其他句子的词。

### 阶段 4：UI 显示复查与优化

目标：改善中文显示，但不能再造成闪烁和错位。

禁止方案：

- 禁止在扫描循环里对共享 Tooltip 写 `sizeDelta`。
- 禁止按当前尺寸继续累加放大。
- 禁止把所有包含 `Tooltip` 的对象一概放大。

可选方案，从低风险到高风险：

1. 优先压缩译文长度，改自然短句。
2. 优先调整换行，让中文按语义分行。
3. 对物品详情继续使用受控 `<size=92%>`，特质说明使用 `<size=100%>`，不要无脑降到很小。
4. 如果必须放大框体，只能定位具体稳定预制体或具体对象路径，在创建时一次性设置，并记录原始尺寸、目标尺寸和对象名。
5. 对不同类型分别处理：奖励门小框、物品详情大框、升级特质列表、状态详情、普通对话框。

重点回归场景：

- 物品房：武器、护甲、戒指、套装、消耗品。
- 升级选特质页面：左侧列表和右侧状态详情。
- 奖励门：保底物品、保底饰品、保底护甲、保底手套、金币、灵魂、宝箱。
- 教程房：逐字对话、拾取提示、物品栏提示。
- 角色面板：General、Offense、Defense、Misc。

### 阶段 5：构建与安装

构建：

```powershell
dotnet build "C:\Users\Mugen\Documents\汉化\TinyRogues.TmpFallback\TinyRogues.TmpFallback.csproj" -c Release
```

生成补丁：

```powershell
& "C:\Users\Mugen\Documents\汉化\build_patch.ps1" -FontBundlePath "D:\SteamLibrary\steamapps\common\Tiny Rogues\arialuni_sdf_u2019"
```

覆盖安装：

```powershell
Copy-Item -Path "C:\Users\Mugen\Documents\汉化\TinyRogues_zh_patch\*" -Destination "D:\SteamLibrary\steamapps\common\Tiny Rogues" -Recurse -Force
```

注意：

- 覆盖安装前先确认游戏未运行，否则 DLL 可能被占用。
- 如果用户明确说“不用验证”，不要强行启动游戏。
- 构建警告中 `System.*` 版本冲突目前是既有警告，只要 `0 个错误` 可继续。

### 阶段 6：验收标准

必须满足：

- BepInEx 日志加载目标版本插件。
- 不出现 `Adjusted tooltip` 一类旧尺寸调整日志。
- 不出现 `Failed to compile regex`。
- 新增规则没有破坏富文本标签数量。
- `_TmpResidualEnglish.txt` 中本轮修复对象不再出现同样残留。
- 物品详情、特质详情、奖励门和对话至少各抽查 3 个场景。

可接受残留：

- 专有名词暂未统一但不影响理解，例如部分怪物名或物品名。
- 技术项、按键名、Steam 提示和日志性文本。

不可接受残留：

- 英文动词或句子留在中文句中。
- `Item`、`Damage`、`Seconds`、`Companions`、`Trigger` 等基础 UI 词未翻。
- 中文字叠到图标、边框或玩家角色上。
- 画面闪烁、提示框尺寸跳动。

## 后续 agent 的工作清单

1. 先读本文件、`CHANGELOG.md`、`findings.md`、`progress.md`。
2. 收集当前 `_TmpUntranslated.txt` 和 `_TmpResidualEnglish.txt`。
3. 按“奖励门、物品详情、特质、状态、对话、菜单”分类。
4. 每次只修一个类别，优先正则整句。
5. 构建后用脚本或日志验证规则加载。
6. 不要把 UI 放大和文本补翻混在同一个大改里。
7. 每轮更新 `CHANGELOG.md`，版本递增。

## 高风险区域

- `TinyRogues.TmpFallback\Plugin.cs` 的扫描循环。
- `IsItemDetailPanel`、`IsStructuredRichText`、`ShouldApplyGeneralFragments` 的路由逻辑。
- `runtime_fragments_zh.txt` 中的短片段。
- 富文本正则中的换行、非断行空格和 `<sprite>`。
- 任何 `RectTransform`、`ContentSizeFitter`、`LayoutGroup` 相关改动。

## 建议下一版本目标

建议版本：`1.5.13`

推荐范围：

- 只做“动态文本残留复查 + 奖励门/物品详情/特质规则补齐”。
- 不做新的提示框容器缩放。
- 如果确实要改善显示框，单独开 `1.5.14`，先实现对象路径白名单和一次性初始化，再测试。

