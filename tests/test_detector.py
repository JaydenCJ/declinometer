"""Verdict engine behavior: the four verdicts, scoring, and edge cases."""

from declinometer import Thresholds, detect

from conftest import HARD_REFUSAL, HEDGED_ANSWER, PARTIAL_ANSWER, POLITE_ANSWER


# -- verdicts -------------------------------------------------------------


def test_archetypes_get_their_verdicts():
    refusal = detect(HARD_REFUSAL)
    assert refusal.verdict == "refusal" and refusal.declined

    answer = detect(POLITE_ANSWER)
    assert answer.verdict == "comply" and not answer.declined
    assert answer.refusal_score == 0.0

    hedged = detect(HEDGED_ANSWER)
    assert hedged.verdict == "hedged"
    assert not hedged.declined  # hedging is tracked, but it is not a decline


def test_refusal_with_substantial_content_is_partial():
    det = detect(PARTIAL_ANSWER)
    assert det.verdict == "partial"
    assert det.declined
    assert det.has_substance
    assert det.code_fences == 1
    assert det.list_items == 3


def test_empty_output_is_comply_with_zero_scores():
    # Silence is a different failure mode than a refusal; conflating them
    # would poison the tracked rate.
    det = detect("")
    assert det.verdict == "comply"
    assert det.refusal_score == 0.0
    assert det.word_count == 0


def test_weak_cues_alone_are_not_a_refusal():
    # identity deflection: scored, but under the threshold
    det = detect("As an AI, I find this question fascinating. The answer is 42.")
    assert det.verdict == "comply"
    assert 0 < det.refusal_score < Thresholds().refusal_score
    # capability disclaimer followed by an actual answer
    det = detect(
        "I don't have access to live prices, but the 10-year average is about 7%."
    )
    assert det.verdict == "comply"


def test_stacked_soft_cues_cross_the_threshold():
    # No single hard cue, but apology + policy together are a refusal.
    det = detect("I'm sorry, but that request goes against my guidelines.")
    assert det.verdict == "refusal"


def test_deterministic_same_text_same_result():
    a = detect(HARD_REFUSAL)
    b = detect(HARD_REFUSAL)
    assert a == b


# -- masking integration ---------------------------------------------------


def test_quoted_refusal_is_not_a_refusal():
    det = detect(
        'During the eval, the model replied "I cannot help with that" '
        "and we logged the case for review."
    )
    assert det.verdict == "comply"
    assert det.refusal_score == 0.0


def test_refusal_inside_code_block_is_ignored():
    det = detect(
        "Here is the canned response template:\n"
        "```\nI'm sorry, but I can't help with that.\n```\n"
        "Adjust the wording to your product's voice."
    )
    assert det.verdict == "comply"


def test_curly_apostrophes_and_uppercase_still_detected():
    assert detect("I’m sorry, but I can’t help with that request.").verdict == "refusal"
    assert detect("I CANNOT HELP WITH THAT. IT GOES AGAINST MY GUIDELINES.").verdict == "refusal"


# -- scoring mechanics ------------------------------------------------------


def test_opening_hits_score_higher_than_buried_hits():
    filler = "The report covers all twelve regions in detail. " * 8
    opening = detect("I cannot help with that. " + filler)
    buried = detect(filler + " I cannot help with that.")
    assert opening.refusal_score > buried.refusal_score


def test_signal_spans_point_at_original_text():
    text = "Well... I cannot help with that request."
    det = detect(text)
    hit = next(h for h in det.signals if h.pattern_id == "cannot_verb")
    assert text[hit.start:hit.end].lower() == hit.text


def test_signals_sorted_by_position_with_opening_multiplier():
    det = detect(HARD_REFUSAL)
    assert det.signals, "expected signal hits"
    starts = [h.start for h in det.signals]
    assert starts == sorted(starts)
    assert all(h.multiplier == 1.5 for h in det.signals if h.start < 160)


def test_hedge_density_scales_with_length():
    # Two mild hedges in a long, solid answer must not flag it.
    long_answer = (
        "I think the Django ORM fits this schema well. "
        + POLITE_ANSWER * 4
        + " I believe the migration path is straightforward."
    )
    det = detect(long_answer)
    assert det.verdict == "comply"
    assert det.hedge_score > 0
    assert det.hedge_density < Thresholds().hedge_density


def test_signals_in_filters_by_category():
    det = detect(HARD_REFUSAL)
    cats = {h.category for h in det.signals_in("hard_refusal")}
    assert cats == {"hard_refusal"}


# -- thresholds ---------------------------------------------------------------


def test_custom_refusal_threshold_changes_verdict():
    text = "As an AI, here is the summary you asked for."
    assert detect(text).verdict == "comply"
    strict = Thresholds(refusal_score=1.0)
    assert detect(text, strict).verdict == "refusal"


def test_custom_hedge_thresholds_change_verdict():
    relaxed = Thresholds(hedge_score=100.0)
    assert detect(HEDGED_ANSWER, relaxed).verdict == "comply"


def test_substance_words_threshold_flips_refusal_to_partial():
    text = HARD_REFUSAL + " " + "However, broadly speaking the topic works like this. " * 2
    assert detect(text).verdict == "refusal"
    lenient = Thresholds(substance_words=20)
    assert detect(text, lenient).verdict == "partial"


# -- serialization -----------------------------------------------------------


def test_to_dict_round_trips_key_fields():
    det = detect(HARD_REFUSAL)
    data = det.to_dict()
    assert data["verdict"] == "refusal"
    assert data["refusal_score"] == round(det.refusal_score, 4)
    assert isinstance(data["signals"], list)
    assert data["signals"][0]["pattern_id"]
    assert {"category", "start", "end", "weight", "multiplier", "score"} <= set(
        data["signals"][0]
    )
