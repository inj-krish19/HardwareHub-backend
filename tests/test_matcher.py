from types import SimpleNamespace as NS

from app.rule_engine import router
from app.rule_engine.matcher import best_match

SYMPTOMS = [
    NS(title="RAM is not detected", keywords="ram not detected, ram missing", bot_type="diagnostic"),
    NS(title="How often should I clean my PC?", keywords="pc cleaning schedule, dust in my pc", bot_type="maintenance"),
    NS(title="Will this RAM work with my motherboard?", keywords="can i use ddr5 on a ddr4 board", bot_type="compatibility"),
    NS(title="Build a gaming PC on a budget", keywords="gaming pc build, budget gaming pc", bot_type="budget"),
]


def _match(query):
    intent = router.route(query)
    bot = router.INTENT_TO_BOT.get(intent) if intent else None
    return best_match(query, SYMPTOMS, bot)


def test_direct_title_match():
    assert _match("RAM not detected").title == "RAM is not detected"


def test_stemming_dusty_matches_dust():
    assert _match("my pc is very dusty").title == "How often should I clean my PC?"


def test_compatibility_phrase():
    assert _match("Can I use DDR5 on a DDR4 board?").bot_type == "compatibility"


def test_budget_amount_routes_to_budget():
    assert router.route("gaming pc for 60000") == "budget_advisor"


def test_unrelated_query_has_no_match():
    assert _match("what is the capital of france") is None


def test_single_generic_word_does_not_match():
    assert _match("pc") is None