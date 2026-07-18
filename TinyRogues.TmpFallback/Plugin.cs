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
    public const string PluginVersion = "1.5.18";

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
    private const int MinimumDialoguePrefixLength = 3;
    private const int MaximumDialoguePrefixLength = 12;
    private readonly Dictionary<string, string> _translations = new(StringComparer.Ordinal);
    private readonly List<KeyValuePair<string, string>> _fragments = [];
    private readonly List<KeyValuePair<string, string>> _itemFragments = [];
    private readonly List<KeyValuePair<string, string>> _structuredFragments = [];
    private readonly List<KeyValuePair<Regex, string>> _regexTranslations = [];
    private readonly Dictionary<string, List<DialogueEntry>> _dialogueEntries = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _dumpedUntranslated = new(StringComparer.Ordinal);
    private readonly HashSet<string> _dumpedResidualTranslations = new(StringComparer.Ordinal);
    private readonly HashSet<int> _expandedGroundItemPanels = [];
    private string _untranslatedDumpPath = string.Empty;
    private string _residualDumpPath = string.Empty;
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
        LoadPluginFragments("RuntimeFragments_zh.txt", _fragments);
        LoadPluginFragments("RuntimeItemFragments_zh.txt", _itemFragments);
        _structuredFragments.AddRange(_fragments);
        _structuredFragments.AddRange(_itemFragments);
        _structuredFragments.Sort((left, right) => right.Key.Length.CompareTo(left.Key.Length));
        LoadDialogueDictionary("RuntimeDialogue_zh.txt");

        var textDirectory = Path.Combine(Paths.BepInExRootPath, "Translation", "zh", "Text");
        _untranslatedDumpPath = Path.Combine(textDirectory, "_TmpUntranslated.txt");
        _residualDumpPath = Path.Combine(textDirectory, "_TmpResidualEnglish.txt");
        Directory.CreateDirectory(textDirectory);

        Plugin.PluginLog.LogInfo(
            $"Loaded {_translations.Count} exact, {_regexTranslations.Count} regex, {_fragments.Count} general fragment, " +
            $"{_itemFragments.Count} item fragment and " +
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
            var translated = Translate(textComponent, normalizedSource);
            if (translated != null && !string.Equals(normalizedSource, translated, StringComparison.Ordinal))
            {
                var isGroundItemDetail = IsGroundItemDetail(textComponent, normalizedSource);
                var finalText = ApplyLayout(textComponent.gameObject.name, normalizedSource, translated);
                if (isGroundItemDetail)
                {
                    var sizedGroundItem = Regex.Match(
                        finalText,
                        "^<size=[^>]+>(?<body>.*)</size>$",
                        RegexOptions.CultureInvariant | RegexOptions.Singleline);
                    var groundItemBody = sizedGroundItem.Success
                        ? sizedGroundItem.Groups["body"].Value
                        : finalText;
                    finalText = $"<size=82%>{groundItemBody}</size>";
                }
                textComponent.text = finalText;
                if (isGroundItemDetail)
                {
                    ExpandGroundItemPanel(textComponent);
                }
                DumpResidualTranslation(textComponent, normalizedSource, finalText);
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

    private string? Translate(TMP_Text textComponent, string source)
    {
        var objectName = textComponent.gameObject.name;
        var directTranslation = TranslateDirect(source);
        if (directTranslation != null)
        {
            return directTranslation;
        }

        // Some rainbow labels wrap every ASCII letter in its own color tag.
        // Flatten only long decorated runs so normal colored stat grades stay intact.
        var flattenedSource = FlattenDecoratedAsciiRuns(source);
        if (!string.Equals(flattenedSource, source, StringComparison.Ordinal))
        {
            source = flattenedSource;
            directTranslation = TranslateDirect(source);
            if (directTranslation != null)
            {
                return directTranslation;
            }
        }

        if (IsStructuredRichText(objectName, source))
        {
            var itemResult = ApplyFragments(
                TranslateTagDelimitedConnectors(source.Replace('\u00A0', ' ')),
                _structuredFragments);
            if (!string.Equals(itemResult, source, StringComparison.Ordinal))
            {
                return itemResult;
            }
        }

        var dialogue = TranslateDialogue(source);
        if (dialogue != null)
        {
            return dialogue;
        }

        if (!ShouldApplyGeneralFragments(objectName, source))
        {
            return null;
        }

        var result = ApplyFragments(TranslateTagDelimitedConnectors(source), _fragments);

        return string.Equals(result, source, StringComparison.Ordinal) ? null : result;
    }

    private string? TranslateDirect(string source)
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

        return null;
    }

    private void DumpUntranslated(TMP_Text textComponent, string source)
    {
        if (string.Equals(textComponent.gameObject.name, "Game Time And Progress Text", StringComparison.Ordinal))
        {
            return;
        }

        var visibleText = Regex.Replace(source, "<[^>]+>", string.Empty);
        if (ShouldIgnoreUntranslated(textComponent.gameObject.name, visibleText))
        {
            return;
        }

        if (string.Equals(textComponent.gameObject.name, "Text", StringComparison.Ordinal) &&
            IsKnownDialoguePrefix(visibleText))
        {
            return;
        }

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

    private void DumpResidualTranslation(TMP_Text textComponent, string source, string translated)
    {
        var visibleTranslation = GetVisibleText(translated);
        if (_residualDumpPath.Length == 0 ||
            !HasActionableEnglish(visibleTranslation) ||
            ShouldIgnoreUntranslated(textComponent.gameObject.name, visibleTranslation))
        {
            return;
        }

        var signature = $"{textComponent.gameObject.name}\n{source}\n{translated}";
        if (!_dumpedResidualTranslations.Add(signature))
        {
            return;
        }

        var objectName = textComponent.gameObject.name.Replace('\t', ' ');
        File.AppendAllText(
            _residualDumpPath,
            $"{DateTime.Now:yyyy-MM-dd HH:mm:ss}\t{objectName}\t{Escape(source)}\t{Escape(translated)}{Environment.NewLine}",
            Encoding.UTF8);
    }

    private static bool HasActionableEnglish(string visibleText)
    {
        if (Regex.IsMatch(
                visibleText.Trim(),
                "^(?:Tiny Rogues|BepInEx|XUnity|Steam|Discord|PC Senior \\(Retro\\)|CRT)$",
                RegexOptions.CultureInvariant | RegexOptions.IgnoreCase))
        {
            return false;
        }

        foreach (Match match in Regex.Matches(
                     visibleText,
                     "[A-Za-z][A-Za-z'-]*",
                     RegexOptions.CultureInvariant))
        {
            var word = match.Value;
            if (word.Length <= 1 ||
                word is "EXP" or "STR" or "DEX" or "INT" or "RNG" or "DPS" or "HP" or "MP" or "HUD" or
                    "FPS" or "TMP" or "UI" or "CRT")
            {
                continue;
            }

            return true;
        }

        return false;
    }

    private static bool ShouldIgnoreUntranslated(string objectName, string visibleText)
    {
        if (objectName == "Error Message")
        {
            return true;
        }

        if (objectName == "Label: \"CRT\"")
        {
            return true;
        }

        if (objectName is "Text (TMP)" &&
            visibleText is "Tab" or "Shift" or "Esc")
        {
            return true;
        }

        if (objectName == "Text" &&
            (Regex.IsMatch(visibleText, "^[A-Za-z]{1,3}$", RegexOptions.CultureInvariant) ||
             Regex.IsMatch(visibleText, "^(?:asdasd)+", RegexOptions.CultureInvariant | RegexOptions.IgnoreCase)))
        {
            return true;
        }

        if (objectName is "Title" && visibleText == "TITLE")
        {
            return true;
        }

        if (Regex.IsMatch(visibleText, "[\u4e00-\u9fff]") &&
            (visibleText.Contains("Shift + Enter", StringComparison.Ordinal) ||
             visibleText.Trim() == "CRT："))
        {
            return true;
        }

        return visibleText is "ayaya?" or "PC Senior (Retro)" ||
               visibleText.EndsWith("Beefy Enemies", StringComparison.Ordinal);
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

    private bool IsKnownDialoguePrefix(string visibleSource)
    {
        if (visibleSource.Length < MinimumDialoguePrefixLength)
        {
            return false;
        }

        var maximumPrefixLength = Math.Min(MaximumDialoguePrefixLength, visibleSource.Length);
        for (var prefixLength = MinimumDialoguePrefixLength;
             prefixLength <= maximumPrefixLength;
             prefixLength++)
        {
            var prefix = visibleSource[..prefixLength];
            if (!_dialogueEntries.TryGetValue(prefix, out var entries))
            {
                continue;
            }

            if (entries.Any(entry =>
                    entry.Source.StartsWith(visibleSource, StringComparison.OrdinalIgnoreCase)))
            {
                return true;
            }
        }

        return false;
    }

    private void LoadPluginFragments(
        string fileName,
        List<KeyValuePair<string, string>> fragments)
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
                fragments.Add(new KeyValuePair<string, string>(source, translated));
            }
        }

        fragments.Sort((left, right) => right.Key.Length.CompareTo(left.Key.Length));
    }

    private static bool IsItemPanel(string objectName, string source)
    {
        if (objectName is not ("Description Text" or "Text"))
        {
            return false;
        }

        var signals = 0;
        if (source.Contains("Weapon Type:", StringComparison.Ordinal)) signals++;
        if (source.Contains("Weapon Range:", StringComparison.Ordinal)) signals++;
        if (source.Contains("Attack Damage:", StringComparison.Ordinal)) signals++;
        if (source.Contains("Equip Load", StringComparison.Ordinal)) signals++;
        if (source.Contains("Attunement:", StringComparison.Ordinal)) signals++;
        if (source.Contains("Damage Scaling:", StringComparison.Ordinal)) signals++;
        if (source.Contains("Body Armor", StringComparison.Ordinal)) signals++;
        if (source.Contains("装备负重", StringComparison.Ordinal)) signals++;
        if (source.Contains("调谐", StringComparison.Ordinal)) signals++;
        return signals >= 2 ||
               source.Contains("Equip Load", StringComparison.Ordinal) ||
               source.Contains("装备负重", StringComparison.Ordinal);
    }

    private static bool IsItemDetailPanel(string objectName, string source)
    {
        if (IsItemPanel(objectName, source))
        {
            return true;
        }

        return objectName is "Text" or "Description Text" &&
               (source.Contains("<color=#808080>Consumable</color>", StringComparison.Ordinal) ||
                source.Contains("<color=#808080>消耗品</color>", StringComparison.Ordinal) ||
                source.Contains("Gift Box", StringComparison.Ordinal) ||
                source.Contains("礼物盒", StringComparison.Ordinal));
    }

    private static bool IsStructuredRichText(string objectName, string source)
    {
        if (IsItemDetailPanel(objectName, source))
        {
            return true;
        }

        if (objectName is not ("Description Text" or "Text"))
        {
            return false;
        }

        return source.Contains("\n•", StringComparison.Ordinal) ||
               source.Contains("<color=#808080>Consumable</color>", StringComparison.Ordinal) ||
               source.Contains("<color=#808080>消耗品</color>", StringComparison.Ordinal) ||
               source.Contains("Maximum Stacks:", StringComparison.Ordinal) ||
               source.Contains("Reward choices", StringComparison.Ordinal) ||
               source.StartsWith("Grants", StringComparison.Ordinal) ||
               source.StartsWith("Drops Rewards", StringComparison.Ordinal) ||
               source.Contains("Lucky Hits", StringComparison.Ordinal) ||
               source.Contains("Cursed Hits", StringComparison.Ordinal) ||
               source.StartsWith("<color=#00E61A>+", StringComparison.Ordinal);
    }

    private static bool ShouldApplyGeneralFragments(string objectName, string source)
    {
        if (objectName is "Character Title Text" or "General Stats" or "Tab Label (TMP)" or
            "Label" or "Value" or "Trait Title" or "Trait Description" or "Title Text" or
            "Input Alias" or "Elite Enchantment Text" or "Main Header" or "Equipment Name" or
            "Collection Item Title" or "Collection Item Description" or
            "Class Ability Title" or "Class Stats Text" or
            "Selected Gift Name" or "Selected Gift Description" or
            "Description Part 1" or "Description Part 2" or
            "Cinder Modifier Title" or "Cinder Modifier Description" or
            "Button Text" or "Boss Name Text" or "Objective Header" or "Objective Text" or
            "Info Text" or "Skill Description" ||
            objectName.StartsWith("Choice ", StringComparison.Ordinal) ||
            objectName.EndsWith(" (Text)", StringComparison.Ordinal))
        {
            return true;
        }

        return source.Contains("After each run you gain mastery", StringComparison.Ordinal) ||
               source.Contains("Per level you can allocate one perk", StringComparison.Ordinal) ||
               source.Contains("The Bonfire beckons you", StringComparison.Ordinal) ||
               (source.Contains("Effect of", StringComparison.Ordinal) &&
                source.Contains("Ailments", StringComparison.Ordinal) &&
                source.Contains("Soul Heart", StringComparison.Ordinal));
    }

    private static string ApplyLayout(string objectName, string source, string translated)
    {
        translated = NormalizePotentiallyUnsupportedGlyphs(translated);

        if (IsItemDetailPanel(objectName, source))
        {
            var sizedItem = Regex.Match(
                translated,
                "^<size=[^>]+>(?<body>.*)</size>$",
                RegexOptions.CultureInvariant | RegexOptions.Singleline);
            var itemBody = sizedItem.Success ? sizedItem.Groups["body"].Value : translated;
            return $"<size=92%>{itemBody}</size>";
        }

        if (string.Equals(objectName, "Trait Description", StringComparison.Ordinal))
        {
            var sizedTrait = Regex.Match(
                translated,
                "^<size=[^>]+>(?<body>.*)</size>$",
                RegexOptions.CultureInvariant | RegexOptions.Singleline);
            var traitBody = sizedTrait.Success ? sizedTrait.Groups["body"].Value : translated;
            return $"<size=100%>{traitBody}</size>";
        }

        if (translated.StartsWith("<size=", StringComparison.Ordinal))
        {
            return translated;
        }

        return translated;
    }

    private static bool IsGroundItemDetail(TMP_Text textComponent, string source)
    {
        return textComponent.gameObject.name == "Text" &&
               source.Length >= 30 &&
               source.Contains('\n') &&
               HasNearbyGroundActionPrompt(textComponent);
    }

    private void ExpandGroundItemPanel(TMP_Text textComponent)
    {
        var textRect = textComponent.rectTransform;
        if (textRect.parent is not RectTransform frame ||
            !_expandedGroundItemPanels.Add(frame.GetInstanceID()) ||
            frame.rect.width <= 0f ||
            frame.rect.height <= 0f)
        {
            return;
        }

        var extraWidth = frame.rect.width * 0.2f;
        var extraHeight = frame.rect.height;
        var frameSize = frame.sizeDelta;
        frameSize.x += extraWidth;
        frameSize.y += extraHeight;
        frame.sizeDelta = frameSize;

        var textSize = textRect.sizeDelta;
        if (Mathf.Approximately(textRect.anchorMin.x, textRect.anchorMax.x))
        {
            textSize.x += extraWidth;
        }
        if (Mathf.Approximately(textRect.anchorMin.y, textRect.anchorMax.y))
        {
            textSize.y += extraHeight;
        }
        textRect.sizeDelta = textSize;

        Plugin.PluginLog.LogInfo(
            $"Expanded ground item panel by {extraWidth:F0}x{extraHeight:F0} layout units.");
    }

    private static bool HasNearbyGroundActionPrompt(TMP_Text textComponent)
    {
        var ancestor = textComponent.transform.parent;
        for (var depth = 0; depth < 5 && ancestor != null; depth++, ancestor = ancestor.parent)
        {
            foreach (var label in ancestor.gameObject.GetComponentsInChildren<TMP_Text>(true))
            {
                if (label == null || label == textComponent)
                {
                    continue;
                }

                var text = Regex.Replace(label.text ?? string.Empty, "<[^>]+>", string.Empty);
                if (text.Contains("拾取", StringComparison.Ordinal) ||
                    text.Contains("购买", StringComparison.Ordinal) ||
                    text.Contains("Pick Up", StringComparison.OrdinalIgnoreCase) ||
                    text.Contains("Buy", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
        }

        return false;
    }

    private static string NormalizePotentiallyUnsupportedGlyphs(string value)
    {
        return value
            .Replace("\u200B", string.Empty)
            .Replace("\u200C", string.Empty)
            .Replace("\u200D", string.Empty)
            .Replace("\uFEFF", string.Empty)
            .Replace('，', ',')
            .Replace('。', '.')
            .Replace('：', ':')
            .Replace('；', ';')
            .Replace('！', '!')
            .Replace('？', '?')
            .Replace('（', '(')
            .Replace('）', ')')
            .Replace('、', ',')
            .Replace('“', '"')
            .Replace('”', '"')
            .Replace('【', '[')
            .Replace('】', ']')
            .Replace('《', '"')
            .Replace('》', '"')
            .Replace('·', '.')
            .Replace('—', '-');
    }

    private static string ApplyFragments(
        string source,
        List<KeyValuePair<string, string>> fragments)
    {
        // 安全替换：跳过 <...> 富文本标签内部，只对可见文本做替换
        return Regex.Replace(
            source,
            "(<[^>]+>)|([^<]+)",
            match =>
            {
                // Group 1 匹配到的是标签，原样返回
                if (match.Groups[1].Success)
                {
                    return match.Value;
                }

                // Group 2 匹配到的是可见文本，做片段替换
                var result = match.Value;
                foreach (var pair in fragments)
                {
                    if (result.Contains(pair.Key, StringComparison.Ordinal))
                    {
                        result = result.Replace(pair.Key, pair.Value, StringComparison.Ordinal);
                    }
                }

                return result;
            },
            RegexOptions.CultureInvariant);
    }

    private static string TranslateTagDelimitedConnectors(string source)
    {
        source = Regex.Replace(source, "(?<=>)to(?=<)", "至", RegexOptions.CultureInvariant);
        source = Regex.Replace(source, "(?<=>)to (?=<color)", "作用于 ", RegexOptions.CultureInvariant);
        source = Regex.Replace(source, "(?<=>)\\nto (?=<color)", "\n作用于 ", RegexOptions.CultureInvariant);
        return Regex.Replace(source, "(?<=>)for (?=<color)", "持续 ", RegexOptions.CultureInvariant);
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

    private static string FlattenDecoratedAsciiRuns(string value)
    {
        return Regex.Replace(
            value,
            "(?:<color=[^>]+>[A-Za-z ]</color>){4,}",
            match => Regex.Replace(match.Value, "<[^>]+>", string.Empty),
            RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
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
