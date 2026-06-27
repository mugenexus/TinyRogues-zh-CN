from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DICT_FILES = [
    ROOT / "runtime_overrides_zh.txt",
    ROOT / "runtime_plugin_overrides_zh.txt",
    ROOT / "runtime_regex_zh.txt",
    ROOT / "runtime_fragments_zh.txt",
    ROOT / "runtime_item_fragments_zh.txt",
    ROOT / "runtime_dialogue_overrides_zh.txt",
]
CSV_FILE = ROOT / "translations_zh.csv"
REPORT_FILE = ROOT / "translation_self_audit.csv"
SUMMARY_FILE = ROOT / "translation_self_audit_summary.json"

TAG_RE = re.compile(r"<[^>]+>")
CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
ENGLISH_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{1,}")
PLACEHOLDER_RE = re.compile(
    r"\{[^{}]+\}|%[A-Za-z]|\\[tr]|\[(?:E|F|Q|C|ESC|SHIFT|ENTER|SPACE|TAB)\]"
)
SAFE_ENGLISH = {
    "exp",
    "hp",
    "mp",
    "str",
    "dex",
    "int",
    "crt",
    "ui",
    "pc",
    "fps",
    "steam",
    "tiny",
    "rogues",
    "bepinex",
    "xunity",
    "tmp",
    "wasd",
    "crt",
    "rng",
}


def find_separator(line: str) -> int:
    if line.startswith('r:"'):
        separator = line.rfind('"=')
        return separator + 1 if separator >= 0 else -1

    inside_tag = False
    for index, char in enumerate(line):
        escaped = index > 0 and line[index - 1] == "\\"
        if char == "<" and not escaped:
            inside_tag = True
            continue
        if char == ">" and not escaped:
            inside_tag = False
            continue
        if char == "=" and not escaped and not inside_tag:
            return index
    return -1


def visible_text(value: str) -> str:
    value = TAG_RE.sub("", value)
    value = value.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")
    return re.sub(r"\s+", " ", value).strip()


def english_words(value: str) -> list[str]:
    return [
        word
        for word in ENGLISH_WORD_RE.findall(visible_text(value))
        if word.casefold() not in SAFE_ENGLISH
    ]


def control_signature(value: str) -> dict[str, Counter[str] | int]:
    return {
        "tags": Counter(TAG_RE.findall(value)),
        "placeholders": Counter(PLACEHOLDER_RE.findall(value)),
        "newlines": value.count("\\n"),
        "highlight_open": value.count("[["),
        "highlight_close": value.count("]]"),
    }


def add_issue(
    issues: list[dict[str, str]],
    severity: str,
    file: Path,
    line: int,
    category: str,
    key: str,
    detail: str,
) -> None:
    issues.append(
        {
            "severity": severity,
            "file": file.name,
            "line": str(line),
            "category": category,
            "key": key[:180],
            "detail": detail[:500],
        }
    )


def audit_dictionary(
    file: Path,
    issues: list[dict[str, str]],
    cross_entries: dict[str, list[tuple[str, int, str]]],
) -> None:
    local_entries: dict[str, list[tuple[int, str]]] = defaultdict(list)
    is_regex = file.name == "runtime_regex_zh.txt"

    for line_number, raw_line in enumerate(
        file.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        trimmed_line = raw_line.strip()
        if not trimmed_line or raw_line.startswith("//") or raw_line.startswith("sr:"):
            continue
        if is_regex and not raw_line.startswith("r:"):
            add_issue(
                issues,
                "error",
                file,
                line_number,
                "非正则行",
                raw_line,
                "正则词典中的有效行必须以 r: 开头。",
            )
            continue

        line = raw_line
        separator = find_separator(line)
        if separator <= 0:
            add_issue(
                issues,
                "error",
                file,
                line_number,
                "无法解析",
                line,
                "未找到富文本标签外的键值分隔符。",
            )
            continue

        source_start = 2 if is_regex else 0
        source = line[source_start:separator]
        if is_regex and source.startswith('"') and source.endswith('"'):
            source = source[1:-1]
        target = line[separator + 1 :]

        if not source or not target:
            add_issue(
                issues,
                "error",
                file,
                line_number,
                "空键或空译文",
                source,
                "源文本或译文为空。",
            )
            continue

        local_entries[source].append((line_number, target))
        if not is_regex:
            cross_entries[source].append((file.name, line_number, target))

        if source == target:
            add_issue(
                issues,
                "review",
                file,
                line_number,
                "原译文相同",
                source,
                "需要确认是专名、按键还是漏翻。",
            )

        words = english_words(target)
        if words and len(words) >= 2:
            add_issue(
                issues,
                "review",
                file,
                line_number,
                "译文英文残留",
                source,
                "残留英文：" + ", ".join(words[:12]),
            )

        if not is_regex:
            source_controls = control_signature(source)
            target_controls = control_signature(target)
            for control_name in (
                "tags",
                "placeholders",
                "newlines",
                "highlight_open",
                "highlight_close",
            ):
                if source_controls[control_name] != target_controls[control_name]:
                    add_issue(
                        issues,
                        "error",
                        file,
                        line_number,
                        "控制符不一致",
                        source,
                        f"{control_name}: {source_controls[control_name]} -> "
                        f"{target_controls[control_name]}",
                    )

    for source, entries in local_entries.items():
        if len(entries) < 2:
            continue
        values = {target for _, target in entries}
        category = "重复键冲突" if len(values) > 1 else "重复键"
        severity = "error" if len(values) > 1 else "warning"
        add_issue(
            issues,
            severity,
            file,
            entries[-1][0],
            category,
            source,
            "出现行：" + ", ".join(str(line) for line, _ in entries),
        )


def audit_csv(issues: list[dict[str, str]]) -> None:
    seen_keys: dict[str, int] = {}
    with CSV_FILE.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, start=2):
            key = (row.get("key") or "").strip()
            source = row.get("source_text") or ""
            target = row.get("translation_zh") or ""

            if key in seen_keys:
                add_issue(
                    issues,
                    "error",
                    CSV_FILE,
                    line_number,
                    "CSV 重复键",
                    key,
                    f"首次出现于第 {seen_keys[key]} 行。",
                )
            else:
                seen_keys[key] = line_number

            if not target.strip():
                add_issue(
                    issues,
                    "error",
                    CSV_FILE,
                    line_number,
                    "CSV 空译文",
                    key,
                    visible_text(source),
                )
                continue

            if source == target:
                add_issue(
                    issues,
                    "review",
                    CSV_FILE,
                    line_number,
                    "CSV 原译文相同",
                    key,
                    visible_text(source),
                )

            words = english_words(target)
            if len(words) >= 2:
                add_issue(
                    issues,
                    "review",
                    CSV_FILE,
                    line_number,
                    "CSV 英文残留",
                    key,
                    "残留英文：" + ", ".join(words[:12]),
                )

            source_controls = control_signature(source)
            target_controls = control_signature(target)
            for control_name in (
                "tags",
                "placeholders",
                "newlines",
                "highlight_open",
                "highlight_close",
            ):
                if source_controls[control_name] != target_controls[control_name]:
                    add_issue(
                        issues,
                        "error",
                        CSV_FILE,
                        line_number,
                        "CSV 控制符不一致",
                        key,
                        f"{control_name}: {source_controls[control_name]} -> "
                        f"{target_controls[control_name]}",
                    )


def main() -> None:
    issues: list[dict[str, str]] = []
    cross_entries: dict[str, list[tuple[str, int, str]]] = defaultdict(list)

    for file in DICT_FILES:
        audit_dictionary(file, issues, cross_entries)
    audit_csv(issues)

    for source, entries in cross_entries.items():
        if len(entries) < 2:
            continue
        if any("fragments" in file.casefold() for file, _, _ in entries):
            continue
        values = {target for _, _, target in entries}
        if len(values) <= 1:
            continue
        locations = ", ".join(f"{file}:{line}" for file, line, _ in entries)
        add_issue(
            issues,
            "warning",
            ROOT / entries[-1][0],
            entries[-1][1],
            "跨词典译文冲突",
            source,
            locations,
        )

    issues.sort(
        key=lambda row: (
            {"error": 0, "warning": 1, "review": 2}.get(row["severity"], 3),
            row["file"],
            int(row["line"]),
        )
    )
    with REPORT_FILE.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["severity", "file", "line", "category", "key", "detail"],
        )
        writer.writeheader()
        writer.writerows(issues)

    summary = {
        "total": len(issues),
        "by_severity": dict(Counter(row["severity"] for row in issues)),
        "by_category": dict(Counter(row["category"] for row in issues)),
        "report": str(REPORT_FILE),
    }
    SUMMARY_FILE.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
