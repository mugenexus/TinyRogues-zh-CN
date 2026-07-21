from __future__ import annotations

import csv
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from audit_translations import find_separator


ROOT = Path(__file__).resolve().parent
HISTORY_FILES = [
    ROOT / "runtime_untranslated_before_1.5.1.txt",
    ROOT / "runtime_untranslated_1.5.1.txt",
    ROOT / "runtime_untranslated_1.5.2_pre_final.txt",
    ROOT / "runtime_untranslated_1.5.2_live_audit.txt",
    ROOT / "runtime_untranslated_1.5.3.txt",
    ROOT / "runtime_untranslated_1.5.10_live.txt",
]
LIVE_TEXT_DIR = Path(
    os.environ.get(
        "TINYROGUES_TEXT_DIR",
        r"D:\SteamLibrary\steamapps\common\Tiny Rogues\BepInEx\Translation\zh\Text",
    )
)
LIVE_UNTRANSLATED_FILE = LIVE_TEXT_DIR / "_TmpUntranslated.txt"
LIVE_RESIDUAL_FILE = LIVE_TEXT_DIR / "_TmpResidualEnglish.txt"
REPORT_FILE = ROOT / "runtime_coverage_audit.csv"
SUMMARY_FILE = ROOT / "runtime_coverage_summary.csv"

TAG_RE = re.compile(r"<[^>]+>")
DECORATED_ASCII_RUN_RE = re.compile(
    r"(?:<color=[^>]+>[A-Za-z ]</color>){4,}", re.IGNORECASE
)
CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
ENGLISH_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{1,}")
TECHNICAL_COMPONENTS = {
    "Error Message",
    'Label: "Cheat Console"',
    'Label: "CRT"',
}
VISIBLE_EXACT_COMPONENTS = {
    "Tooltip Title (TMP)",
    "Tooltip Text (TMP)",
    "Description Text",
    "Elite Enchantment Text",
    "Main Header",
    "Title Text",
    "Trait Title",
    "Choice 1 (TMP)",
}
TECHNICAL_TEXT_PATTERNS = [
    re.compile(r"^\(?\d+ Errors?\)?", re.IGNORECASE),
    re.compile(r"^\d+(?:\.\d+){2,} "),
    re.compile(r"^(?:Tab|Shift|Esc|Enter|Space)$", re.IGNORECASE),
    re.compile(r"^(?:PC Senior|Retro|CRT)\b", re.IGNORECASE),
    re.compile(r"^(?:TITLE|SOMETHING|ayaya\?)$", re.IGNORECASE),
    re.compile(r"\bNullReferenceException\b"),
    re.compile(r"^>?\s*Choice \d+$", re.IGNORECASE),
    re.compile(r"^My Ability$", re.IGNORECASE),
    re.compile(r"^asdasd(?:\s+asdasd)*$", re.IGNORECASE),
    re.compile(r'^YOu have been inflicted with "SOMETHING"', re.IGNORECASE),
    re.compile(r"^Gain stats if you have this trait\.", re.IGNORECASE),
    re.compile(r"Example line 1\.", re.IGNORECASE),
]


def history_label(path: Path) -> str:
    if path == LIVE_UNTRANSLATED_FILE:
        return "live:_TmpUntranslated.txt"
    if path == LIVE_RESIDUAL_FILE:
        return "live:_TmpResidualEnglish.txt"
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def iter_untranslated_files() -> list[Path]:
    candidates = [
        *HISTORY_FILES,
        *sorted(ROOT.glob("runtime_untranslated*.txt")),
        LIVE_UNTRANSLATED_FILE,
    ]
    files: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        resolved = str(path.resolve())
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        files.append(path)
    return files


def unescape(value: str) -> str:
    return (
        value.replace("\\=", "=")
        .replace("\\:", ":")
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
    )


def visible(value: str) -> str:
    value = TAG_RE.sub("", value.replace("\r\n", "\n").replace("\r", "\n"))
    return re.sub(r"\s+", " ", value).strip()


def visible_lookup_key(value: str) -> str:
    value = (
        value.replace("[[", "")
        .replace("]]", "")
        .replace("((", "")
        .replace("))", "")
        .replace("##", "")
        .replace("//", "")
        .replace("\u00a0", " ")
    )
    value = re.sub(r"\s+\(Meta Perk\)[^A-Za-z0-9]*$", "", value, flags=re.IGNORECASE)
    return visible(value).casefold()


def flatten_decorated_ascii_runs(value: str) -> str:
    return DECORATED_ASCII_RUN_RE.sub(lambda match: TAG_RE.sub("", match.group()), value)


def load_pairs(path: Path, regex_only: bool = False) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        if not raw_line.strip() or raw_line.startswith("//") or raw_line.startswith("sr:"):
            continue
        if regex_only and not raw_line.startswith("r:"):
            continue
        if not regex_only and raw_line.startswith("r:"):
            continue
        separator = find_separator(raw_line)
        if separator <= 0:
            continue
        source_start = 2 if regex_only else 0
        source = raw_line[source_start:separator]
        if regex_only and source.startswith('"') and source.endswith('"'):
            source = source[1:-1]
        pairs.append((unescape(source), unescape(raw_line[separator + 1 :])))
    return pairs


def convert_dotnet_regex(pattern: str) -> str:
    pattern = re.sub(r"\(\?<([A-Za-z_][A-Za-z0-9_]*)>", r"(?P<\1>", pattern)
    return pattern


def load_regexes() -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for pattern, _ in load_pairs(ROOT / "runtime_regex_zh.txt", regex_only=True):
        try:
            patterns.append(re.compile(convert_dotnet_regex(pattern)))
        except re.error:
            continue
    return patterns


def fragments_match(source: str, fragments: list[tuple[str, str]]) -> bool:
    for part in re.split(r"(<[^>]+>)", source):
        if not part or part.startswith("<"):
            continue
        if any(key in part for key, _ in fragments):
            return True
    return False


def is_item_panel(component: str, source: str) -> bool:
    if component not in {"Description Text", "Text"}:
        return False
    signals = (
        "Weapon Type:",
        "Weapon Range:",
        "Attack Damage:",
        "Equip Load",
        "Attunement:",
        "Damage Scaling:",
        "Body Armor",
        "装备负重",
        "调谐",
    )
    count = sum(signal in source for signal in signals)
    return count >= 2 or "Equip Load" in source or "装备负重" in source


def is_structured(component: str, source: str) -> bool:
    if is_item_panel(component, source):
        return True
    if component not in {"Description Text", "Text"}:
        return False
    return (
        "\n•" in source
        or "<color=#808080>Consumable</color>" in source
        or "<color=#808080>消耗品</color>" in source
        or "Maximum Stacks:" in source
        or "Reward choices" in source
        or source.startswith("Grants")
        or source.startswith("Drops Rewards")
        or "Lucky Hits" in source
        or "Cursed Hits" in source
        or source.startswith("<color=#00E61A>+")
    )


def general_route(component: str, source: str) -> bool:
    if (
        component
        in {
            "Character Title Text",
            "General Stats",
            "Tab Label (TMP)",
            "Label",
            "Value",
            "Trait Title",
            "Trait Description",
            "Title Text",
            "Input Alias",
            "Elite Enchantment Text",
            "Main Header",
            "Equipment Name",
            "Collection Item Title",
            "Collection Item Description",
            "Class Ability Title",
            "Class Stats Text",
            "Selected Gift Name",
            "Selected Gift Description",
            "Description Part 1",
            "Description Part 2",
            "Cinder Modifier Title",
            "Cinder Modifier Description",
            "Button Text",
            "Boss Name Text",
            "Objective Header",
            "Objective Text",
            "Info Text",
            "Skill Description",
        }
        or component.startswith("Choice ")
        or component.endswith(" (Text)")
    ):
        return True
    return (
        "After each run you gain mastery" in source
        or "Per level you can allocate one perk" in source
        or "The Bonfire beckons you" in source
        or (
            "Effect of" in source
            and "Ailments" in source
            and "Soul Heart" in source
        )
    )


def dialogue_match(source: str, dialogue_sources: list[str]) -> bool:
    current = visible(source).casefold()
    if len(current) < 3:
        return False
    translations = {
        dialogue_source
        for dialogue_source in dialogue_sources
        if dialogue_source.startswith(current) or current.startswith(dialogue_source)
    }
    return len(translations) == 1


def is_technical(component: str, source: str) -> bool:
    text = visible(source)
    if component in TECHNICAL_COMPONENTS:
        return True
    if component == "Text" and re.fullmatch(r"[A-Za-z]{1,3}", text):
        return True
    if component == "Text" and re.fullmatch(r"(?:asdasd)+[\w\s]*", text, re.IGNORECASE):
        return True
    return any(pattern.search(text) for pattern in TECHNICAL_TEXT_PATTERNS)


def classify(
    component: str,
    source: str,
    exact: set[str],
    visible_exact: set[str],
    regexes: list[re.Pattern[str]],
    fragments: list[tuple[str, str]],
    item_fragments: list[tuple[str, str]],
    dialogue_sources: list[str],
) -> str:
    if source in exact:
        return "exact"
    if component in VISIBLE_EXACT_COMPONENTS and visible_lookup_key(source) in visible_exact:
        return "visible_exact"
    color_wrapped = re.fullmatch(r"<color=[^>]+>([^<>]+)</color>", source)
    if color_wrapped and color_wrapped.group(1) in exact:
        return "exact"
    if any(pattern.fullmatch(source) for pattern in regexes):
        return "regex"
    flattened_source = flatten_decorated_ascii_runs(source)
    if flattened_source != source:
        return classify(
            component,
            flattened_source,
            exact,
            visible_exact,
            regexes,
            fragments,
            item_fragments,
            dialogue_sources,
        )
    if is_structured(component, source) and (
        fragments_match(source, item_fragments) or fragments_match(source, fragments)
    ):
        return "structured_fragments"
    if dialogue_match(source, dialogue_sources):
        return "dialogue"
    current_dialogue = visible(source).casefold()
    if component == "Text" and any(entry.startswith(current_dialogue) for entry in dialogue_sources):
        return "typing_prefix"
    if general_route(component, source) and fragments_match(source, fragments):
        return "general_fragments"
    if is_technical(component, source):
        return "technical_ignored"
    return "uncovered"


def main() -> None:
    runtime_pairs = [
        pair
        for file in ("runtime_overrides_zh.txt", "runtime_plugin_overrides_zh.txt")
        for pair in load_pairs(ROOT / file)
    ]
    exact = {source for source, _ in runtime_pairs}
    visible_exact = {visible_lookup_key(source) for source, translation in runtime_pairs if translation != source}
    regexes = load_regexes()
    fragments = load_pairs(ROOT / "runtime_fragments_zh.txt")
    item_fragments = load_pairs(ROOT / "runtime_item_fragments_zh.txt")
    dialogue_sources = [
        visible(source).casefold()
        for source, _ in load_pairs(ROOT / "runtime_dialogue_overrides_zh.txt")
    ]
    with (ROOT / "translations_zh.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            source = row.get("source_text") or ""
            translation = row.get("translation_zh") or ""
            key = row.get("key") or ""
            source_file = row.get("source_file") or ""
            if source and translation and translation != source:
                visible_exact.add(visible_lookup_key(source))
            if (
                (not key.startswith("AUTO_") or "global-metadata.dat" in source_file)
                and len(source) >= 6
                and re.search(r"[.!?]|\\n", source)
                and translation != source
            ):
                dialogue_sources.append(visible(unescape(source)).casefold())

    samples: dict[tuple[str, str], set[str]] = defaultdict(set)
    for file in iter_untranslated_files():
        for raw_line in file.read_text(encoding="utf-8-sig").splitlines():
            parts = raw_line.split("\t", 2)
            if len(parts) != 3:
                continue
            _, component, escaped_source = parts
            source = unescape(escaped_source)
            text = visible(source)
            if CHINESE_RE.search(text):
                continue
            if len(ENGLISH_WORD_RE.findall(text)) < 1:
                continue
            samples[(component, source)].add(history_label(file))

    rows: list[dict[str, str]] = []
    for (component, source), files in samples.items():
        status = classify(
            component,
            source,
            exact,
            visible_exact,
            regexes,
            fragments,
            item_fragments,
            dialogue_sources,
        )
        rows.append(
            {
                "status": status,
                "component": component,
                "source": source.replace("\n", "\\n"),
                "history_files": ";".join(sorted(files)),
            }
        )

    rows.sort(key=lambda row: (row["status"], row["component"], row["source"]))
    text_rows = [
        row
        for row in rows
        if row["status"] == "uncovered" and row["component"] == "Text"
    ]
    visible_texts = [visible(unescape(row["source"])).casefold() for row in text_rows]
    for row, current in zip(text_rows, visible_texts):
        if any(
            len(other) > len(current) and other.startswith(current)
            for other in visible_texts
        ):
            row["status"] = "typing_prefix"

    rows.sort(key=lambda row: (row["status"], row["component"], row["source"]))
    with REPORT_FILE.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["status", "component", "source", "history_files"],
        )
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter((row["status"], row["component"]) for row in rows)
    with SUMMARY_FILE.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["status", "component", "count"],
        )
        writer.writeheader()
        for (status, component), count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        ):
            writer.writerow(
                {"status": status, "component": component, "count": str(count)}
            )

    status_counts = Counter(row["status"] for row in rows)
    for status, count in status_counts.most_common():
        print(f"{status}: {count}")
    print(f"总样本: {len(rows)}")
    print(f"报告: {REPORT_FILE}")


if __name__ == "__main__":
    main()
