from __future__ import annotations

import csv
import re
from pathlib import Path

from audit_runtime_coverage import (
    LIVE_RESIDUAL_FILE,
    ROOT,
    convert_dotnet_regex,
    general_route,
    history_label,
    is_structured,
    is_technical,
    iter_untranslated_files,
    load_pairs,
    unescape,
    visible,
)


REPORT_FILE = ROOT / "runtime_residual_english_audit.csv"
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
ALLOWED_WORDS = {
    "EXP",
    "STR",
    "DEX",
    "INT",
    "RNG",
    "DPS",
    "HP",
    "MP",
    "FPS",
    "TMP",
    "UI",
    "CRT",
    "BepInEx",
    "XUnity",
    "Steam",
    "Discord",
}


def apply_fragments(source: str, fragments: list[tuple[str, str]]) -> str:
    parts = re.split(r"(<[^>]+>)", source)
    for index, part in enumerate(parts):
        if not part or part.startswith("<"):
            continue
        for key, translation in fragments:
            if key in part:
                part = part.replace(key, translation)
        parts[index] = part
    return "".join(parts)


def convert_replacement(value: str) -> str:
    value = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", r"\\g<\1>", value)
    return re.sub(r"\$([0-9]+)", r"\\g<\1>", value)


def load_exact() -> dict[str, str]:
    exact: dict[str, str] = {}
    for file_name in (
        "runtime_overrides_zh.txt",
        "runtime_plugin_overrides_zh.txt",
    ):
        exact.update(load_pairs(ROOT / file_name))

    with (ROOT / "translations_zh.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            source = unescape(row.get("source_text") or "")
            translation = unescape(row.get("translation_zh") or "")
            if source and translation and source != translation:
                exact.setdefault(source, translation)
    return exact


def translate_dialogue_prefix(source: str, exact: dict[str, str]) -> str | None:
    current = visible(source).casefold()
    if len(current) < 4:
        return None

    matches = {
        translation
        for full_source, translation in exact.items()
        if len(visible(full_source)) > len(current)
        and visible(full_source).casefold().startswith(current)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def load_regex_pairs() -> list[tuple[re.Pattern[str], str]]:
    pairs: list[tuple[re.Pattern[str], str]] = []
    for pattern, replacement in load_pairs(
        ROOT / "runtime_regex_zh.txt", regex_only=True
    ):
        try:
            pairs.append(
                (
                    re.compile(convert_dotnet_regex(pattern)),
                    convert_replacement(replacement),
                )
            )
        except re.error:
            continue
    return pairs


def translate(
    component: str,
    source: str,
    exact: dict[str, str],
    regex_pairs: list[tuple[re.Pattern[str], str]],
    fragments: list[tuple[str, str]],
    item_fragments: list[tuple[str, str]],
) -> str:
    if source in exact:
        return exact[source]

    color_wrapped = re.fullmatch(
        r"<color=(?P<color>[^>]+)>(?P<text>[^<>]+)</color>",
        source,
    )
    if color_wrapped and color_wrapped.group("text") in exact:
        return (
            f'<color={color_wrapped.group("color")}>'
            f'{exact[color_wrapped.group("text")]}</color>'
        )

    for pattern, replacement in regex_pairs:
        if pattern.fullmatch(source):
            return pattern.sub(replacement, source)

    if is_structured(component, source):
        result = apply_fragments(source, item_fragments).replace("\u00a0", " ")
        return apply_fragments(result, fragments)

    if general_route(component, source):
        return apply_fragments(source, fragments)

    dialogue = translate_dialogue_prefix(source, exact)
    if dialogue is not None:
        return dialogue

    return source


def residual_words(value: str) -> list[str]:
    words: list[str] = []
    for match in WORD_RE.finditer(visible(value)):
        word = match.group(0)
        if len(word) <= 1 or word in ALLOWED_WORDS:
            continue
        words.append(word)
    return sorted(set(words), key=str.casefold)


def main() -> None:
    exact = load_exact()
    regex_pairs = load_regex_pairs()
    fragments = load_pairs(ROOT / "runtime_fragments_zh.txt")
    fragments.sort(key=lambda pair: len(pair[0]), reverse=True)
    item_fragments = load_pairs(ROOT / "runtime_item_fragments_zh.txt")
    item_fragments.sort(key=lambda pair: len(pair[0]), reverse=True)

    samples: dict[tuple[str, str], set[str]] = {}
    for path in iter_untranslated_files():
        for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
            parts = raw_line.split("\t", 2)
            if len(parts) != 3:
                continue
            _, component, escaped_source = parts
            source = unescape(escaped_source)
            samples.setdefault((component, source), set()).add(history_label(path))

    rows: list[dict[str, str]] = []
    for (component, source), files in samples.items():
        if is_technical(component, source):
            continue
        translated = translate(
            component,
            source,
            exact,
            regex_pairs,
            fragments,
            item_fragments,
        )
        # 历史日志中的纯英文对话数量很大，且由独立对话路由处理。
        # 本报告聚焦当前运行样本，以及翻译后仍夹杂英文的混合文本。
        if not any(file.startswith("live:") for file in files) and not CHINESE_RE.search(translated):
            continue
        words = residual_words(translated)
        if not words:
            continue
        rows.append(
            {
                "component": component,
                "residual_words": ";".join(words),
                "source": source.replace("\n", "\\n"),
                "translated": translated.replace("\n", "\\n"),
                "history_files": ";".join(sorted(files)),
            }
        )

    if LIVE_RESIDUAL_FILE.exists():
        for raw_line in LIVE_RESIDUAL_FILE.read_text(encoding="utf-8-sig").splitlines():
            parts = raw_line.split("\t", 3)
            if len(parts) != 4:
                continue
            _, component, escaped_source, escaped_translated = parts
            source = unescape(escaped_source)
            if is_technical(component, source):
                continue
            translated = translate(
                component,
                source,
                exact,
                regex_pairs,
                fragments,
                item_fragments,
            )
            if translated == source:
                translated = unescape(escaped_translated)
            words = residual_words(translated)
            if not words:
                continue
            rows.append(
                {
                    "component": component,
                    "residual_words": ";".join(words),
                    "source": source.replace("\n", "\\n"),
                    "translated": translated.replace("\n", "\\n"),
                    "history_files": history_label(LIVE_RESIDUAL_FILE),
                }
            )

    rows.sort(key=lambda row: (row["component"], row["residual_words"], row["source"]))
    with REPORT_FILE.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "component",
                "residual_words",
                "source",
                "translated",
                "history_files",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"残留样本: {len(rows)}")
    print(f"报告: {REPORT_FILE}")


if __name__ == "__main__":
    main()
