param(
    [string]$CsvPath = (Join-Path $PSScriptRoot 'translations_zh.csv'),
    [string]$ReportPath = (Join-Path $PSScriptRoot 'translation_polish_report.csv')
)

$ErrorActionPreference = 'Stop'

function Get-ControlSignature {
    param([string]$Text)

    $pattern = '\r\n|\r|\n|\\n|\\r|\\t|<[^>]+>|\{[^{}]+\}|\(\*\)|\(br\)|\((?:x\d+(?:%?x\d+)?|[a-z][A-Za-z0-9_]*)\)|\[\[|\]\]|##|//'
    return (([regex]::Matches($Text, $pattern) |
        ForEach-Object {
            if ($_.Value -eq "`r`n" -or $_.Value -eq "`r" -or $_.Value -eq "`n") {
                '\n'
            }
            else {
                $_.Value
            }
        } |
        Sort-Object) -join [char]0)
}

function Add-ReviewNote {
    param(
        [object]$Row,
        [string]$Reason
    )

    $note = "人工校对：$Reason"
    $parts = @($Row.notes -split ';\s*' | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_) -and $_ -notlike '人工校对：*'
    })
    $Row.notes = (@($parts) + $note) -join '; '
}

if (-not (Test-Path -LiteralPath $CsvPath)) {
    throw "CSV 不存在：$CsvPath"
}

$rows = @(Import-Csv -LiteralPath $CsvPath)
$beforeByKey = @{}
foreach ($row in $rows) {
    $beforeByKey[$row.key] = $row.translation_zh
}

$exact = @{
    'Attunement_Bonfire' = '调谐已装备的物品？'
    'Black_Market_Rat_Thank_You_1' = '这买卖真是捡了大便宜。'
    'BOSS_Cerberus_1' = '我闻到你的气味了。\n快跑。\n……'
    'NotEnoughHearts' = '*需要一颗备用的\n//心<sprite name="Health">作为祭品。*'
    'Tips_For_Adventurers_9' = '冒险者小贴士 9/10\n你知道吗？大多数敌人，甚至首领，\n都会弱于某种伤害类型。\n携带附魔类消耗品时，\n了解这些弱点会很有帮助！'
    'NPC_Nurse_2' = '你好！\n你看起来受了点伤，\n需要治疗吗？\n<color=grey>[完全恢复心<sprite name="Heart">\n并补满药瓶。]</color>'
    'NPC_Bar_Maiden_1' = '想留宿\n一晚吗？\n<color=grey>[将重掷酒馆访客。]</color>'
    'Goat_Devil_2' = '我不骗你。\n没错，我是个恶魔。\n不过先别急着\n下结论。\n咩-嘿-嘿-嘿！'
    'Goat_Devil_7' = '没那么糟，对吧？\n咩-嘿-嘿-嘿！\n合作愉快。'
    'AUTO_LEVEL0_170B0' = '选项：环绕物透明度'
    'AUTO_LEVEL0_3509C' = '加快首领击败及奖励动画：'
    'AUTO_LEVEL0_38ACC' = '敌人生命条：'
    'AUTO_LEVEL2_5C0F4' = '首领名称'
    'AUTO_GLOBAL-METADATA_DAT_2440E' = '每层中，每个余烬修正都会提高生命<sprite name=Heart>和护甲<sprite name=Armor>。</i>\n<SubArrow><i>收割者和自动机[[不受影响]]。</i>'
    'AUTO_GLOBAL-METADATA_DAT_35986' = '每轮结束后，你会根据击败的首领数量获得精通<color=yellow>经验</color>。\n每提升一级即可分配一个天赋点。\n这些天赋'
    'AUTO_GLOBAL-METADATA_DAT_A6254' = '{0}(*)<i>造成 [[+{1:0} 至 {2:0}]] 点{3}伤害'
    'AUTO_GLOBAL-METADATA_DAT_A6CE0' = '{0}获得 {1} 个{2}同伴<sprite name="Companion">。{3}'
    'AUTO_GLOBAL-METADATA_DAT_97B93' = '直到房间清理完成'
    'AUTO_GLOBAL-METADATA_DAT_9830C' = '武器类别'
    'AUTO_GLOBAL-METADATA_DAT_93717' = '非暴击'
    'AUTO_RESOURCES_ASSETS_E7D998' = '固有护甲拾取物'
    'AUTO_RESOURCES_ASSETS_E7D9E8' = '生命水晶拾取物'
    'AUTO_RESOURCES_ASSETS_E8C4D4' = '生命之泉'
    'AUTO_RESOURCES_ASSETS_E96A60' = '生命药瓶充能拾取物'
    'AUTO_RESOURCES_ASSETS_221CE2C' = '(*)(x0) 个首领奖励选项'
    'AUTO_RESOURCES_ASSETS_21DC04A' = '(actionName) 造成 (damage) 点伤害。</i>'
    'AUTO_RESOURCES_ASSETS_220FF40' = '每个法力槽<Mana>使其造成 (xx0x1) 点伤害。'
    'AUTO_RESOURCES_ASSETS_2210C2C' = '每个护甲槽<Armor>使其造成 (xx0x1) 点物理伤害。'
    'AUTO_RESOURCES_ASSETS_2211240' = '你每拥有一个灵魂<Soul>，同伴<Companion>就造成 (xx0x1) 点伤害。'
    'AUTO_RESOURCES_ASSETS_221E008' = '(*)<i>每点善良<Good>提供 (x0x1) 宝藏寻获<Treasure> <g>（当前为 (x0)）</g></i>'
    'AUTO_RESOURCES_ASSETS_221E1FC' = '(*)<i>每点混沌<Chaos>提供 (x0x1) 宝藏寻获<Treasure> <g>（当前为 (x0)）</g></i>'
    'AUTO_RESOURCES_ASSETS_221E528' = '(*)<i>每点邪恶<Evil>提供 (x0x1) 宝藏寻获<Treasure> <g>（当前为 (x0)）</g></i>'
    'AUTO_RESOURCES_ASSETS_2257B6C' = '(x0) 个首领奖励选项'
    'AUTO_RESOURCES_ASSETS_2273174' = '(*)(i)占位'
    'AUTO_RESOURCES_ASSETS_22750F0' = '(*)(i)占位'
    'AUTO_RESOURCES_ASSETS_2275C38' = '<SubArrow>造成 (xx0) 点伤害。</i>'
    'AUTO_RESOURCES_ASSETS_2284DAC' = '(*)<i>对恶魔造成 (xx0) 点伤害。</i>'
    'AUTO_RESOURCES_ASSETS_22C57D0' = '可使移动速度提高 (x0%)。'
    'AUTO_RESOURCES_ASSETS_22E26B8' = '首领在第一阶段拥有 <color=#00E317>x0.75</color> 倍生命<Heart>和护甲<Armor>，但在第二阶段拥有 <color=red>x1.25</color> 倍。'
    'AUTO_RESOURCES_ASSETS_22E2838' = '每层最多出现 ((x3.00)) 倍的附魔敌人群。'
    'AUTO_RESOURCES_ASSETS_22E28D8' = '第 1 层的耐力恢复速度<sprite name="Stamina">延迟 ((+3)) 秒，第 2 层延迟 ((+2)) 秒，第 3 层延迟 ((+1)) 秒。'
    'AUTO_RESOURCES_ASSETS_22E29CC' = '无论你的诅咒<Curse>有多高，收割者现在都可能出现。'
    'AUTO_RESOURCES_ASSETS_22E2A0B' = '收割者获得护甲<Armor>和一个额外的##攻击词缀。'
    'AUTO_RESOURCES_ASSETS_22E2B38' = '首领会由 ((2)) 个随机守卫自动机陪同。'
    'AUTO_RESOURCES_ASSETS_22E2BF7' = '开启它们需要 ((1)) 颗心<sprite name="Heart">。'
    'AUTO_RESOURCES_ASSETS_22E2C80' = '首领、宝箱怪和蛇怪会获得附魔。'
    'AUTO_RESOURCES_ASSETS_22E2CAC' = '<color=grey>（首领不会因附魔获得生命<sprite name=Heart>或护甲<sprite name=Armor>加成。）</color>'
    'AUTO_RESOURCES_ASSETS_22E2E30' = '附魔敌人有 ((20%)) 几率获得一个额外的防御修正。'
    'AUTO_RESOURCES_ASSETS_22E2FE0' = '百夫长猎手自动机有时会入侵战斗并##攻击你。'
    'AUTO_RESOURCES_ASSETS_22E3098' = '进入首领战的第一和第二阶段时，你和同伴<Companion>造成的伤害变为 ((x0.50)) 倍。'
    'AUTO_RESOURCES_ASSETS_22E3107' = '此惩罚会在 20 秒内以每次 ((x0.05)) 的幅度逐步衰减。'
    'AUTO_RESOURCES_ASSETS_22E31D2' = '感染敌人死亡时会爆炸，并将感染传播给其他敌人。'
    'AUTO_RESOURCES_ASSETS_22E3280' = '附魔敌人有 ((50%)) 几率获得一个额外的次要修正。'
    'AUTO_RESOURCES_ASSETS_22E3644' = '诅咒<sprite name="Curse">达到 5 层或更多时击败死神。'
    'AUTO_RESOURCES_ASSETS_22E39DC' = '你就是天选之人，别有压力。'
    'AUTO_RESOURCES_ASSETS_22E9A28' = '<rainbow>瓶中彩虹</rainbow>'
    'AUTO_RESOURCES_ASSETS_22EBBFC' = '移除 1 层诅咒<sprite name="Curse">。'
    'AUTO_RESOURCES_ASSETS_2325603' = '当前穿戴的物品会[[x1.20]]更##常见。'
    'AUTO_RESOURCES_ASSETS_2326338' = '当一种阵营倾向达到 2 或更高，且另外三种为 1 或更低时：'
    'AUTO_RESOURCES_ASSETS_23267B0' = '第 1 层必定出现一扇通往同伴奖励的门，并将其作为首领奖励。'
    'AUTO_RESOURCES_ASSETS_2327B04' = '提供//武器或装备的首领奖励，现在会为 [[3]] 件物品保证指定类型，而不再只保证 1 件。'
    'AUTO_RESOURCES_ASSETS_2328814' = '整层未受到伤害即可让首领额外提供 [[+1]] 个奖励。'
    'AUTO_RESOURCES_ASSETS_23293B8' = '保证特定稀有度物品的首领奖励，现在会让所有选项都至少达到该稀有度。'
}

# 这两条含有富文本标签，单独赋值以避免手写时误改控制符。
$exact['AUTO_RESOURCES_ASSETS_2273174'] = '(*)<i>每个法力槽<Mana>使其造成 (xx0x1) 点伤害。'
$exact['AUTO_RESOURCES_ASSETS_22750F0'] = '(*)<i>每点邪恶<Evil>使其造成 (xx0x1) 点伤害。'

$exactSource = @{
    'Good for you!' = '真有你的！'
}

foreach ($row in $rows) {
    $reason = New-Object System.Collections.Generic.List[string]

    if ($exact.ContainsKey($row.key)) {
        $row.translation_zh = $exact[$row.key]
        $reason.Add('完整句校正')
    }
    elseif ($exactSource.ContainsKey($row.source_text)) {
        $row.translation_zh = $exactSource[$row.source_text]
        $reason.Add('上下文校正')
    }

    $translation = $row.translation_zh
    $source = $row.source_text

    if ($source -match '\bBoss(?:es)?\b') {
        $translation = $translation.Replace('老板', '首领').Replace('Boss', '首领')
    }
    if ($source -match '\bHealth\b|\bhealth\b') {
        $translation = $translation.Replace('健康酒吧', '生命条').Replace('健康显示器', '生命显示')
        $translation = $translation.Replace('健康', '生命')
    }
    if ($source -match '\bArmor\b|\barmor\b') {
        $translation = $translation.Replace('装甲集装箱', '护甲槽').Replace('装甲容器', '护甲槽')
        $translation = $translation.Replace('装甲箱', '护甲槽').Replace('装甲', '护甲')
    }
    if ($source -match '\bTrait(?:s)?\b|\btrait(?:s)?\b') {
        $translation = $translation.Replace('特征', '特质')
    }
    if ($source -match '\bReroll(?:s|ed|ing)?\b|\breroll(?:s|ed|ing)?\b') {
        $translation = $translation.Replace('重新滚动', '重掷')
    }
    if ($source -match '\bDamage\b|\bdamage\b') {
        $translation = $translation.Replace('损坏', '伤害')
        $translation = $translation.Replace('火灾伤害', '火焰伤害').Replace('顶端伤害', '最大伤害')
    }
    if ($source -match '\bDeals\b') {
        $translation = [regex]::Replace($translation, '交易(?=\s*[\[\(（]?[+#x\d])', '造成')
    }
    if ($source -match '\bCinder\b') {
        $translation = $translation.Replace('煤渣', '余烬').Replace('Cinder', '余烬')
    }
    if ($source -match '\bTick Speed\b') {
        $translation = $translation.Replace('刻度速度', '触发频率').Replace('滴答速度', '触发频率')
        $translation = $translation.Replace('Tick Speed', '触发频率')
    }
    if ($source -match '\bSwiftness\b') {
        $translation = $translation.Replace('敏捷性', '迅捷').Replace('Swiftness', '迅捷')
    }
    if ($source -match '\bMagic Find\b') {
        $translation = $translation.Replace('魔法发现', '魔法寻获').Replace('Magic Find', '魔法寻获')
    }
    if ($source -match '\bTreasure Find\b') {
        $translation = $translation.Replace('宝藏发现', '宝藏寻获').Replace('Treasure Find', '宝藏寻获')
    }
    if ($source -match '\bEquipment Item\b|\bequipment items?\b') {
        $translation = $translation.Replace('设备项目', '装备').Replace('设备物品', '装备')
    }
    if ($source -match '\bCritical Hit(?:s)?\b') {
        $translation = $translation.Replace('致命打击', '暴击').Replace('致命一击', '暴击')
    }
    if ($source -match '\bNon Critical Hits\b') {
        $translation = $translation.Replace('非致命打击', '非暴击')
    }
    if ($source -match '\bRuthless Hit(?:s)?\b') {
        $translation = $translation.Replace('无情的打击', '无情一击')
    }
    if ($source -match '\bSneaky Hit(?:s)?\b') {
        $translation = $translation.Replace('偷偷摸摸的打击', '偷袭').Replace('偷偷摸摸', '偷袭')
    }
    if ($source -match '\bBlock(?:s)?\b') {
        $translation = $translation.Replace('方块', '格挡')
    }
    if ($source -match '\bEquip Load\b') {
        $translation = $translation.Replace('装备负载', '装备重量')
    }
    if ($source -match '\bTop End Damage\b') {
        $translation = $translation.Replace('顶端伤害', '最大伤害').Replace('顶端损坏', '最大伤害')
    }
    if ($source -match '\bActor(?:s)?\b') {
        $translation = $translation.Replace('演员', '单位')
    }
    if ($source -match '\bStats\b|\bstats\b') {
        $translation = $translation.Replace('统计数据', '属性')
    }
    if ($source -match '\bFloor(?:s)?\b') {
        $translation = [regex]::Replace($translation, '(?<!地)楼层', '层')
        $translation = $translation.Replace('地板', '层')
    }
    if ($source -match '\bChance\b|\bchance\b' -and
        $source -match 'Hit|Attack|Repeat|Reward|upgrade|Shop|Luck|Jackpot|Rarity|seal|take a Critical') {
        $translation = $translation.Replace('机会', '几率')
    }

    $translation = $translation.Replace('[[also]]', '[[同样]]')
    $translation = $translation.Replace('在 Dash 上', '冲刺时').Replace('On Dash', '冲刺时')
    $translation = $translation.Replace('房间完工', '房间清理完成')
    $translation = $translation.Replace('武器等级', '武器类别')

    if ($translation -cne $row.translation_zh) {
        $row.translation_zh = $translation
        $reason.Add('术语统一')
    }

    if ($reason.Count -gt 0) {
        Add-ReviewNote -Row $row -Reason (($reason | Select-Object -Unique) -join '、')
    }
}

$invalid = @(
    $rows | Where-Object {
        [string]::IsNullOrWhiteSpace($_.translation_zh) -or
        (Get-ControlSignature $_.source_text) -cne (Get-ControlSignature $_.translation_zh)
    }
)
if ($invalid.Count -gt 0) {
    $details = ($invalid | Select-Object -First 12 key, source_text, translation_zh | Format-Table -Wrap | Out-String)
    throw "校对后存在 $($invalid.Count) 条空译文或控制符不一致：`n$details"
}

$report = @(
    foreach ($row in $rows) {
        $before = $beforeByKey[$row.key]
        if ($before -cne $row.translation_zh) {
            [pscustomobject]@{
                key = $row.key
                source_file = $row.source_file
                line_number = $row.line_number
                source_text = $row.source_text
                translation_before = $before
                translation_after = $row.translation_zh
            }
        }
    }
)

$backupPath = Join-Path (Split-Path -Parent $CsvPath) 'translations_zh.before_polish.csv'
if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $CsvPath -Destination $backupPath
}

$rows | Export-Csv -LiteralPath $CsvPath -NoTypeInformation -Encoding UTF8
$report | Export-Csv -LiteralPath $ReportPath -NoTypeInformation -Encoding UTF8

Write-Output "校对修改：$($report.Count) 条"
Write-Output "控制符异常：$($invalid.Count) 条"
Write-Output "报告：$ReportPath"
