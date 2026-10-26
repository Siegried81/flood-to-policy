"""Tests for the brief translation tab.

The model is mocked throughout: what is pinned here is not that a model
translates well, which no test can assert, but that a translation which changed a
figure or a citation never reaches the page. That is the whole value of the
module - the prose is the model's problem, the numbers are this repo's.
"""

from __future__ import annotations

import pytest

from src import translate

SECTION = (
    "At the 100-year return period, 29,727,887 residents are in the flood "
    "extent [S1]. The 50-year river discharge rises by a median 16.9% under "
    "RCP 8.5 [S2], and 810 of 1,345 regions drain into a basin shared with "
    "another country [S3]."
)


def _model(answer):
    """Stand in for the provider call, which is the only network in this path."""
    return lambda prompt, system=None: answer


# --- the digits survive the three separator conventions -------------------------

def test_the_same_number_in_three_languages_is_the_same_number():
    """English writes 1,345, French 1 345, Dutch 1.345 - and the same three
    characters mean thousands in one and a decimal point in another. Comparing
    the strings would reject every correct translation."""
    assert translate.digits("1,345") == ["1345"]
    assert translate.digits("1 345") == ["1345"]
    assert translate.digits("1.345") == ["1345"]
    assert translate.digits("16.9") == translate.digits("16,9") == ["169"]


def test_a_citation_marker_is_not_read_as_a_number():
    """`[S1]` holds a digit, and counting it as a figure would make every
    citation look like a lost number the moment one moved."""
    assert translate.digits("a claim [S1] and 42 people") == ["42"]
    assert translate.citations("a claim [S1] and [S12] again") == ["[S1]", "[S12]"]


def test_a_faithful_translation_passes_and_says_what_it_checked(monkeypatch):
    french = (
        "Pour une periode de retour de 100 ans, 29 727 887 habitants se trouvent "
    "dans l'emprise de l'inondation [S1]. Le debit fluvial de retour 50 ans "
    "augmente d'une mediane de 16,9 % selon le RCP 8.5 [S2], et 810 des "
    "1 345 regions se deversent dans un bassin partage avec un autre pays [S3]."
    )
    monkeypatch.setattr(translate, "complete", _model(french))
    out = translate.translate(SECTION, "fr")
    assert out.language == "fr"
    assert out.numbers == 7
    assert out.citations == 3
    assert "29 727 887" in out.text


# --- and the four ways it is allowed to fail ------------------------------------

def test_a_rounded_figure_is_refused(monkeypatch):
    """The failure that looks most like success. "a median of 17%" reads as a
    clean translation and is a different finding from 16.9%."""
    monkeypatch.setattr(
        translate, "complete",
        _model("Pour une periode de retour de 100 ans, 29 727 887 habitants [S1]. "
               "Le debit de retour 50 ans augmente d'une mediane de 17 % selon le "
               "RCP 8.5 [S2], et 810 des 1 345 regions [S3]."),
    )
    with pytest.raises(translate.TranslationFailed, match="figures changed"):
        translate.translate(SECTION, "fr")


def test_a_figure_written_out_in_words_is_refused(monkeypatch):
    """"29,7 millions" is how a translator would naturally write it, and it
    destroys the digits a reader would check against the table."""
    monkeypatch.setattr(
        translate, "complete",
        _model("Pour une periode de retour de 100 ans, 29,7 millions d'habitants "
               "[S1]. Le debit de retour 50 ans augmente d'une mediane de 16,9 % "
               "selon le RCP 8.5 [S2], et 810 des 1 345 regions [S3]."),
    )
    with pytest.raises(translate.TranslationFailed, match="figures changed"):
        translate.translate(SECTION, "fr")


def test_a_dropped_citation_is_refused(monkeypatch):
    """A brief whose claim lost its marker is an uncited claim, which is the one
    thing the drafting step refuses to produce in the first place."""
    monkeypatch.setattr(
        translate, "complete",
        _model("Pour une periode de retour de 100 ans, 29 727 887 habitants [S1]. "
               "Le debit de retour 50 ans augmente d'une mediane de 16,9 % selon le "
               "RCP 8.5 [S2], et 810 des 1 345 regions."),
    )
    with pytest.raises(translate.TranslationFailed, match="citations changed"):
        translate.translate(SECTION, "fr")


def test_reordered_citations_are_refused(monkeypatch):
    """Swapping two sentences swaps their markers, and every claim then points at
    the other's source. The count is unchanged, so only order catches it."""
    monkeypatch.setattr(
        translate, "complete",
        _model("Pour une periode de retour de 100 ans, 29 727 887 habitants [S2]. "
               "Le debit de retour 50 ans augmente d'une mediane de 16,9 % selon le "
               "RCP 8.5 [S1], et 810 des 1 345 regions [S3]."),
    )
    with pytest.raises(translate.TranslationFailed, match="citations changed"):
        translate.translate(SECTION, "fr")


def test_an_empty_answer_is_refused_rather_than_shown(monkeypatch):
    monkeypatch.setattr(translate, "complete", _model("   "))
    with pytest.raises(translate.TranslationFailed, match="returned nothing"):
        translate.translate(SECTION, "nl")


# --- the target language is a key, never free text ------------------------------

def test_english_is_not_a_target():
    """Offering it invites a round trip, and a translation of a translation is
    how a figure quietly changes."""
    with pytest.raises(ValueError, match="not a target language"):
        translate.translate(SECTION, "en")


def test_an_unknown_language_is_refused_before_the_model_is_called(monkeypatch):
    def explode(*_a, **_k):
        raise AssertionError("the model must not be called with a bad language")
    monkeypatch.setattr(translate, "complete", explode)
    with pytest.raises(ValueError, match="not a target language"):
        translate.translate(SECTION, "elvish")


def test_nothing_to_translate_is_refused():
    with pytest.raises(ValueError, match="nothing to translate"):
        translate.translate("   ", "fr")


def test_the_three_belgian_languages_are_offered():
    """A Belgian authority works in three; the brief has to reach all of them."""
    assert sorted(translate.LANGUAGES) == ["de", "fr", "nl"]


# --- what the digits alone let through ------------------------------------------
#
# Each lie below kept every digit and every citation, so `check` passed it and
# the page showed it. The figures are now compared as digit GROUPS, the scale
# words and the negations per language.

@pytest.mark.parametrize("src, out, why", [
    ("Water deeper than 1.5 m [S1].", "Eau de plus de 15 m [S1].", "decimal point moved"),
    ("Exposure rose 16.9% [S1].", "L'exposition a augmenté de 169 % [S1].", "decimal point moved"),
    ("About 1.2 million people [S1].", "Environ 1,2 milliard de personnes [S1].", "scale word"),
    ("Hainaut should not be prioritised [S1].", "Le Hainaut doit être priorisé [S1].", "negations"),
])
def test_a_meaning_change_that_keeps_the_digits_is_refused(monkeypatch, src, out, why):
    monkeypatch.setattr(translate, "complete", _model(out))
    with pytest.raises(translate.TranslationFailed, match=why):
        translate.translate(src, "fr")


@pytest.mark.parametrize("src, out, language", [
    ("Water deeper than 1.5 m [S1].", "Eau de plus de 1,5 m [S1].", "fr"),
    ("Exposure rose 16.9% [S1].", "Die Exposition stieg um 16,9 % [S1].", "de"),
    ("About 26000 people [S1].", "Ongeveer 26.000 mensen [S1].", "nl"),
    ("About 1,200 people [S1].", "Environ 1200 personnes [S1].", "fr"),
    ("About 1.2 million people [S1].", "Environ 1,2 million de personnes [S1].", "fr"),
    ("About 1.2 billion euros [S1].", "Environ 1,2 milliard d'euros [S1].", "fr"),
    ("About 1.2 billion euros [S1].", "Etwa 1,2 Milliarden Euro [S1].", "de"),
    ("Hainaut should not be prioritised [S1].", "Le Hainaut ne doit pas être priorisé [S1].", "fr"),
    ("Hainaut should not be prioritised [S1].", "Hainaut sollte nicht priorisiert werden [S1].", "de"),
    ("Hainaut should not be prioritised [S1].", "Henegouwen mag niet worden geprioriteerd [S1].", "nl"),
    ("It isn't required [S1].", "Ce n'est pas requis [S1].", "fr"),
    ("Neither Namur nor Liège is covered [S1].", "Ni Namur ni Liège ne sont couverts [S1].", "fr"),
    ("Hainaut is no longer exposed [S1].", "Le Hainaut n'est plus exposé [S1].", "fr"),
    ("Only Hainaut is exposed [S1].", "Seul le Hainaut n'est exposé qu'en partie [S1].", "fr"),
    ("This is not only a river risk [S1].", "Ce n'est pas seulement un risque fluvial [S1].", "fr"),
    ("Regulation No. 1293/2013 applies [S1].", "Le règlement n° 1293/2013 s'applique [S1].", "fr"),
])
def test_a_faithful_translation_still_passes(monkeypatch, src, out, language):
    monkeypatch.setattr(translate, "complete", _model(out))
    assert translate.translate(src, language).text == out


def test_the_digit_groups_keep_the_decimal_boundary_the_digits_lose():
    assert translate.digits("1.5") == translate.digits("15")
    assert translate.groups("1.5") == [("1", "5")] != translate.groups("15")
    assert (translate.groups("29,727,887") == translate.groups("29 727 887")
            == translate.groups("29.727.887") == [("29", "727", "887")])


def test_check_without_a_language_compares_figures_and_citations_only():
    """The language-free call keeps its old contract for any caller that has no
    target language to give; the scale and negation checks need one."""
    translate.check("Hainaut should not be prioritised [S1].", "Le Hainaut doit être priorisé [S1].")
    with pytest.raises(translate.TranslationFailed, match="decimal point"):
        translate.check("Water deeper than 1.5 m [S1].", "Eau de plus de 15 m [S1].")
