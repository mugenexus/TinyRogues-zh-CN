import unittest

from audit_runtime_coverage import ROOT, flatten_decorated_ascii_runs, load_pairs
from audit_runtime_residuals import apply_fragments, load_exact, load_regex_pairs, translate


class RuntimeTranslationTest(unittest.TestCase):
    def test_only_explicit_per_level_conditions_are_translated_as_per_level(self):
        fragments = load_pairs(ROOT / "runtime_item_fragments_zh.txt")
        fragments.sort(key=lambda pair: len(pair[0]), reverse=True)
        for source, expected in (
            ("Deals 25", "造成25"),
            ("Gains +10%", "获得+10%"),
            ("Deals <color=#00E61A>25</color> Damage per Level.",
             "造成<color=#00E61A>25</color>伤害（每级）。"),
            ("Gains <color=#00E61A>+10%</color> Range per Level.",
             "获得<color=#00E61A>+10%</color>射程（每级）。"),
            ("<color=#00E61A>+10%</color>per Level.",
             "<color=#00E61A>+10%</color>（每级）。"),
        ):
            with self.subTest(source=source):
                self.assertEqual(apply_fragments(source, fragments), expected)

    def test_pocket_magic_preserves_dynamic_interval(self):
        exact = load_exact()
        regexes = load_regex_pairs()
        for interval, attack, weapon, tick in (
            ("Every 1 second ", "Attack", "Weapon", "Tick"),
            ("Every\u00a02.5\u00a0seconds", "Attack", "Weapon", "Tick"),
            ("每 2.5 秒", "攻击", "武器", "周期"),
        ):
            with self.subTest(interval=interval):
                source = (
                    f"<size=100%><color=#00E61A>{interval}</color> "
                    f"<color=#A61FFF>trigger</color> an <color=#A61FFF>{attack}</color>"
                    f" of a random Wand or Staff <color=#A61FFF>{weapon}</color> in your Inventory."
                    f"<color=#808080>\n({weapon} Enchantments will not apply.)</color>"
                    f" <color=#808080>[<color=#A61FFF>{tick}</color>]</color></size>"
                )
                expected_seconds = "1" if "1" in interval else "2.5"
                expected = (
                    f"<size=100%><color=#00E61A>每 {expected_seconds} 秒</color>"
                    "<color=#A61FFF>触发</color>一次背包中随机魔杖或法杖武器的"
                    "<color=#A61FFF>攻击</color>。<color=#808080>\n（武器附魔不生效。）</color>"
                    " <color=#808080>[<color=#A61FFF>周期</color>]</color></size>"
                )
                self.assertEqual(translate("Trait Description", source, exact, {}, regexes, [], []), expected)

    def test_rainbow_label_keeps_nonbreaking_separator(self):
        source = "".join(f"<color=#123456>{part}</color>" for part in ("C", "o", "a", "t", "l", "\u00a0", "B", "u", "r", "s", "t"))
        self.assertEqual(flatten_decorated_ascii_runs(source), "Coatl\u00a0Burst")


if __name__ == "__main__":
    unittest.main()
