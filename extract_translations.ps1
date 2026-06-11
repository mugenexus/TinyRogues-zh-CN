param(
    [string]$GameRoot = 'D:\SteamLibrary\steamapps\common\Tiny Rogues',
    [string]$OutputCsv = (Join-Path $PSScriptRoot 'translations_zh.csv')
)

$ErrorActionPreference = 'Stop'

$source = @'
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

public sealed class TranslationRow
{
    public string Key = "";
    public string SourceFile = "";
    public int LineNumber;
    public long ByteOffset;
    public string SourceText = "";
    public string TranslationZh = "";
    public string Notes = "";
}

public sealed class AsciiItem
{
    public long Offset;
    public string Text = "";
}

public static class TinyRoguesExtractor
{
    private static readonly Regex JsonPair = new Regex(
        "\"(?<key>(?:\\\\.|[^\"\\\\])+)\"\\s*:\\s*\"(?<value>(?:\\\\.|[^\"\\\\])*)\"",
        RegexOptions.Compiled);

    private static readonly Regex Word = new Regex("[A-Za-z]{2,}", RegexOptions.Compiled);
    private static readonly Regex SentenceSignal = new Regex(
        @"(?ix)
        \b(
          attack|damage|health|heart|armor|mana|stamina|critical|chance|speed|range|
          weapon|equipment|item|consumable|skill|trait|effect|status|enemy|boss|
          room|floor|gold|soul|curse|luck|poison|burn|bleed|freeze|block|evade|
          gain|grant|increase|decrease|deal|recover|restore|inflict|trigger|
          requires?|cannot|choose|press|hold|continue|options?|settings?|restart|
          start|save|slot|unlock|upgrade|reroll|shop|inventory|description|
          victory|defeat|world|journey|death|heaven|hell|abyss|seconds?|cooldown
        )\b",
        RegexOptions.Compiled);

    private static readonly Regex AssetLike = new Regex(
        @"^(?:Assets/|Packages/|Library/|Shader |Shader Graphs/|UI/|[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+){2,})",
        RegexOptions.Compiled);

    private static readonly Regex CodeLike = new Regex(
        @"(?:Assembly-CSharp|PublicKeyToken|Version=\d|System\.|UnityEngine|UnityEditor|Exception|stacktrace|https?://|\.dll\b|\.cs\b|\.h\b)",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex TypeLike = new Regex(
        @"^[A-Z][A-Za-z0-9]+(?:Controller|Manager|Provider|Behaviour|Behavior|Spawner|Handler|Tracker|System|Component|Renderer|Material|Prefab|Atlas|Sprite|Icon|Canvas|Panel|Layout|Display|Object|Event|Condition|Sequence|Reaction)$",
        RegexOptions.Compiled);

    public static List<TranslationRow> Extract(string gameRoot)
    {
        string data = Path.Combine(gameRoot, "Tiny Rogues_Data");
        string[] files = {
            Path.Combine(data, "resources.assets"),
            Path.Combine(data, "sharedassets0.assets"),
            Path.Combine(data, "sharedassets1.assets"),
            Path.Combine(data, "sharedassets2.assets"),
            Path.Combine(data, "level0"),
            Path.Combine(data, "level1"),
            Path.Combine(data, "level2"),
            Path.Combine(data, "il2cpp_data", "Metadata", "global-metadata.dat")
        };

        var rows = new List<TranslationRow>();
        foreach (string file in files)
        {
            if (!File.Exists(file)) continue;
            ExtractFile(file, gameRoot, rows);
        }

        return Deduplicate(rows);
    }

    private static void ExtractFile(string file, string gameRoot, List<TranslationRow> rows)
    {
        byte[] data = File.ReadAllBytes(file);
        bool isMetadata = Path.GetFileName(file).Equals("global-metadata.dat", StringComparison.OrdinalIgnoreCase);
        string prefix = gameRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        string relative = file.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
            ? file.Substring(prefix.Length)
            : file;
        List<AsciiItem> strings;
        if (isMetadata
            && data.Length >= 24
            && BitConverter.ToUInt32(data, 0) == 0xFAB11BAF)
        {
            strings = ReadMetadataLiterals(data);
        }
        else
        {
            strings = ReadAsciiStrings(data, 4, 0, data.Length);
        }
        var explicitOffsets = new HashSet<long>();
        int line = 0;

        if (Path.GetFileName(file).Equals("resources.assets", StringComparison.OrdinalIgnoreCase))
        {
            foreach (var item in strings)
            {
                if (!item.Text.Contains("\": \"")) continue;
                foreach (Match match in JsonPair.Matches(item.Text))
                {
                    string key = UnescapeJson(match.Groups["key"].Value);
                    string value = UnescapeJson(match.Groups["value"].Value);
                    if (!IsExplicitTranslatable(value)) continue;
                    line++;
                    long offset = item.Offset + Encoding.UTF8.GetByteCount(item.Text.Substring(0, match.Index));
                    explicitOffsets.Add(item.Offset);
                    rows.Add(new TranslationRow {
                        Key = key,
                        SourceFile = relative,
                        LineNumber = line,
                        ByteOffset = offset,
                        SourceText = EscapeNewlines(value),
                        Notes = "Explicit source key; preserve tags, placeholders, and newline escapes"
                    });
                }
            }
        }

        foreach (var item in strings)
        {
            if (explicitOffsets.Contains(item.Offset)) continue;
            string text = item.Text.Trim();
            if (!IsTranslatable(text, isMetadata)) continue;
            line++;
            rows.Add(new TranslationRow {
                Key = "AUTO_" + Path.GetFileName(file).Replace('.', '_').ToUpperInvariant()
                    + "_" + item.Offset.ToString("X", CultureInfo.InvariantCulture),
                SourceFile = relative,
                LineNumber = line,
                ByteOffset = item.Offset,
                SourceText = EscapeNewlines(text),
                Notes = "Generated stable key from file name and byte offset"
            });
        }
    }

    private static bool IsTranslatable(string text, bool strictMetadata)
    {
        if (String.IsNullOrWhiteSpace(text)) return false;
        if (text.Length < 3 || text.Length > 1200) return false;
        if (Regex.IsMatch(text, "^\\s*\"[^\"]+\"\\s*:")) return false;
        if (Regex.IsMatch(text, @"^(?:Shader|Shader Graphs|Legacy Shaders)/", RegexOptions.IgnoreCase)) return false;
        if (text.Contains("|") || text.Contains("::") || text.Contains("Modules/")) return false;
        if (text.Contains("_") && !text.Contains("<")) return false;
        if (Regex.IsMatch(text, @"(?:^|[\\/])(?:Assets|Packages|Library|Runtime|Editor|Public)(?:[\\/]|$)", RegexOptions.IgnoreCase)) return false;
        if (Regex.IsMatch(text, @"\b(?:Prefab|Material|Renderer|Controller|Manager|Spawner|Handler|Provider|Behaviour|Behavior|Definition|Sequence|Reaction|Condition|Node|Bindings)\b", RegexOptions.IgnoreCase)) return false;
        if (Regex.IsMatch(text, @"\((?:Effect(?:\s+\d+)?|Attack|Attack Definition|Description|Reward Effect|Trait Effect.*|Trigger|Status Effect|Meta Perk|Trait|Weight Manipulator)\)[A-Z]?\s*$", RegexOptions.IgnoreCase)) return false;
        if (Regex.IsMatch(text, @"^(?:Load|Spawn|Texture|Particles?|Tutorial Room \d|Boss Room Gate)\b", RegexOptions.IgnoreCase)) return false;
        if (Regex.IsMatch(text, @"^[^A-Za-z0-9<\[\(\{""']")) return false;
        if (!text.Contains(" ") && text.Length > 40) return false;
        if (CodeLike.IsMatch(text) || TypeLike.IsMatch(text)) return false;
        if (AssetLike.IsMatch(text) && !text.Contains(" ")) return false;

        int letters = text.Count(Char.IsLetter);
        int controls = text.Count(c => c < 32 && c != '\n' && c != '\r' && c != '\t');
        if (letters < 2 || controls > 0) return false;

        int words = Word.Matches(text).Count;
        bool phrase = text.Contains(" ") || text.Contains("\\n") || text.Contains("\n");
        bool punctuation = text.IndexOfAny(new[] { '.', '!', '?', ':', ';', ',' }) >= 0;
        bool markup = text.Contains("<sprite") || text.Contains("[[") || text.Contains("##")
            || text.Contains("(+") || text.Contains("(-");
        bool signal = SentenceSignal.IsMatch(text);

        if (strictMetadata)
        {
            if (!signal && !markup) return false;
            if (Regex.IsMatch(text,
                @"\b(?:out of range|cannot be null|null or empty|PlayerPrefs|Timeline|Reflection\.Emit|ParentRelation|channel sink|SimpleContent|Request header|FormatterEmitter|rootBone|bitNum|capacity)\b",
                RegexOptions.IgnoreCase)) return false;
            if (Regex.IsMatch(text, @"^(?:Loaded option|Set up|Addtrack|failed to find|cannot hold an instance)", RegexOptions.IgnoreCase)) return false;
            if (Regex.IsMatch(text, @"^Cannot\b", RegexOptions.IgnoreCase)
                && !Regex.IsMatch(text,
                    @"\b(?:use|used|equip|upgrade|attack|skill|item|weapon|room|combat|door|trait|reroll|cancel|swap|revive|afford|purchase|open|enter)\b",
                    RegexOptions.IgnoreCase)) return false;
            if (Regex.IsMatch(text,
                @"^(?:error|failed|cannot (?:convert|import|remove|specify)|unexpected|parameter|argument|allocator|buffer|constraint|the (?:method|object|event|base type)|missing method|DTD|JSON|XML|Struct '\{|Index \{|Interaction count)",
                RegexOptions.IgnoreCase)) return false;
            if (Regex.IsMatch(text,
                @"\b(?:deserialize|delegate table|generic parameter|primary key|namespace|simpleType|RenderTexture|graphicsFormat|fixup|byte\.MaxValue)\b",
                RegexOptions.IgnoreCase)) return false;
            if (text.Contains("/") && !text.Contains("<")) return false;
        }

        if (text.Length <= 32 && words <= 4)
        {
            return signal && !Regex.IsMatch(text, @"^(?:Load|Spawn|Player|Enemy|Trait|Skill|Item|Weapon|Equipment)\s+[A-Z]");
        }

        return words >= 2 && (signal || punctuation || markup || (phrase && words >= 5));
    }

    private static bool IsExplicitTranslatable(string text)
    {
        if (String.IsNullOrWhiteSpace(text) || text.Length > 2000) return false;
        if (!Regex.IsMatch(text, "[A-Za-z]")) return false;
        if (CodeLike.IsMatch(text)) return false;
        return true;
    }

    private static List<TranslationRow> Deduplicate(List<TranslationRow> rows)
    {
        var explicitKeys = new HashSet<string>(
            rows.Where(r => !r.Key.StartsWith("AUTO_", StringComparison.Ordinal))
                .Select(r => r.Key), StringComparer.Ordinal);
        var seenAuto = new HashSet<string>(StringComparer.Ordinal);
        var result = new List<TranslationRow>();

        foreach (var row in rows)
        {
            if (!row.Key.StartsWith("AUTO_", StringComparison.Ordinal))
            {
                result.Add(row);
                continue;
            }
            string normalized = row.SourceText.Trim();
            if (explicitKeys.Contains(normalized)) continue;
            string signature = row.SourceFile + "\0" + normalized;
            if (seenAuto.Add(signature)) result.Add(row);
        }
        return result;
    }

    private static List<AsciiItem> ReadAsciiStrings(byte[] data, int minimum, int offset, int length)
    {
        var result = new List<AsciiItem>();
        int start = -1;
        int begin = Math.Max(0, offset);
        int end = Math.Min(data.Length, begin + Math.Max(0, length));
        for (int i = begin; i <= end; i++)
        {
            bool printable = i < end && data[i] >= 32 && data[i] <= 126;
            if (printable)
            {
                if (start < 0) start = i;
                continue;
            }
            if (start >= 0 && i - start >= minimum)
            {
                result.Add(new AsciiItem {
                    Offset = start,
                    Text = Encoding.UTF8.GetString(data, start, i - start)
                });
            }
            start = -1;
        }
        return result;
    }

    private static List<AsciiItem> ReadMetadataLiterals(byte[] data)
    {
        var result = new List<AsciiItem>();
        int tableOffset = BitConverter.ToInt32(data, 8);
        int tableSize = BitConverter.ToInt32(data, 12);
        int dataOffset = BitConverter.ToInt32(data, 16);
        int dataSize = BitConverter.ToInt32(data, 20);
        int tableEnd = Math.Min(data.Length, tableOffset + tableSize);
        int dataEnd = Math.Min(data.Length, dataOffset + dataSize);

        for (int i = tableOffset; i + 8 <= tableEnd; i += 8)
        {
            int length = BitConverter.ToInt32(data, i);
            int index = BitConverter.ToInt32(data, i + 4);
            long absolute = (long)dataOffset + index;
            if (length < 3 || length > 2000 || absolute < dataOffset || absolute + length > dataEnd)
                continue;

            string text;
            try
            {
                text = Encoding.UTF8.GetString(data, (int)absolute, length);
            }
            catch
            {
                continue;
            }
            result.Add(new AsciiItem { Offset = absolute, Text = text });
        }
        return result;
    }

    private static string UnescapeJson(string value)
    {
        var sb = new StringBuilder(value.Length);
        for (int i = 0; i < value.Length; i++)
        {
            if (value[i] != '\\' || i + 1 >= value.Length)
            {
                sb.Append(value[i]);
                continue;
            }
            char next = value[++i];
            switch (next)
            {
                case 'n': sb.Append('\n'); break;
                case 'r': sb.Append('\r'); break;
                case 't': sb.Append('\t'); break;
                case '"': sb.Append('"'); break;
                case '\\': sb.Append('\\'); break;
                default: sb.Append('\\').Append(next); break;
            }
        }
        return sb.ToString();
    }

    private static string EscapeNewlines(string value)
    {
        return value.Replace("\r\n", "\\n").Replace("\r", "\\n").Replace("\n", "\\n");
    }
}
'@

Add-Type -TypeDefinition $source -Language CSharp

if (-not (Test-Path -LiteralPath $GameRoot)) {
    throw "游戏目录不存在：$GameRoot"
}

$rows = [TinyRoguesExtractor]::Extract($GameRoot)
$rows |
    Select-Object @{
        Name = 'key'; Expression = { $_.Key }
    }, @{
        Name = 'source_file'; Expression = { $_.SourceFile }
    }, @{
        Name = 'line_number'; Expression = { $_.LineNumber }
    }, @{
        Name = 'byte_offset'; Expression = { '0x{0:X}' -f $_.ByteOffset }
    }, @{
        Name = 'source_text'; Expression = { $_.SourceText }
    }, @{
        Name = 'translation_zh'; Expression = { $_.TranslationZh }
    }, @{
        Name = 'notes'; Expression = { $_.Notes }
    } |
    Export-Csv -LiteralPath $OutputCsv -NoTypeInformation -Encoding utf8

Write-Output "输出：$OutputCsv"
Write-Output "条目数：$($rows.Count)"
