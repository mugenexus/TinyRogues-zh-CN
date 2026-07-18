from __future__ import annotations

import csv
import re
from pathlib import Path

from audit_runtime_coverage import (
    LIVE_RESIDUAL_FILE,
    ROOT,
    convert_dotnet_regex,
    flatten_decorated_ascii_runs,
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
    "NaN",
    "ig-gi-ig-gi-",
}
STYLED_WORD_RE = re.compile(r"(?:<color=[^>]+>[A-Za-z]</color>){2,}")


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


def translate_tag_delimited_connectors(source: str) -> str:
    source = re.sub(r"(?<=>)to(?=<)", "至", source)
    source = re.sub(r"(?<=>)to (?=<color)", "作用于 ", source)
    source = re.sub(r"(?<=>)\nto (?=<color)", "\n作用于 ", source)
    return re.sub(r"(?<=>)for (?=<color)", "持续 ", source)


def convert_replacement(value: str) -> str:
    value = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", r"\\g<\1>", value)
    return re.sub(r"\$([0-9]+)", r"\\g<\1>", value)


def load_exact() -> dict[str, str]:
    exact: dict[str, str] = {}
    for file_name in (
        "runtime_overrides_zh.txt",
        "runtime_plugin_overrides_zh.txt",
        "runtime_dialogue_overrides_zh.txt",
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
    if len(current) < 3:
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
    structured_fragments: list[tuple[str, str]],
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

    flattened_source = flatten_decorated_ascii_runs(source)
    if flattened_source != source:
        source = flattened_source
        if source in exact:
            return exact[source]
        color_wrapped = re.fullmatch(
            r"<color=(?P<color>[^>]+)>(?P<text>[^<>]+)</color>", source
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
        source = translate_tag_delimited_connectors(source.replace("\u00a0", " "))
        return apply_fragments(source, structured_fragments)

    if general_route(component, source):
        return apply_fragments(translate_tag_delimited_connectors(source), fragments)

    dialogue = translate_dialogue_prefix(source, exact)
    if dialogue is not None:
        return dialogue

    return source


def translate_until_stable(
    component: str,
    source: str,
    exact: dict[str, str],
    regex_pairs: list[tuple[re.Pattern[str], str]],
    fragments: list[tuple[str, str]],
    structured_fragments: list[tuple[str, str]],
) -> str:
    result = source
    for _ in range(4):
        translated = translate(
            component,
            result,
            exact,
            regex_pairs,
            fragments,
            structured_fragments,
        )
        if translated == result:
            break
        result = translated
    return result


def residual_words(value: str) -> list[str]:
    words: list[str] = []
    value = STYLED_WORD_RE.sub("", value)
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
    structured_fragments = sorted(
        [*fragments, *item_fragments], key=lambda pair: len(pair[0]), reverse=True
    )

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
        translated = translate_until_stable(
            component,
            source,
            exact,
            regex_pairs,
            fragments,
            structured_fragments,
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
            translated = translate_until_stable(
                component,
                source,
                exact,
                regex_pairs,
                fragments,
                structured_fragments,
            )
            if translated == source:
                translated = translate_until_stable(
                    component,
                    unescape(escaped_translated),
                    exact,
                    regex_pairs,
                    fragments,
                    structured_fragments,
                )
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
