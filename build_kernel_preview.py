"""Build a separate offline preview from the verified community 9.14 delta."""

import argparse
import hashlib
import json
import re
import shutil
import struct
import zipfile
from pathlib import Path, PurePosixPath

import UnityPy


RESOURCE = Path("Tiny Rogues_Data/resources.assets")
METADATA = Path("Tiny Rogues_Data/il2cpp_data/Metadata/global-metadata.dat")
METADATA_BASE_HASH = "2b25d17ec7d67e50ad441c0b5d45c206ac27b812692d28123a50455b0cff419f"
LITERAL_EDITS = {
    17984: ("+1 <color=#FF008CFF>魔法寻获</color><Magic_Find>",
            "+1 <color=#FF008CFF>珍品率</color><Magic_Find>"),
    692: ("##<color=#D77BBAFF>护符</color>", "##<color=#D77BBAFF>符咒</color>"),
    6197: ("最高纪录：装备{0}/4个<color=#D77BBAFF>护符</color>", "最高纪录：装备{0}/4个<color=#D77BBAFF>符咒</color>"),
    7395: ("<color=#FF008CFF>魔法寻获</color><Magic_Find>", "<color=#FF008CFF>珍品率</color><Magic_Find>"),
    7396: ("<color=#FF008CFF>魔法寻获</color><Magic_Find>\n提高以下事件的概率：\n<SubArrow>提升物品<color=#FFDB59FF>稀有</color>度\n<SubArrow>凑齐", "<color=#FF008CFF>珍品率</color><Magic_Find>\n提高以下事件的概率：\n<SubArrow>提升物品<color=#FFDB59FF>稀有</color>度\n<SubArrow>凑齐"),
    11216: ("<color=#FCC926FF>宝藏寻获</color><Treasure>", "<color=#FCC926FF>掉宝率</color><Treasure>"),
    11217: ("<color=#FCC926FF>宝藏寻获</color><Treasure>\n提高以下事件的概率：\n<SubArrow>+1首领奖励\n<SubArrow>宝箱内+1件物品\n<SubArrow>奖励数量取最大值", "<color=#FCC926FF>掉宝率</color><Treasure>\n提高以下事件的概率：\n<SubArrow>+1首领奖励\n<SubArrow>宝箱内+1件物品\n<SubArrow>奖励数量取最大值"),
    103: ("\nHow about ", "\n我出 "),
    104: ("\nI offer ", "\n我出 "),
    289: (" Gold", " 金币"),
    436: (" for it, deal?", "，成交吗？"),
    437: (" for it?", "，怎么样？"),
    671: ('"?\nA truly magnificent piece.', "」？\n真是件精品。"),
    672: ('"?\nAn okay item.', "」？\n还算不错。"),
    673: ('"?\nDecent!', "」？\n不错！"),
    674: ('"?\nI mean if you really\nwant to get rid of it...', "」？\n你要是真想\n把它出手……"),
    675: ('"?\nNot the best...', "」？\n东西一般……"),
    676: ('"?\nNothing special,\nbut I can take it.', "」？\n没什么特别的，\n不过我可以收下。"),
    677: ('"?\nThat\'s a nice one,\nnot going to lie.', "」？\n说实话，\n这件挺不错。"),
    678: ('"?\nThat\'s pretty nice.', "」？\n这件挺不错。"),
    679: ('"?\nYou are one lucky fellow!', "」？\n你运气可真好！"),
    5391: ("Exit", "离开"),
    6214: ('Hmm, a "', "嗯，这件「"),
    8046: ('Now we are talking.\nI know some folks that would give\ntheir left leg for a "', "这才像话。\n我认识几个家伙，\n为了这件「"),
    9646: ('So so, a "', "嗯，这件「"),
    10186: ("Talk", "对话"),
    11518: ('Ugh, a "', "呃，这件「"),
    11853: ("Upgrade", "升级"),
    11856: ("Upgrade <color=grey>[ALREADY AT MAX]</color>", "升级 <color=grey>[已满级]</color>"),
}
EDITS = {
    53017: (
        ("(*)<i>你与伙伴造成的<color=#EDDE99FF>光耀</color>伤害<Companion>施加<color=#76428AFF>易伤</color>。</i>",
         "(*)<i>你或伙伴<Companion>造成<color=#EDDE99FF>光耀</color>伤害时，对目标施加<color=#76428AFF>易伤</color>。</i>", 1),
    ),
    53353: (
        ("你和你伙伴造成的<color=#EDDE99FF>光耀</color>伤害<Companion>，赋予你燃烧热情。",
         "你或伙伴<Companion>造成<color=#EDDE99FF>光耀</color>伤害时，你获得燃烧热情。", 1),
    ),
    53360: (
        ("你和你伙伴造成的<color=#6E5442FF>穿刺</color>伤害<Companion>施加<color=#6E5442FF>穿刺</color>状态。",
         "你或伙伴<Companion>造成<color=#6E5442FF>刺击</color>伤害时，对目标施加<color=#6E5442FF>刺伤</color>。", 1),
    ),
    55153: (
        ("(*)<i>你和你伙伴的刺击伤害<Companion>会施加<color=#FF3326FF>流血</color>。</i>",
         "(*)<i>你或伙伴<Companion>造成刺击伤害时，对目标施加<color=#FF3326FF>流血</color>。</i>", 1),
    ),
    56328: (
        ("你与伙伴的<Companion>造成<color=#00E200FF>坏死</color>与<color=#018606FF>毒素</color>伤害，并施加<color=#DF7126FF>脆弱</color>。",
         "你或伙伴<Companion>造成<color=#00E200FF>坏死</color>或<color=#018606FF>毒素</color>伤害时，对目标施加<color=#DF7126FF>脆弱</color>。", 1),
    ),
    56378: (
        ("你与伙伴的<Companion>造成<color=#6E5442FF>打击</color>伤害，并施加<color=#FF3326FF>不稳定</color>。",
         "你或伙伴<Companion>造成<color=#6E5442FF>打击</color>伤害时，对目标施加<color=#FF3326FF>不稳定</color>。", 1),
    ),
    56397: (
        ("你与伙伴<Companion>造成的<color=#6E5442FF>斩击</color>伤害会施加<color=#FF3326FF>流血</color>。 ",
         "你或伙伴<Companion>造成<color=#6E5442FF>斩击</color>伤害时，对目标施加<color=#FF3326FF>流血</color>。", 1),
    ),
    52239: (
        ('获得(x0)<color=#00D608FF>幸运</color><sprite name="Luck">，于等级[[1]]时生效，',
         '以下等级各获得(x0)<color=#00D608FF>幸运</color><sprite name="Luck">：[[1]]、', 2),
    ),
    52240: (
        (" [[3]]并且", "[[3]]、", 2),
    ),
    52271: (
        ('获得(x0)<color=#26B0FFFF>法力</color><sprite name="Mana">，于等级[[2]]时生效，',
         '以下等级各获得(x0)<color=#26B0FFFF>法力</color><sprite name="Mana">：[[2]]、', 2),
    ),
    52272: (
        (" [[4]]且", "[[4]]、", 2),
    ),
    52609: (
        ("对所有敌人施加威慑。", "对所有敌人施加威吓。", 1),
    ),
    52657: (
        ("你的移动速度修正也[[also]]适用于<color=#26B0FFFF>魔法</color>伤害。\n(current)",
         "你的移动速度修正[[也]]适用于<color=#26B0FFFF>魔法</color>伤害。\n(current)", 1),
    ),
    52917: (
        ("(*)<i>使用<color=#A61FFFFF>技能</color>时，对所有敌人施加虚弱。</i>",
         "(*)<i>使用<color=#A61FFFFF>技能</color>时，对所有敌人施加易伤。</i>", 1),
    ),
    53021: (
        ("(br)(*)(+x0%)毒性效果", "(br)(*)(+x0%)毒蚀效果", 2),
    ),
    53078: (
        ("施加<color=#D77BBAFF>魅惑</color>时，同时施加<color=#DF7126FF>脆弱</color>。",
         "施加<color=#D77BBAFF>魅惑</color>时，同时施加<color=#76428AFF>易伤</color>。", 1),
    ),
    53211: (
        ("从<color=#26FF66FF>敏捷</color>中获得(+x0%)属性，但",
         "<color=#26FF66FF>敏捷</color>提供的属性 (+x0%)；", 2),
    ),
    53212: (
        ("从<color=#FF2666FF>力量</color>中获得(-x0%)属性，并",
         "<color=#FF2666FF>力量</color>提供的属性 (-x0%)，同样的减幅也适用于", 2),
    ),
    53225: (
        ("在远距离获得(+x0%)<color=#26FF66FF>致命一击几率</color><Lethal>。<Far>",
         "在远距离<Far>时，获得 (+x0%) <color=#26FF66FF>致命一击几率</color><Lethal>。", 2),
    ),
    53266: (
        ("你的<color=#A61FFFFF>攻击</color>获得(chance)在命中时<color=#A61FFFFF>触发</color>(actionName)，各造成(damage)点伤害。",
         "你的<color=#A61FFFFF>攻击</color>命中时有 (chance) 几率<color=#A61FFFFF>触发</color> (actionName)，每枚造成 (damage) 点伤害。", 1),
    ),
    53261: (
        ("(*)<i>提供(+x0%)<color=#A61FFFFF>环绕物</color>范围。</i>\n(*)<i>你的<color=#A61FFFFF>环绕物</color>造成虚弱。</i>",
         "(*)<i>提供(+x0%)<color=#A61FFFFF>环绕物</color>范围。</i>\n(*)<i>你的<color=#A61FFFFF>环绕物</color>施加易伤。</i>", 2),
    ),
    53243: (
        ("冰冷额外添加(+x0%)受到暴击的几率<Crit>。",
         "冰缓额外使受到暴击的几率<Crit>提高 (+x0%)。", 2),
    ),
    53373: (
        ("(br)(*)<i>阴影<color=#A61FFFFF>环绕物</color>会一次性施加[[所有]]层忧郁效果。</i>",
         "(br)(*)<i>阴影<color=#A61FFFFF>环绕物</color>会一次性施加[[所有]]层阴郁。</i>", 2),
    ),
    55477: (
        ("(*)<i>你的<color=#EDDE99FF>光耀</color>伤害会施加<color=#DF7126FF>灼烧</color>、冰冻和<color=#FFE53DFF>感电</color>。</i>",
         "(*)<i>你的<color=#EDDE99FF>光耀</color>伤害会施加<color=#DF7126FF>灼烧</color>、冰缓和<color=#FFE53DFF>感电</color>。</i>", 1),
    ),
    56010: (
        ("冰寒", "冰缓", 1),
    ),
    56033: (
        ("中毒", "毒蚀", 1),
    ),
    55814: (
        ('每次运行一次，当你进入第5层之后的楼层且没有<color=#3B3B7AFF>炸弹</color>时<sprite name="Bomb">，获得[[3]]个<color=#3B3B7AFF>炸弹</color><sprite name="Bomb">。',
         '每局限一次：进入第5层之后的楼层时，若没有<color=#3B3B7AFF>炸弹</color><sprite name="Bomb">，获得[[3]]个<color=#3B3B7AFF>炸弹</color><sprite name="Bomb">。', 1),
    ),
    55857: (
        ("每次奔跑中，当你进入第5层之后的楼层时，如果没有<color=#FCC926FF>金币</color><Gold>，则获得[[10]]<color=#FCC926FF>金币</color><Gold>。",
         "每局限一次：进入第5层之后的楼层时，若没有<color=#FCC926FF>金币</color><Gold>，获得[[10]]<color=#FCC926FF>金币</color><Gold>。", 1),
    ),
    55864: (
        ("每次奔跑你有[[+10%]]的几率遇到皇家军械库。\n<color=grey>[添加到5%的基础几率上。]</color>",
         "每局遇到皇家军械库的几率[[+10%]]。\n<color=grey>[在5%基础几率上叠加。]</color>", 1),
    ),
    56128: (
        ('(xx0) 受到的伤害\n在近距离<sprite name="Close">',
         '近距离<sprite name="Close">时，受到的伤害\n变为 (xx0)', 1),
        ('(*)<i>(xx0) 受到的伤害 \n在近距离<sprite name="Close"></i>',
         '(*)<i>近距离<sprite name="Close">时，受到的伤害\n变为 (xx0)</i>', 1),
    ),
    56187: (
        ("(xx0) Damage with Non Critical Hits", "非暴击命中的伤害 (xx0)", 1),
        ("(*)(xx0) Damage with Non Critical Hits", "(*)非暴击命中的伤害 (xx0)", 1),
    ),
}
INFUSIONS = {
    "Cold": ("冰冷", (56167, 56169, 56171)),
    "Fire": ("火焰", (56168, 56170, 56177)),
    "Lightning": ("闪电", (56172, 56173, 56179)),
    "Poison": ("剧毒", (56174, 56178)),
    "Radiant": ("光耀", (56175,)),
    "Nature": ("自然", (56176,)),
}
for element, (label, object_ids) in INFUSIONS.items():
    for object_id in object_ids:
        EDITS[object_id] = tuple(
            (f"{prefix}(x0) [[to]] (#x1) {element} Damage to Weapons",
             f"{prefix}为武器附加 (x0) [[至]] (#x1) 点{label}伤害", 1)
            for prefix in ("", "(*)")
        )

TOKENS = re.compile(r'<[^>]+>|\([#A-Za-z0-9%]+\)|\(\*\)|\[\[|\]\]')
for object_id, edits in {
    51902: (("用<color=#FCC926FF>金币</color>##购买\n护身符<Gold>。", "用<color=#FCC926FF>金币</color>##购买\n符咒<Gold>。", 1),),
    51925: (("用<color=#FCC926FF>金币</color>##购买\n护身符<Gold>。", "用<color=#FCC926FF>金币</color>##购买\n符咒<Gold>。", 1),),
    52245: (("获得(+x0%)来自//护身符和 ", "获得(+x0%)来自//符咒和 ", 2),),
    52256: (("(x0)<color=#FCC926FF>宝藏寻获</color><Treasure>", "(x0)<color=#FCC926FF>掉宝率</color><Treasure>", 2),),
    52321: ((" (x0) <color=#FF008CFF>魔法寻获</color><Magic_Find>", " (x0) <color=#FF008CFF>珍品率</color><Magic_Find>", 2),),
    52323: (("(x0)<color=#FCC926FF>宝藏寻获</color><Treasure>", "(x0)<color=#FCC926FF>掉宝率</color><Treasure>", 2),),
    52325: (("(*)(x0) <color=#FCC926FF>宝藏寻获</color>率<Treasure>", "(*)(x0) <color=#FCC926FF>掉宝率</color>率<Treasure>", 1), ("(x0)<color=#FCC926FF>宝藏寻获</color><Treasure>", "(x0)<color=#FCC926FF>掉宝率</color><Treasure>", 1),),
    52345: ((" (x0) <color=#FF008CFF>魔法寻获</color><Magic_Find>", " (x0) <color=#FF008CFF>珍品率</color><Magic_Find>", 2),),
    52367: (("(x0)<color=#FCC926FF>宝藏寻获</color><Treasure>", "(x0)<color=#FCC926FF>掉宝率</color><Treasure>", 2),),
    52406: (("(x0)<color=#FCC926FF>宝藏寻获</color><Treasure>", "(x0)<color=#FCC926FF>掉宝率</color><Treasure>", 1), ("(*)<i>每拥有一点<color=#FCC926FF>善良</color><Good>，<color=#FCC926FF>宝藏寻获</color><Treasure> (x0x1) <g>（当前加成：(x0)）</g></i>", "(*)<i>每拥有一点<color=#FCC926FF>善良</color><Good>，<color=#FCC926FF>掉宝率</color><Treasure> (x0x1) <g>（当前加成：(x0)）</g></i>", 1),),
    52408: (("(x0)<color=#FCC926FF>宝藏寻获</color><Treasure>", "(x0)<color=#FCC926FF>掉宝率</color><Treasure>", 1), ("(*)<i>每拥有一点<color=#7C8990FF>混乱</color><Chaos>，<color=#FCC926FF>宝藏寻获</color><Treasure> (x0x1) <g>（当前加成：(x0)）</g></i>", "(*)<i>每拥有一点<color=#7C8990FF>混乱</color><Chaos>，<color=#FCC926FF>掉宝率</color><Treasure> (x0x1) <g>（当前加成：(x0)）</g></i>", 1),),
    52409: (("(x0)<color=#FCC926FF>宝藏寻获</color><Treasure>", "(x0)<color=#FCC926FF>掉宝率</color><Treasure>", 1), ("(*)<i>每拥有一点<color=#5ECCE3FF>守序</color><Lawful>，<color=#FCC926FF>宝藏寻获</color><Treasure> (x0x1) <g>（当前加成：(x0)）</g></i>", "(*)<i>每拥有一点<color=#5ECCE3FF>守序</color><Lawful>，<color=#FCC926FF>掉宝率</color><Treasure> (x0x1) <g>（当前加成：(x0)）</g></i>", 1),),
    52410: (("(x0)<color=#FCC926FF>宝藏寻获</color><Treasure>", "(x0)<color=#FCC926FF>掉宝率</color><Treasure>", 1), ("(*)<i>每拥有一点<color=#FF0000FF>邪恶</color><Evil>，<color=#FCC926FF>宝藏寻获</color><Treasure> (x0x1) <g>（当前加成：(x0)）</g></i>", "(*)<i>每拥有一点<color=#FF0000FF>邪恶</color><Evil>，<color=#FCC926FF>掉宝率</color><Treasure> (x0x1) <g>（当前加成：(x0)）</g></i>", 1),),
    52421: (("(*)(x0) <color=#FCC926FF>宝藏寻获</color>率<Treasure>", "(*)(x0) <color=#FCC926FF>掉宝率</color>率<Treasure>", 2),),
    52455: (("(*)(+x0%)来自//护身符的属性", "(*)(+x0%)来自//符咒的属性", 2),),
    52462: (("(*)(x0) <color=#FF008CFF>魔法寻获</color><Magic_Find>", "(*)(x0) <color=#FF008CFF>珍品率</color><Magic_Find>", 2),),
    52539: (("(br)(*)(x0)<color=#FF008CFF>魔法寻获</color><Magic_Find>", "(br)(*)(x0)<color=#FF008CFF>珍品率</color><Magic_Find>", 2),),
    52548: (("(*)(x0) <color=#FCC926FF>宝藏寻获</color>率<Treasure>", "(*)(x0) <color=#FCC926FF>掉宝率</color>率<Treasure>", 2),),
    52552: (("(br)(*)<i>每拥有一次<color=#FCC926FF>复活</color>机会<Revive>，<color=#FF008CFF>魔法寻获</color><Magic_Find> (x0x1)</i>", "(br)(*)<i>每拥有一次<color=#FCC926FF>复活</color>机会<Revive>，<color=#FF008CFF>珍品率</color><Magic_Find> (x0x1)</i>", 2),),
    52553: (("(br)(*)<i>每拥有一次<color=#FCC926FF>复活</color>机会<Revive>，<color=#FCC926FF>宝藏寻获</color><Treasure> (x0x1)</i>", "(br)(*)<i>每拥有一次<color=#FCC926FF>复活</color>机会<Revive>，<color=#FCC926FF>掉宝率</color><Treasure> (x0x1)</i>", 2),),
    52579: (("(*)(x0) <color=#FF008CFF>魔法寻获</color><Magic_Find>", "(*)(x0) <color=#FF008CFF>珍品率</color><Magic_Find>", 2),),
    52598: (("(*)(x0) <color=#FF008CFF>魔法寻获</color><Magic_Find>", "(*)(x0) <color=#FF008CFF>珍品率</color><Magic_Find>", 2),),
    52698: (("(*)(x0) <color=#FCC926FF>宝藏寻获</color>率<Treasure>", "(*)(x0) <color=#FCC926FF>掉宝率</color>率<Treasure>", 2),),
    52706: (("(*)(x0) <color=#FF008CFF>魔法寻获</color><Magic_Find>", "(*)(x0) <color=#FF008CFF>珍品率</color><Magic_Find>", 2),),
    52713: (("(*)(x0) <color=#FCC926FF>宝藏寻获</color>率<Treasure>", "(*)(x0) <color=#FCC926FF>掉宝率</color>率<Treasure>", 2),),
    52746: (("(*)(x0) <color=#FF008CFF>魔法寻获</color><Magic_Find>", "(*)(x0) <color=#FF008CFF>珍品率</color><Magic_Find>", 2),),
    52916: (("(*)(x0) <color=#FCC926FF>宝藏寻获</color>率<Treasure>", "(*)(x0) <color=#FCC926FF>掉宝率</color>率<Treasure>", 2),),
    53104: (("每拥有一个<color=#26B0FFFF>法力</color>容器<Mana>，<color=#FF008CFF>魔法寻获</color><Magic_Find> (x0x1)。 <color=grey>（当前加成：(x0)）</color>", "每拥有一个<color=#26B0FFFF>法力</color>容器<Mana>，<color=#FF008CFF>珍品率</color><Magic_Find> (x0x1)。 <color=grey>（当前加成：(x0)）</color>", 2),),
    53158: (("(x0) <color=#FF008CFF>魔法寻获</color><Magic_Find>", "(x0) <color=#FF008CFF>珍品率</color><Magic_Find>", 2),),
    53403: (("(*)<i>获得(x0)点<color=#FF008CFF>魔法寻获</color><Magic_Find>。</i>(br)", "(*)<i>获得(x0)点<color=#FF008CFF>珍品率</color><Magic_Find>。</i>(br)", 2),),
    53404: (("(*)<i>获得(x0)点<color=#FCC926FF>宝藏寻获</color><Treasure>。</i>", "(*)<i>获得(x0)点<color=#FCC926FF>掉宝率</color><Treasure>。</i>", 2),),
    53822: (("奖励选择\n包括[[至少]]\n[[3]]个##护身符。", "奖励选择\n包括[[至少]]\n[[3]]个##符咒。", 1),),
    53953: (("必定获得护符", "必定获得符咒", 1), ("奖励选项\n[[至少]]包含\n[[1]] ##<color=#D77BBAFF>护符</color>.", "奖励选项\n[[至少]]包含\n[[1]] ##<color=#D77BBAFF>符咒</color>.", 1),),
    54074: (("随机护符", "随机符咒", 1), ("随机获得 ##<color=#D77BBAFF>护符</color>.", "随机获得 ##<color=#D77BBAFF>符咒</color>.", 1),),
    54868: (("同时装备4个<color=#D77BBAFF>护符</color>。", "同时装备4个<color=#D77BBAFF>符咒</color>。", 1),),
    55360: (("深渊护符", "深渊符咒", 1),),
    55361: (("天使护符", "天使符咒", 1),),
    55362: (("护甲护符", "护甲符咒", 1),),
    55363: (("蔚蓝护符", "蔚蓝符咒", 1),),
    55364: (("暴风雪护符", "暴雪符咒", 1),),
    55365: (("格挡护符", "格挡符咒", 1),),
    55366: (("骨制护符", "骨制符咒", 1),),
    55368: (("拳击护符", "拳击符咒", 1),),
    55369: (("斗士护符", "斗士符咒", 1),),
    55370: (("混沌护符", "混沌符咒", 1),),
    55371: (("三叶草护符", "三叶草符咒", 1),),
    55372: (("十字护符", "十字符咒", 1),),
    55373: (("恶魔护符", "恶魔符咒", 1),),
    55374: (("龙眼护符", "龙眼符咒", 1),),
    55375: (("龙裔护符", "龙裔符咒", 1),),
    55376: (("隐秘护符", "隐秘符咒", 1),),
    55377: (("能量护符", "能量符咒", 1),),
    55378: (("闪避护符", "闪避符咒", 1),),
    55379: (("火鸟护符", "火鸟符咒", 1),),
    55380: (("药瓶护符", "药瓶符咒", 1),),
    55381: (("制箭护符", "制箭符咒", 1),),
    55382: (("流动护符", "流动符咒", 1),),
    55383: (("幸运护符", "幸运符咒", 1),),
    55384: (("友谊护符", "友谊符咒", 1),),
    55385: (("石榴石护符", "石榴石符咒", 1),),
    55386: (("凝视护符", "凝视符咒", 1),),
    55390: (("哥布林护符", "哥布林符咒", 1),),
    55391: (("黄金护符", "黄金符咒", 1),),
    55392: (("心灵护符", "心灵符咒", 1),),
    55393: (("英雄护符", "英雄符咒", 1),),
    55394: (("巫术护符", "巫术符咒", 1),),
    55395: (("小鬼护符", "小鬼符咒", 1),),
    55396: (("翡翠护符", "翡翠符咒", 1),),
    55397: (("法力护符", "法力符咒", 1),),
    55398: (("心灵护符", "心灵符咒", 1),),
    55399: (("力量护符", "力量符咒", 1),),
    55400: (("宝珠护符", "宝珠符咒", 1),),
    55401: (("秩序护符", "秩序符咒", 1),),
    55402: (("精准护符", "精准符咒", 1),),
    55403: (("兔之护符", "兔之符咒", 1),),
    55405: (("<rainbow>彩虹护符</rainbow>", "<rainbow>彩虹符咒</rainbow>", 1),),
    55406: (("延长护符", "延长符咒", 1),),
    55407: (("焕发护符", "焕发符咒", 1),),
    55408: (("根之护符", "根之符咒", 1),),
    55409: (("学者护符", "学者符咒", 1),),
    55410: (("技能护符", "技能符咒", 1),),
    55411: (("骷髅护符", "骷髅符咒", 1),),
    55412: (("雪鸟护符", "雪鸟符咒", 1),),
    55413: (("灵魂之心护符", "灵魂之心符咒", 1),),
    55414: (("耐力护符", "耐力符咒", 1),),
    55415: (("压制护符", "压制符咒", 1),),
    55416: (("破旧技能护符", "破旧技能符咒", 1),),
    55417: (("雷鸟护符", "雷鸟符咒", 1),),
    55418: (("虎之护符", "虎之符咒", 1),),
    55424: (("魔法寻获升级", "珍品率升级", 1),),
    55429: (("警戒护符", "警戒符咒", 1),),
    55430: (("疾风护符", "疾风符咒", 1),),
    55431: (("僵尸护符", "僵尸符咒", 1),),
    55641: (("召唤师护符", "魔术师护符", 1),),
    55767: (("提前1个房间找到首领房间。 <g>[##护身符]</g>", "提前1个房间找到首领房间。 <g>[##符咒]</g>", 1),),
    55770: (("获得[[+15%]]食物奖励升级的几率。 <g>[##护身符]</g>", "获得[[+15%]]食物奖励升级的几率。 <g>[##符咒]</g>", 1),),
    55779: (("进入一层时恢复[[2]]颗心<sprite name=\"Heart\">。<g>[##<color=#D77BBAFF>护符</color>]</g>", "进入一层时恢复[[2]]颗心<sprite name=\"Heart\">。<g>[##<color=#D77BBAFF>符咒</color>]</g>", 1),),
    55815: (("当一种阵营为2或更高，另外三种为1或更低时：\n获得[[+1]]<color=#FCC926FF>宝藏寻获</color><Treasure>。\n<g>（阵营为<color=#FCC926FF>善良</color><Good>、<color=#FF0000FF>邪恶</color><Evil>、<color=#5ECCE3FF>守序</color><Lawful>或<color=#7C8990FF>混乱</color><Chaos>。）</g>\n", "当一种阵营为2或更高，另外三种为1或更低时：\n获得[[+1]]<color=#FCC926FF>掉宝率</color><Treasure>。\n<g>（阵营为<color=#FCC926FF>善良</color><Good>、<color=#FF0000FF>邪恶</color><Evil>、<color=#5ECCE3FF>守序</color><Lawful>或<color=#7C8990FF>混乱</color><Chaos>。）</g>\n", 1),),
    55819: (("黑市总是有巫师出售##<color=#D77BBAFF>护符</color>。\n你还在那个商店获得[[50%]]折扣。", "黑市总是有巫师出售##<color=#D77BBAFF>符咒</color>。\n你还在那个商店获得[[50%]]折扣。", 1),),
    55846: (("打开\n5个宝箱后，\n永久获得 \n[[+1]] <color=#FF008CFF>魔法寻获</color><Magic_Find>。", "打开\n5个宝箱后，\n永久获得 \n[[+1]] <color=#FF008CFF>珍品率</color><Magic_Find>。", 1),),
    55880: (("在第1层，必定有一扇门通向##<color=#D77BBAFF>护符</color>奖励作为首领奖励。", "在第1层，必定有一扇门通向##<color=#D77BBAFF>符咒</color>奖励作为首领奖励。", 1),),
    55888: (("无伤击败首领将\n在本次奖励选择中获得[[+1]]<color=#FF008CFF>魔法寻获</color><sprite name=\"Magic_Find\">。", "无伤击败首领将\n在本次奖励选择中获得[[+1]]<color=#FF008CFF>珍品率</color><sprite name=\"Magic_Find\">。", 1),),
    55964: (("每打开一个礼物盒，随机获得以下一种加成：\n<SubArrow> [[+1]]<color=#00D608FF>幸运</color><Luck>、\n<SubArrow> [[+1]]<color=#FCC926FF>宝藏寻获</color><Treasure>或\n<SubArrow> [[+1]]<color=#FF008CFF>魔法寻获</color><Magic_Find>。", "每打开一个礼物盒，随机获得以下一种加成：\n<SubArrow> [[+1]]<color=#00D608FF>幸运</color><Luck>、\n<SubArrow> [[+1]]<color=#FCC926FF>掉宝率</color><Treasure>或\n<SubArrow> [[+1]]<color=#FF008CFF>珍品率</color><Magic_Find>。", 1),),
    56102: (("(x0) <color=#FF008CFF>魔法寻获</color><sprite name=\"Magic_Find\">", "(x0) <color=#FF008CFF>珍品率</color><sprite name=\"Magic_Find\">", 2),),
    56108: (("(x0)<color=#FCC926FF>宝藏寻获</color><Treasure>", "(x0)<color=#FCC926FF>掉宝率</color><Treasure>", 1), ("(*)(x0) <color=#FCC926FF>宝藏寻获</color>率<Treasure>", "(*)(x0) <color=#FCC926FF>掉宝率</color>率<Treasure>", 1),),
    57515: (("+3魔法寻获<Magic_Find>", "+3珍品率<Magic_Find>", 1),),
}.items():
    EDITS[object_id] = EDITS.get(object_id, ()) + edits
COLOR_TAG = re.compile(r'<color=#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?>')
NUMBER = re.compile(r'[+-]?\d+(?:\.\d+)?%?')


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def checked_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or not path.parts:
        raise ValueError(f"Unsafe path: {name}")
    return Path(*path.parts)


def unity_string(text, endian):
    encoded = text.encode("utf-8")
    return struct.pack(endian + "I", len(encoded)) + encoded + b"\0" * (-len(encoded) % 4)


def patch_resources(source, target):
    env = UnityPy.load(str(source))
    objects = {obj.path_id: obj for obj in env.objects}
    expected = {}
    for object_id, edits in EDITS.items():
        obj = objects[object_id]
        if obj.type.name != "MonoBehaviour":
            raise ValueError(f"Unexpected object type: {object_id}")
        raw = obj.get_raw_data()
        for old, new, count in edits:
            old_tokens = sorted(TOKENS.findall(COLOR_TAG.sub("<color>", old)))
            new_tokens = sorted(TOKENS.findall(COLOR_TAG.sub("<color>", new)))
            if old_tokens != new_tokens:
                raise ValueError(f"Control tokens changed: {object_id}")
            if NUMBER.findall(re.sub(r'<[^>]+>', '', old)) != NUMBER.findall(re.sub(r'<[^>]+>', '', new)):
                raise ValueError(f"Numeric values changed: {object_id}")
            old_blob = unity_string(old, obj.reader.endian)
            offsets = [m.start() for m in re.finditer(re.escape(old_blob), raw)]
            if len(offsets) != count or any(offset % 4 for offset in offsets):
                raise ValueError(f"Unexpected serialized strings: {object_id}")
            raw = raw.replace(old_blob, unity_string(new, obj.reader.endian))
        obj.set_raw_data(raw)
        expected[object_id] = raw

    with target.open("xb") as handle:
        handle.write(env.file.save())
    rebuilt = {obj.path_id: obj for obj in UnityPy.load(str(target)).objects}
    original = {obj.path_id: obj for obj in UnityPy.load(str(source)).objects}
    if rebuilt.keys() != original.keys():
        raise ValueError("Resource object IDs changed")
    for object_id, obj in rebuilt.items():
        before = original[object_id]
        if obj.type != before.type or obj.get_raw_data() != expected.get(object_id, before.get_raw_data()):
            raise ValueError(f"Unexpected rebuilt resource object: {object_id}")


def patch_metadata(source, target):
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != METADATA_BASE_HASH:
        raise ValueError("Unexpected metadata baseline")
    magic, version, table, table_size, text, text_size = struct.unpack_from("<6I", data)
    if (magic, version) != (0xFAB11BAF, 31) or table_size % 8 or table + table_size != text or text + text_size != len(data):
        raise ValueError("Unexpected metadata literal table layout")

    def literal(blob, index):
        length, offset = struct.unpack_from("<II", blob, table + 8 * index)
        return blob[text + offset:text + offset + length]

    # shortcut: this baseline keeps the literal data at EOF; revisit the layout for other builds.
    updated = bytearray(data)
    for index, (old, new) in LITERAL_EDITS.items():
        if literal(data, index) != old.encode("utf-8") or old.count("\n") != new.count("\n"):
            raise ValueError(f"Unexpected source literal: {index}")
        encoded = new.encode("utf-8")
        struct.pack_into("<II", updated, table + 8 * index, len(encoded), len(updated) - text)
        updated.extend(encoded)
    struct.pack_into("<I", updated, 20, len(updated) - text)

    for index in range(table_size // 8):
        expected = LITERAL_EDITS[index][1].encode("utf-8") if index in LITERAL_EDITS else literal(data, index)
        if literal(updated, index) != expected:
            raise ValueError(f"Unexpected rebuilt literal: {index}")
    with target.open("xb") as handle:
        handle.write(updated)


def build(game, archive, decoded, output):
    game, decoded, output = (p.resolve() for p in (game, decoded, output))
    if output.is_relative_to(game) or output.is_relative_to(decoded):
        raise ValueError("Preview must be outside the game and decoded directories")
    with zipfile.ZipFile(archive) as z:
        manifests = [name for name in z.namelist() if name.endswith("/patch-manifest.json")]
        if len(manifests) != 1:
            raise ValueError("Expected exactly one patch manifest")
        manifest = json.loads(z.read(manifests[0]))
    if manifest.get("workbench_version") != "0.11.4" or manifest.get("architecture") != "offline-resources":
        raise ValueError("This preview targets the 9.14 offline package")
    originals = {checked_path(name): meta["sha256"] for name, meta in manifest["baseline"].items()}
    patched = {checked_path(entry["file"]): entry["after"]["sha256"] for entry in manifest["files"]}
    if not patched.keys() <= originals.keys() or not {RESOURCE, METADATA} <= patched.keys():
        raise ValueError("Patch targets are outside the original manifest")
    for files, root in ((originals, game), (patched, decoded)):
        for path, expected in files.items():
            if digest(root / path) != expected:
                raise ValueError(f"Unexpected hash: {root / path}")

    output.mkdir()
    for path in originals:
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if path == RESOURCE:
            patch_resources(decoded / path, target)
        elif path == METADATA:
            patch_metadata(decoded / path, target)
        else:
            source = (decoded if path in patched else game) / path
            shutil.copyfile(source, target)
            if digest(target) != (patched[path] if path in patched else originals[path]):
                raise ValueError(f"Copy verification failed: {target}")
    print(f"Verified {len(originals)} original files, {len(patched)} delta outputs, "
          f"and {sum(count for edits in EDITS.values() for _, _, count in edits)} template fields.")
    print(output / "Tiny Rogues.exe")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("game", "archive", "decoded", "output"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    build(args.game, args.archive, args.decoded, args.output)
