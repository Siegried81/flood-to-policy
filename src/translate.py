"""Translate an approved brief section, and prove the figures survived.

The brief is drafted in English because the corpus, the UI and the code are in
English and a jury reads it there. But the authority that would act on it is
Belgian, and a Walloon or Flemish official reads a recommendation in French or in
Dutch. So translation is a tab, never a rewrite: the English section stays the
record and the translation sits beside it.

**Why this module exists at all, rather than a line of prompt.** A translation is
the one transformation in this kit that is allowed to change every word and
forbidden to change a single number. A model asked to translate a paragraph will
cheerfully localise `29,727,887` to `29 727 887` - which is correct - and just as
cheerfully write `29,7 million`, drop a citation marker, or round `16.9%` to
`17%`. None of that looks wrong in the output. So every translation is checked
against its source, and one that lost a figure or a citation is returned with the
failure named rather than displayed.

**Separators are the trap inside the trap.** English writes `1,345`, French
writes `1 345`, Dutch writes `1.345`, and the same three characters mean
thousands in one language and a decimal point in another. Comparing the strings
would flag every correct translation; comparing the parsed numbers would need a
locale this module does not know. So the comparison is on the DIGITS alone, in
order: `29,727,887` and `29 727 887` are both `29727887`, while `29,7 million`
is `297` and fails.

The digits alone would let a decimal point vanish (`1.5` -> `15` is `15` both
times), so the digit GROUPS are compared too, with one tolerance: a thousands
grouping may be added or dropped (`26000` -> `26 000`), never a short trailing
group. Scale words ("million", "milliard") and the count of negations are
compared per language, because "1.2 million" -> "1,2 milliard" keeps every
digit, and a dropped "not" keeps every figure. What none of this sees: two
figures swapped between their regions, a direction verb flipped ("rose" ->
"a baissé"), or any change of meaning that keeps the numbers and the negations.

One structured call per section, same provider path as the drafting step, so a
dead venue network falls back to the local model here too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.rag import complete

#: The languages a Belgian authority actually works in. English is the source and
#: so is not a target: offering it would invite a round trip, and a translation of
#: a translation is how a figure quietly changes.
LANGUAGES = {
    "fr": "French",
    "nl": "Dutch",
    "de": "German",
}

SYSTEM_PROMPT = (
    "You translate one section of a policy brief for a public authority. "
    "Translate the prose faithfully into {language}, in the register a civil "
    "servant would use. Keep EVERY number exactly as it is: do not round, do not "
    "convert units, do not write a figure out in words. You may use the thousands "
    "and decimal separators of {language}. Keep every citation marker such as "
    "[S1] or [S2] exactly where it is. Keep place names, region names and "
    "institution names in their original form. Output the translation only, with "
    "no preamble and no note about what you did."
)

#: `[S1]`, `[S12]` - the marker the drafting step emits and the verify step counts.
_CITATION = re.compile(r"\[S\d+\]")

#: A run of digits, together with the separators that sit BETWEEN digits. The
#: lookarounds are what make `1,345` one token and `[S1], [S2]` two.
_NUMBER = re.compile(r"\d+(?:[ .,  ](?=\d)\d+)*")


class TranslationFailed(RuntimeError):
    """The translation came back, and it is not safe to show.

    Its own type so a UI can say which figure moved instead of rendering a
    paragraph that reads perfectly and is wrong.
    """


@dataclass(frozen=True)
class Translation:
    """A translated section and the evidence it is faithful."""

    text: str
    language: str
    numbers: int
    citations: int


def digits(text: str) -> list[str]:
    """Every number in the text, reduced to its digits, in order.

    Separators between digits are dropped rather than interpreted, because which
    of `.` and `,` is the decimal point depends on the language and this module
    translates into three of them. What survives is what must not change: the
    digit sequence.

    Citation markers are removed first. `[S1]` holds a digit, and counting it as
    a figure would make every citation look like a lost number the moment one
    moved - and would report a citation fault as a figure fault, which sends a
    reader looking in the wrong place.
    """
    text = _CITATION.sub(" ", text)
    return ["".join(ch for ch in m.group() if ch.isdigit())
            for m in _NUMBER.finditer(text)]


def groups(text: str) -> list[tuple[str, ...]]:
    """Every number in the text as its digit groups, in order: `16.9` is ("16", "9").

    `digits` alone reads `1.5` and `15` as the same figure, because it drops the
    separator - which is how a decimal point can vanish and the check still
    pass. The boundaries between groups are kept here while the separator
    characters are still not interpreted, so `29,727,887`, `29 727 887` and
    `29.727.887` are all ("29", "727", "887") and `16,9` matches `16.9`.
    """
    text = _CITATION.sub(" ", text)
    return [tuple(re.split(r"[^\d]", m.group())) for m in _NUMBER.finditer(text)]


def _same_figure(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Whether two digit-group tuples can be the same number in two locales.

    Equal groups always are. Otherwise the one legitimate difference is a
    thousands grouping added or dropped - `26000` against `26 000` - which is
    only possible when every group after the first has exactly three digits.
    A short trailing group ("1.5", "16.9") is a decimal part, and losing its
    boundary multiplies the figure.
    """
    if a == b:
        return True
    if "".join(a) != "".join(b):
        return False
    grouped, plain = (a, b) if len(a) > len(b) else (b, a)
    return len(plain) == 1 and all(len(g) == 3 for g in grouped[1:])


#: Scale words per language, as powers of ten. Separate tables because the same
#: word changes value across them: "billion" is 10^9 in English and 10^12 in
#: French and German, where 10^9 is "milliard" / "Milliarde".
SCALES = {
    "en": {"thousand": 3, "thousands": 3, "million": 6, "millions": 6, "mn": 6,
           "billion": 9, "billions": 9, "bn": 9, "trillion": 12, "trillions": 12},
    "fr": {"mille": 3, "milliers": 3, "million": 6, "millions": 6, "milliard": 9,
           "milliards": 9, "md": 9, "mrd": 9, "billion": 12, "billions": 12},
    "nl": {"duizend": 3, "duizenden": 3, "miljoen": 6, "miljoenen": 6, "mln": 6,
           "miljard": 9, "miljarden": 9, "mld": 9, "biljoen": 12},
    "de": {"tausend": 3, "tausende": 3, "million": 6, "millionen": 6, "mio": 6,
           "milliarde": 9, "milliarden": 9, "mrd": 9, "billion": 12, "billionen": 12},
}

#: Negation words per language. French counts a clause, not a word: "ne ... pas"
#: is one negation, so "ne"/"n'" is not listed and the second half is.
#: "Not only" and its translations are not negations and are removed first.
NEGATORS = {
    "en": {"not", "no", "never", "none", "nor", "without", "cannot", "nothing",
           "nobody", "neither"},
    "fr": {"pas", "jamais", "aucun", "aucune", "sans", "ni", "rien", "nul", "nulle"},
    "nl": {"niet", "geen", "nooit", "zonder", "noch", "niets", "niemand"},
    "de": {"nicht", "kein", "keine", "keinen", "keinem", "keiner", "keines", "nie",
           "niemals", "ohne", "weder", "nichts", "niemand"},
}
_NOT_ONLY = re.compile(
    r"\b(?:not\s+only|not\s+just|(?:(?:ne|n['’])\s*[^\W\d_]+\s+)?pas\s+seulement|"
    r"non\s+seulement|niet\s+alleen|nicht\s+nur)\b", re.IGNORECASE)
#: "n°" / "nº" is French for "No." (a number), not the "n'" of a negation.
_NUMERO = re.compile(r"\b[nN]\s*[°º]")
#: The two halves of "neither ... nor" in each language; German "noch" is not a
#: negator on its own ("still"), so "weder" alone carries the German pair.
_CORRELATIVES = {"en": ("neither", "nor"), "fr": ("ni", "ni"), "nl": ("noch", "noch"),
                 "de": ("weder", "weder")}
#: A word, keeping an English "n't" on the verb it negates ("don't", "isn’t").
_WORD = re.compile(r"[^\W\d_]+n['’]t\b|[^\W\d_]+", re.UNICODE)


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(_CITATION.sub(" ", text))]


def scales(text: str, language: str) -> list[int]:
    """The scale words in the text as powers of ten, sorted."""
    table = SCALES[language]
    return sorted(table[w] for w in _words(text) if w in table)


def negations(text: str, language: str) -> int:
    """How many negations the text holds, so a source and its translation compare.

    The unit is the negation, not the word: French "ne ... pas" counts once,
    and a correlative ("neither ... nor", "ni ... ni", "noch ... noch") counts
    once per sentence, so a faithful translation lands on the same number as
    its source. "No." before a digit is a regulation number, not a negation.
    """
    text = _NOT_ONLY.sub(" ", _CITATION.sub(" ", text))
    text = _NUMERO.sub(" ", re.sub(r"\bNo\.\s*(?=\d)", " ", text))
    words = NEGATORS[language]
    first, second = _CORRELATIVES[language]
    total = 0
    for sentence in re.split(r"(?<=[.!?;])\s+", text):
        found = [w for w in _words(sentence)
                 if w in words or (language == "en" and re.search(r"n['’]t$", w))]
        if first in found and second in found:
            found = [w for w in found if w not in (first, second)] + [first]
        total += len(found)
        if language == "fr":
            # A "ne"/"n'" with no second half in the sentence is still a negation
            # ("ne ... plus", "ne ... guère"), unless it is the restrictive
            # "ne ... que", which means "only".
            said = _words(sentence)
            restrictive = said.count("que") + said.count("qu")
            bare = said.count("ne") + said.count("n") - len(found) - restrictive
            total += max(0, bare)
    return total


def citations(text: str) -> list[str]:
    """Every citation marker, in order. Order matters: a brief cites per claim."""
    return _CITATION.findall(text)


def check(source: str, translated: str, language: str | None = None) -> None:
    """Raise unless every figure and every citation survived, in order.

    Deliberately strict about order as well as membership. A model that swaps two
    sentences also swaps their citations, and the result attributes each claim to
    the other's source - which no count of markers would catch.

    With `language` (a key of `LANGUAGES`) two more things are compared: the
    scale words, so "1.2 million" cannot become "1,2 milliard" with the digits
    intact, and the number of negations, so "should not be prioritised" cannot
    become "doit être priorisé". The source is English. Without `language` only
    the figures and the citations are checked, as before.
    """
    want, got = digits(source), digits(translated)
    if want != got:
        lost = [d for d in want if d not in got]
        added = [d for d in got if d not in want]
        # The count is reported only when it actually differs. When it matches
        # and the values do not - a rounded figure, the common case - leading
        # with "2 numbers became 2 numbers" reads like a bug in the check.
        detail = (
            f" Missing: {lost[:5]}." if lost else ""
        ) + (f" Invented: {added[:5]}." if added else "")
        counts = (
            f" Source has {len(want)} numbers, the translation {len(got)}."
            if len(want) != len(got) else ""
        )
        raise TranslationFailed(
            "The figures changed." + counts + detail
            + " Nothing is shown rather than a figure nobody can trace."
        )
    moved = [(a, b) for a, b in zip(groups(source), groups(translated))
             if not _same_figure(a, b)]
    if moved:
        shown = [f"{'.'.join(a)} became {'.'.join(b)}" for a, b in moved[:5]]
        raise TranslationFailed(
            "A decimal point moved: the digits are the same but the figure is not ("
            + "; ".join(shown) + ", groups shown separated by '.'). Nothing is "
            "shown rather than a figure ten or a hundred times off."
        )
    want, got = citations(source), citations(translated)
    if want != got:
        raise TranslationFailed(
            f"The citations changed: {want} became {got}. Every claim in a brief "
            f"is cited to a numbered passage, so a reordered marker points the "
            f"reader at the wrong source."
        )
    if language is None:
        return
    want, got = scales(source, "en"), scales(translated, language)
    if want != got:
        raise TranslationFailed(
            f"A scale word changed: the source has {[f'10^{p}' for p in want]}, the "
            f"translation {[f'10^{p}' for p in got]}. The digits survive and the "
            "figure is a thousand times off - \"billion\" is 10^9 in English and "
            "10^12 in French and German."
        )
    want, got = negations(source, "en"), negations(translated, language)
    if want != got:
        raise TranslationFailed(
            f"The negations changed: the source has {want}, the translation {got}. "
            "A dropped or added \"not\" reverses a recommendation and reads "
            "perfectly; check the translation sentence by sentence."
        )


def translate(text: str, language: str) -> Translation:
    """One section into one language, checked before it is returned.

    `language` is a key of `LANGUAGES`, not a free-text name: a typo would reach
    the model as an instruction and come back as something plausible in a language
    nobody asked for.
    """
    if language not in LANGUAGES:
        raise ValueError(
            f"`{language}` is not a target language. Choose one of "
            f"{sorted(LANGUAGES)} - English is the source and is not a target."
        )
    if not text or not text.strip():
        raise ValueError("There is nothing to translate; draft the section first.")

    name = LANGUAGES[language]
    answer = complete(text, SYSTEM_PROMPT.format(language=name)).strip()
    if not answer:
        raise TranslationFailed(
            f"The model returned nothing for {name}. The English section is "
            f"unchanged; try again or show it as it is."
        )
    check(text, answer, language)
    return Translation(
        text=answer,
        language=language,
        numbers=len(digits(text)),
        citations=len(citations(text)),
    )
