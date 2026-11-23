from app.core.slugs import MAX_SLUG_LENGTH, slugify, unique_slug


def test_slugify_real_guide_titles():
    assert slugify("No power / PC will not turn on") == "no-power-pc-will-not-turn-on"
    assert slugify("PSU overheating or fan not spinning") == "psu-overheating-or-fan-not-spinning"
    assert (
        slugify("System powers on but will not POST (PSU related)")
        == "system-powers-on-but-will-not-post-psu-related"
    )


def test_slugify_collapses_punctuation_and_spaces():
    assert slugify("  RAM -- not   detected!!  ") == "ram-not-detected"


def test_slugify_drops_accents_and_non_ascii():
    assert slugify("Café fan noise") == "cafe-fan-noise"
    assert slugify("風扇 fan noise") == "fan-noise"


def test_slugify_falls_back_when_nothing_is_left():
    assert slugify("???") == "guide"
    assert slugify("") == "guide"


def test_slugify_truncates_without_leaving_a_trailing_hyphen():
    slug = slugify("word " * 40)
    assert len(slug) <= MAX_SLUG_LENGTH
    assert not slug.endswith("-") and not slug.startswith("-")


def test_unique_slug_adds_a_counter_and_remembers_what_it_gave_out():
    taken = {"ram-not-detected"}
    assert unique_slug("ram-not-detected", taken) == "ram-not-detected-2"
    assert unique_slug("ram-not-detected", taken) == "ram-not-detected-3"
    assert unique_slug("fan-noise", taken) == "fan-noise"
    assert {"ram-not-detected-2", "ram-not-detected-3", "fan-noise"} <= taken