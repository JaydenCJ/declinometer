"""Normalization must be length-preserving and mask mentioned-not-spoken text."""

from declinometer.normalize import (
    count_code_fences,
    count_list_items,
    fold,
    mask,
    prepare,
    word_count,
)


def test_fold_lowercases_and_converts_typographic_punctuation():
    # Curly apostrophes (U+2019) are the single most common reason a
    # lexicon misses a refusal; folding must neutralize them.
    assert fold("I CAN'T Help") == "i can't help"
    assert fold("I’m sorry") == "i'm sorry"
    assert fold("“I cannot help”") == '"i cannot help"'


def test_fold_preserves_length_for_any_input():
    samples = [
        "I’m sorry — but I can’t.",
        "İstanbul ẞtraße 混ぜ書き",  # tricky uppercase forms
        "“quoted” and ‘single’",
    ]
    for text in samples:
        assert len(fold(text)) == len(text)
    # 'İ'.lower() is two characters; folding must keep it rather than
    # corrupting every span after it.
    assert fold("İzmir")[0] == "İ"


def test_mask_blanks_fenced_code_blocks():
    folded = fold("intro\n```\ni cannot help with that\n```\noutro")
    masked = mask(folded)
    assert "i cannot help" not in masked
    assert "intro" in masked and "outro" in masked


def test_mask_preserves_length_and_newlines():
    folded = fold('before "i cannot help" after\n```\nx\n```\n')
    masked = mask(folded)
    assert len(masked) == len(folded)
    assert masked.count("\n") == folded.count("\n")


def test_mask_blanks_inline_code_and_double_quotes():
    assert "cannot help" not in prepare("the constant `i cannot help` is a test")
    masked = prepare('The model said "I cannot help with that" and stopped.')
    assert "cannot help" not in masked
    assert "the model said" in masked


def test_mask_leaves_apostrophes_alone():
    # Single quotes are contractions far more often than quotations;
    # masking them would blind the detector to "can't".
    assert "i can't help" in prepare("I can't help with that")


def test_mask_blanks_blockquote_lines():
    masked = prepare("Summary:\n> I cannot help with that\nMy view: proceed.")
    assert "cannot help" not in masked
    assert "my view: proceed." in masked


def test_mask_ignores_unterminated_quote():
    # A stray quote must not swallow the rest of the document.
    masked = prepare('He said " and then I explained the algorithm fully')
    assert "explained the algorithm" in masked


def test_word_count_contractions_and_empty():
    assert word_count("I can't help") == 3
    assert word_count("") == 0
    assert word_count("   \n\t") == 0


def test_count_code_fences_requires_closing_fence():
    assert count_code_fences("```\nx\n```") == 1
    assert count_code_fences("```\nunclosed") == 0
    assert count_code_fences("none") == 0


def test_count_list_items_bullets_numbers_and_non_items():
    text = "- one\n* two\n+ three\n1. four\n2) five\nplain line"
    assert count_list_items(text) == 5
    # horizontal rules and bare dashes are not list items
    assert count_list_items("---\n- \n-x") == 0
