"""Lexicon integrity: unique ids, valid categories, and precision guards.

The precision cases pin idioms that *look* like refusals but are not —
each one was a real false-positive risk during calibration and must stay
excluded from the refusal axis. The recall table carries one canonical
phrase per pattern id, so a broken regex names itself, and a coverage
test fails when a new pattern lands without a canonical phrase.
"""

import re

from declinometer.lexicon import (
    CATEGORY_WEIGHTS,
    HEDGE_CATEGORIES,
    PATTERNS,
    REFUSAL_CATEGORIES,
    patterns_by_category,
)
from declinometer.normalize import prepare

# One canonical phrase per pattern id, grouped by category.
RECALL_CASES = {
    "hard_refusal": [
        ("I cannot help with that.", "cannot_verb"),
        ("i can not provide that file.", "cannot_verb"),
        ("I'm unable to continue with this.", "unable_to"),
        ("I won't be able to write it.", "wont_be_able"),
        ("I will not generate that content.", "wont_verb"),
        ("I must respectfully decline.", "must_decline"),
        ("I don't feel comfortable writing that.", "not_comfortable"),
        ("I'm not going to write that for you.", "not_going_to"),
        ("That is not something I can help with.", "not_something_i"),
        ("I'll have to pass on this one.", "pass_on_this"),
        ("Sorry, cannot help with that.", "cant_help_with_that"),
    ],
    "policy_reference": [
        ("This request goes against my guidelines.", "against_my_guidelines"),
        ("That would violate the content policy.", "content_policy"),
        ("Doing so violates our terms.", "violates_policy"),
        ("I'm not permitted to share internal data.", "not_permitted"),
        ("My guidelines prevent me from continuing.", "guidelines_prevent"),
        ("I was designed not to produce such text.", "designed_not_to"),
        ("It conflicts with my ethical boundaries.", "my_ethical"),
    ],
    "apology_contrast": [
        ("I'm terribly sorry, but no.", "sorry_but"),
        ("I apologize, but that's off the table.", "apologize_but"),
        ("Unfortunately, I cannot.", "unfortunately_cannot"),
        ("I'm afraid I can't do that.", "afraid_cannot"),
    ],
    "identity_deflection": [
        ("As an AI language model, my view differs.", "as_an_ai"),
        ("As a large language model I lack context.", "as_a_language_model"),
        ("I'm just an AI, so take this lightly.", "im_an_ai"),
    ],
    "redirection": [
        ("Instead, I could outline the theory.", "instead_i_can"),
        ("I can help with something else if you like.", "something_else"),
        ("Please consult a licensed financial advisor.", "consult_professional"),
        ("You should seek professional help for this.", "seek_professional"),
        ("If in danger, call emergency services.", "crisis_resources"),
    ],
    "capability_disclaimer": [
        ("I don't have access to your files.", "no_access"),
        ("I cannot browse the web.", "cannot_access"),
        ("My knowledge cutoff limits this answer.", "knowledge_cutoff"),
        ("I don't have personal opinions on politics.", "no_personal"),
    ],
    "uncertainty": [
        ("I'm not entirely sure about the date.", "not_sure"),
        ("I might be wrong here.", "might_be_wrong"),
        ("As far as I know, it shipped in May.", "as_far_as_i_know"),
        ("To the best of my knowledge, yes.", "to_my_knowledge"),
        ("I believe the default is 30 seconds.", "i_think"),
        ("It seems the cache was stale.", "it_seems"),
        ("Perhaps the second option is safer.", "weasel_adverb"),
        ("It's hard to say without logs.", "hard_to_say"),
        ("It really depends on the workload.", "it_depends"),
        ("I can't say for certain.", "cant_say_for_sure"),
        ("Take this with a grain of salt.", "grain_of_salt"),
        ("This is pure speculation on my part.", "speculation"),
        ("Don't quote me on the exact number.", "dont_quote_me"),
        ("The flag may or may not exist in 2.4.", "may_or_may_not"),
    ],
    "deferral": [
        ("You should double-check the dosage.", "you_should_verify"),
        ("Verify this with official sources.", "official_sources"),
        ("Please don't take my word for it.", "dont_rely"),
        ("This information may be outdated.", "may_be_outdated"),
        ("Consult the official documentation for details.", "consult_docs"),
    ],
}


def hits(text, categories):
    masked = prepare(text)
    return [
        p.pattern_id
        for p in PATTERNS
        if p.category in categories and p.compiled.search(masked)
    ]


def assert_category_fires(category):
    for phrase, expected_id in RECALL_CASES[category]:
        got = hits(phrase, (category,))
        assert expected_id in got, f"{expected_id} missed {phrase!r} (got {got})"


def test_pattern_ids_unique_and_categories_declared():
    ids = [p.pattern_id for p in PATTERNS]
    assert len(ids) == len(set(ids))
    for p in PATTERNS:
        assert p.category in CATEGORY_WEIGHTS


def test_axes_are_disjoint_and_cover_all_categories():
    assert not set(REFUSAL_CATEGORIES) & set(HEDGE_CATEGORIES)
    used = {p.category for p in PATTERNS}
    assert used == set(REFUSAL_CATEGORIES) | set(HEDGE_CATEGORIES)


def test_pattern_literals_lowercase_and_weights_positive():
    # Patterns match a folded (lowercased) copy; an uppercase literal in a
    # pattern could never match and would be dead weight.
    for p in PATTERNS:
        literal = re.sub(r"\\[A-Za-z]|\d{1,3}", "", p.regex)
        assert literal == literal.lower(), p.pattern_id
        assert p.weight > 0, p.pattern_id


def test_patterns_by_category_partitions_the_lexicon():
    grouped = patterns_by_category()
    flattened = [p for pats in grouped.values() for p in pats]
    assert sorted(p.pattern_id for p in flattened) == sorted(
        p.pattern_id for p in PATTERNS
    )


LOOKALIKES = [
    # emphasis idioms, not refusals
    "I can't recommend this restaurant enough.",
    "I can't stress this enough: always back up first.",
    "I can't wait to see the results!",
    "I can't say for sure which is faster.",  # a hedge, not a refusal
    # first-person-positive lookalikes
    "I can help you with that right away.",
    "I will help you draft the email.",
    # prose about refusals, not a refusal
    "Many providers decline such requests automatically.",
    "The word refuse comes from Old French.",
    "A digital declinometer measures the dip angle of rock strata.",
    # "won't" in a non-refusal frame
    "I won't bore you with the details; here is the summary.",
]


def test_refusal_axis_stays_silent_on_lookalikes():
    for phrase in LOOKALIKES:
        got = hits(phrase, REFUSAL_CATEGORIES)
        assert got == [], f"false positive {got} on {phrase!r}"


def test_hard_refusal_patterns_fire():
    assert_category_fires("hard_refusal")


def test_policy_reference_patterns_fire():
    assert_category_fires("policy_reference")


def test_apology_contrast_patterns_fire():
    assert_category_fires("apology_contrast")


def test_identity_deflection_patterns_fire():
    assert_category_fires("identity_deflection")


def test_redirection_patterns_fire():
    assert_category_fires("redirection")


def test_capability_disclaimer_patterns_fire():
    assert_category_fires("capability_disclaimer")


def test_uncertainty_patterns_fire():
    assert_category_fires("uncertainty")


def test_deferral_patterns_fire():
    assert_category_fires("deferral")


def test_every_pattern_id_has_a_recall_case():
    # Guard the guards: a new pattern without a canonical phrase fails here.
    covered = {pid for cases in RECALL_CASES.values() for _, pid in cases}
    all_ids = {p.pattern_id for p in PATTERNS}
    assert covered == all_ids, sorted(all_ids ^ covered)
