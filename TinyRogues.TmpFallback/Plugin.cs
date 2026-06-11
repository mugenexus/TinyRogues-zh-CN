using System.Text;
using System.Text.RegularExpressions;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using TMPro;
using UnityEngine;

namespace TinyRogues.TmpFallback;

[BepInPlugin(PluginGuid, PluginName, PluginVersion)]
public sealed class Plugin : BasePlugin
{
    public const string PluginGuid = "mugen.tinyrogues.tmpfallback";
    public const string PluginName = "Tiny Rogues TMP Translation Fallback";
    public const string PluginVersion = "1.3.1";

    internal static ManualLogSource PluginLog { get; private set; } = null!;

    public override void Load()
    {
        PluginLog = Log;
        AddComponent<TmpTranslationFallback>();
        Log.LogInfo("TMP translation fallback loaded.");
    }
}

public sealed class TmpTranslationFallback : MonoBehaviour
{
    private const int MinimumDialoguePrefixLength = 4;
    private const int MaximumDialoguePrefixLength = 12;
    private readonly Dictionary<string, string> _translations = new(StringComparer.Ordinal);
    private readonly List<KeyValuePair<string, string>> _fragments = [];
    private readonly List<KeyValuePair<Regex, string>> _regexTranslations = [];
    private readonly Dictionary<string, List<DialogueEntry>> _dialogueEntries = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _dumpedUntranslated = new(StringComparer.Ordinal);
    private string _untranslatedDumpPath = string.Empty;
    private float _nextScanTime;
    private int _lastLoggedReplacementCount = -1;
    private int _dialogueEntryCount;

    public TmpTranslationFallback(IntPtr pointer) : base(pointer)
    {
    }

    private void Awake()
    {
        LoadDictionary("TinyRogues_zh.txt", loadRegex: false);
        LoadDictionary("RuntimeOverrides_zh.txt", loadRegex: false);
        LoadPluginDictionary("RuntimePluginOverrides_zh.txt");
        LoadRegexFile();
        LoadPluginFragments("RuntimeFragments_zh.txt");
        LoadDialogueDictionary("RuntimeDialogue_zh.txt");

        var textDirectory = Path.Combine(Paths.BepInExRootPath, "Translation", "zh", "Text");
        _untranslatedDumpPath = Path.Combine(textDirectory, "_TmpUntranslated.txt");
        Directory.CreateDirectory(textDirectory);

        Plugin.PluginLog.LogInfo(
            $"Loaded {_translations.Count} exact, {_regexTranslations.Count} regex, {_fragments.Count} fragment and " +
            $"{_dialogueEntryCount} dialogue TMP translations.");
    }

    private void Update()
    {
        if (Time.unscaledTime < _nextScanTime)
        {
            return;
        }

        _nextScanTime = Time.unscaledTime + 0.1f;
        var replacements = 0;

        foreach (var textComponent in Resources.FindObjectsOfTypeAll<TMP_Text>())
        {
            if (textComponent == null || textComponent.gameObject == null ||
                !textComponent.gameObject.activeInHierarchy)
            {
                continue;
            }

            var source = textComponent.text;
            if (string.IsNullOrWhiteSpace(source))
            {
                continue;
            }

            var normalizedSource = NormalizeNewlines(source);
            var translated = Translate(normalizedSource);
            if (translated != null && !string.Equals(normalizedSource, translated, StringComparison.Ordinal))
            {
                textComponent.text = translated;
                replacements++;
                continue;
            }

            DumpUntranslated(textComponent, normalizedSource);
        }

        if (replacements > 0 && replacements != _lastLoggedReplacementCount)
        {
            Plugin.PluginLog.LogInfo($"Applied {replacements} TMP fallback translations.");
            _lastLoggedReplacementCount = replacements;
        }
    }

    private string? Translate(string source)
    {
        if (_translations.TryGetValue(source, out var exact))
        {
            return exact;
        }

        var colorWrapped = Regex.Match(
            source,
            "^<color=(?<color>[^>]+)>(?<text>[^<>]+)</color>$",
            RegexOptions.CultureInvariant);
        if (colorWrapped.Success &&
            _translations.TryGetValue(colorWrapped.Groups["text"].Value, out var wrappedTranslation))
        {
            return $"<color={colorWrapped.Groups["color"].Value}>{wrappedTranslation}</color>";
        }

        foreach (var pair in _regexTranslations)
        {
            if (pair.Key.IsMatch(source))
            {
                return pair.Key.Replace(source, pair.Value);
            }
        }

        var dialogue = TranslateDialogue(source);
        if (dialogue != null)
        {
            return dialogue;
        }

        var result = source;
        foreach (var pair in _fragments)
        {
            if (result.Contains(pair.Key, StringComparison.Ordinal))
            {
                result = result.Replace(pair.Key, pair.Value, StringComparison.Ordinal);
            }
        }

        return string.Equals(result, source, StringComparison.Ordinal) ? null : result;
    }

    private void DumpUntranslated(TMP_Text textComponent, string source)
    {
        if (string.Equals(textComponent.gameObject.name, "Game Time And Progress Text", StringComparison.Ordinal))
        {
            return;
        }

        var visibleText = Regex.Replace(source, "<[^>]+>", string.Empty);
        var englishWords = Regex.Matches(visibleText, "[A-Za-z]{2,}");
        if (_untranslatedDumpPath.Length == 0 || englishWords.Count == 0 ||
            source.StartsWith("<sprite", StringComparison.OrdinalIgnoreCase) ||
            (Regex.IsMatch(visibleText, "[\u4e00-\u9fff]") &&
             englishWords.Cast<Match>().All(match => match.Value.Length <= 4)) ||
            !_dumpedUntranslated.Add(source))
        {
            return;
        }

        var escaped = Escape(source);
        var objectName = textComponent.gameObject.name.Replace('\t', ' ');
        File.AppendAllText(
            _untranslatedDumpPath,
            $"{DateTime.Now:yyyy-MM-dd HH:mm:ss}\t{objectName}\t{escaped}{Environment.NewLine}",
            Encoding.UTF8);
    }

    private void LoadDictionary(string fileName, bool loadRegex)
    {
        var path = Path.Combine(Paths.BepInExRootPath, "Translation", "zh", "Text", fileName);
        LoadDictionaryPath(path, loadRegex);
    }

    private void LoadPluginDictionary(string fileName)
    {
        var path = Path.Combine(Paths.PluginPath, "TinyRogues.TmpFallback", fileName);
        LoadDictionaryPath(path, loadRegex: false);
    }

    private void LoadDictionaryPath(string path, bool loadRegex)
    {
        if (!File.Exists(path))
        {
            Plugin.PluginLog.LogWarning($"Translation file not found: {path}");
            return;
        }

        foreach (var rawLine in File.ReadLines(path, Encoding.UTF8))
        {
            if (string.IsNullOrWhiteSpace(rawLine) || rawLine.StartsWith("//", StringComparison.Ordinal) ||
                rawLine.StartsWith("sr:", StringComparison.Ordinal))
            {
                continue;
            }

            if (rawLine.StartsWith("r:", StringComparison.Ordinal))
            {
                if (loadRegex)
                {
                    LoadRegex(rawLine);
                }

                continue;
            }

            var separator = FindSeparator(rawLine);
            if (separator <= 0)
            {
                continue;
            }

            var source = Unescape(rawLine[..separator]);
            var translated = Unescape(rawLine[(separator + 1)..]);
            if (source.Length > 0 && translated.Length > 0)
            {
                _translations[NormalizeNewlines(source)] = translated;
            }
        }
    }

    private void LoadRegex(string rawLine)
    {
        var separator = FindSeparator(rawLine);
        if (separator <= 3)
        {
            return;
        }

        var pattern = rawLine[2..separator].Trim();
        if (pattern.Length >= 2 && pattern[0] == '"' && pattern[^1] == '"')
        {
            pattern = pattern[1..^1];
        }

        try
        {
            _regexTranslations.Add(new KeyValuePair<Regex, string>(
                new Regex(pattern, RegexOptions.CultureInvariant),
                Unescape(rawLine[(separator + 1)..])));
        }
        catch (ArgumentException exception)
        {
            Plugin.PluginLog.LogWarning($"Invalid runtime translation regex: {exception.Message}");
        }
    }

    private void LoadRegexFile()
    {
        var path = Path.Combine(
            Paths.PluginPath,
            "TinyRogues.TmpFallback",
            "RuntimeRegex_zh.txt");
        if (!File.Exists(path))
        {
            Plugin.PluginLog.LogWarning($"Translation regex file not found: {path}");
            return;
        }

        foreach (var rawLine in File.ReadLines(path, Encoding.UTF8))
        {
            if (!string.IsNullOrWhiteSpace(rawLine) &&
                !rawLine.StartsWith("//", StringComparison.Ordinal) &&
                rawLine.StartsWith("r:", StringComparison.Ordinal))
            {
                LoadRegex(rawLine);
            }
        }
    }

    private void LoadDialogueDictionary(string fileName)
    {
        var path = Path.Combine(Paths.PluginPath, "TinyRogues.TmpFallback", fileName);
        if (!File.Exists(path))
        {
            Plugin.PluginLog.LogWarning($"Dialogue translation file not found: {path}");
            return;
        }

        foreach (var rawLine in File.ReadLines(path, Encoding.UTF8))
        {
            if (string.IsNullOrWhiteSpace(rawLine) || rawLine.StartsWith("//", StringComparison.Ordinal))
            {
                continue;
            }

            var separator = FindSeparator(rawLine);
            if (separator <= 0)
            {
                continue;
            }

            var source = Unescape(rawLine[..separator]);
            var translated = Unescape(rawLine[(separator + 1)..]);
            var visibleSource = GetVisibleText(source);
            if (visibleSource.Length < MinimumDialoguePrefixLength || translated.Length == 0)
            {
                continue;
            }

            var entry = new DialogueEntry(visibleSource, translated);
            _dialogueEntryCount++;
            var maximumPrefixLength = Math.Min(MaximumDialoguePrefixLength, visibleSource.Length);
            for (var prefixLength = MinimumDialoguePrefixLength;
                 prefixLength <= maximumPrefixLength;
                 prefixLength++)
            {
                var prefix = visibleSource[..prefixLength];
                if (!_dialogueEntries.TryGetValue(prefix, out var entries))
                {
                    entries = [];
                    _dialogueEntries[prefix] = entries;
                }

                entries.Add(entry);
            }
        }
    }

    private string? TranslateDialogue(string source)
    {
        var visibleSource = GetVisibleText(source);
        if (visibleSource.Length < MinimumDialoguePrefixLength)
        {
            return null;
        }

        var prefix = GetDialoguePrefix(visibleSource);
        if (!_dialogueEntries.TryGetValue(prefix, out var entries))
        {
            return null;
        }

        DialogueEntry? match = null;
        foreach (var entry in entries)
        {
            if (!entry.Source.StartsWith(visibleSource, StringComparison.OrdinalIgnoreCase) &&
                !visibleSource.StartsWith(entry.Source, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (match != null && !string.Equals(match.Translation, entry.Translation, StringComparison.Ordinal))
            {
                return null;
            }

            match = entry;
        }

        return match?.Translation;
    }

    private void LoadPluginFragments(string fileName)
    {
        var path = Path.Combine(Paths.PluginPath, "TinyRogues.TmpFallback", fileName);
        if (!File.Exists(path))
        {
            Plugin.PluginLog.LogWarning($"Translation fragment file not found: {path}");
            return;
        }

        foreach (var rawLine in File.ReadLines(path, Encoding.UTF8))
        {
            if (string.IsNullOrWhiteSpace(rawLine) || rawLine.StartsWith("//", StringComparison.Ordinal))
            {
                continue;
            }

            var separator = FindSeparator(rawLine);
            if (separator <= 0)
            {
                continue;
            }

            var source = NormalizeNewlines(Unescape(rawLine[..separator]));
            var translated = Unescape(rawLine[(separator + 1)..]);
            if (source.Length >= 3 && translated.Length > 0)
            {
                _fragments.Add(new KeyValuePair<string, string>(source, translated));
            }
        }

        _fragments.Sort((left, right) => right.Key.Length.CompareTo(left.Key.Length));
    }

    private static int FindSeparator(string line)
    {
        if (line.StartsWith("r:\"", StringComparison.Ordinal))
        {
            var regexSeparator = line.LastIndexOf("\"=", StringComparison.Ordinal);
            return regexSeparator >= 0 ? regexSeparator + 1 : -1;
        }

        var insideTag = false;
        for (var index = 0; index < line.Length; index++)
        {
            if (line[index] == '<' && (index == 0 || line[index - 1] != '\\'))
            {
                insideTag = true;
                continue;
            }

            if (line[index] == '>' && (index == 0 || line[index - 1] != '\\'))
            {
                insideTag = false;
                continue;
            }

            if (!insideTag && line[index] == '=' && (index == 0 || line[index - 1] != '\\'))
            {
                return index;
            }
        }

        return -1;
    }

    private static string Unescape(string value)
    {
        return value
            .Replace("\\=", "=")
            .Replace("\\:", ":")
            .Replace("\\n", "\n")
            .Replace("\\r", "\r")
            .Replace("\\t", "\t");
    }

    private static string Escape(string value)
    {
        return value
            .Replace("\\", "\\\\")
            .Replace("\r", "\\r")
            .Replace("\n", "\\n")
            .Replace("\t", "\\t");
    }

    private static string NormalizeNewlines(string value)
    {
        return value.Replace("\r\n", "\n").Replace('\r', '\n');
    }

    private static string GetVisibleText(string value)
    {
        var withoutTags = Regex.Replace(NormalizeNewlines(value), "<[^>]+>", string.Empty);
        return Regex.Replace(withoutTags, "\\s+", " ").Trim();
    }

    private static string GetDialoguePrefix(string visibleSource)
    {
        return visibleSource[..Math.Min(MaximumDialoguePrefixLength, visibleSource.Length)];
    }

    private sealed class DialogueEntry
    {
        public DialogueEntry(string source, string translation)
        {
            Source = source;
            Translation = translation;
        }

        public string Source { get; }
        public string Translation { get; }
    }
}
