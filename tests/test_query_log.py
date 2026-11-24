from app.core.query_log import MAX_QUERY_LENGTH, clean_query


def test_keeps_the_text_and_builds_a_grouping_key():
    assert clean_query("  My PC   won't turn on!! ") == ("My PC won't turn on!!", "my pc won t turn on")


def test_repeats_with_different_case_or_punctuation_share_a_key():
    assert clean_query("PC wont turn on!!")[1] == clean_query("pc wont turn on")[1]


def test_too_short_or_empty_is_not_logged():
    assert clean_query("") is None
    assert clean_query("  ") is None
    assert clean_query("hi") is None
    assert clean_query(None) is None  # type: ignore[arg-type]


def test_digits_or_symbols_only_is_not_logged():
    assert clean_query("12345") is None
    assert clean_query("??? !!!") is None


def test_email_addresses_are_not_logged():
    assert clean_query("my email is sam@example.com pc broken") is None


def test_phone_numbers_are_not_logged_in_common_formats():
    assert clean_query("call me 9876543210 about my pc") is None
    assert clean_query("call 98765 43210 about my pc") is None
    assert clean_query("+91 (98765) 43-210 pc broken") is None


def test_budgets_and_model_numbers_are_still_logged():
    assert clean_query("best pc under 60000") is not None
    assert clean_query("ryzen 5 5600 with rtx 3060 not booting") is not None


def test_long_text_is_cut():
    text, _ = clean_query("word " * 200)
    assert len(text) <= MAX_QUERY_LENGTH and not text.endswith(" ")


def test_non_english_text_still_gets_a_key():
    assert clean_query("मेरा कंप्यूटर चालू नहीं होता") is not None