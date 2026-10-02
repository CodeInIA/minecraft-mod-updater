import re

import pytest

import i18n

PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.mark.parametrize("lang", sorted(i18n.STRINGS))
def test_every_language_has_every_string(lang):
    assert set(i18n.STRINGS[lang]) == set(i18n.STRINGS["en"])


@pytest.mark.parametrize("lang", sorted(i18n.STRINGS))
def test_placeholders_match_english(lang):
    for key, english in i18n.STRINGS["en"].items():
        assert sorted(PLACEHOLDER.findall(i18n.STRINGS[lang][key])) == sorted(PLACEHOLDER.findall(english)), key


@pytest.mark.parametrize("lang", sorted(i18n.STRINGS))
def test_strings_format_without_errors(lang):
    i18n.set_language(lang)
    for key, english in i18n.STRINGS["en"].items():
        kwargs = {name: "X" for name in PLACEHOLDER.findall(english)}
        assert i18n.t(key, **kwargs)
    i18n.set_language("en")


def test_languages_list_matches_translations():
    assert set(i18n.LANGUAGES) == set(i18n.STRINGS)


@pytest.mark.parametrize("raw, expected", [
    ("es_ES", "es"), ("es-ES", "es"), ("es_ES.UTF-8", "es"), ("pt_BR", "pt"), ("zh-Hans-CN", "zh"),
    ("de_DE@euro", "de"), ("ja_JP.eucJP", "ja"), ("C", "c"),
])
def test_normalize_language_codes(raw, expected):
    assert i18n._normalize(raw) == expected


def test_unknown_language_falls_back(monkeypatch):
    monkeypatch.setattr(i18n, "_system_language_candidates", lambda: ["xx_XX", "C"])
    assert i18n.set_language(i18n.SYSTEM) == "en"
    monkeypatch.setattr(i18n, "_system_language_candidates", lambda: ["fr_CA.UTF-8"])
    assert i18n.set_language(i18n.SYSTEM) == "fr"
    i18n.set_language("en")


def test_missing_key_returns_english_or_key():
    i18n.set_language("es")
    assert i18n.t("does_not_exist") == "does_not_exist"
    i18n.set_language("en")
