"""Process-local provider cooldown book."""

from model_radar.cooldown import COOLDOWN_SECONDS, CooldownBook


def test_fresh_book_is_not_cooled():
    book = CooldownBook()
    assert book.is_cooled("nvidia") is False
    assert book.remaining("nvidia") == 0.0
    assert book.reason("nvidia") is None


def test_record_cools_until_expiry():
    book = CooldownBook()
    book.record("nvidia", "529", seconds=600, now=1000.0)
    assert book.is_cooled("nvidia", now=1000.0) is True
    assert book.is_cooled("nvidia", now=1599.0) is True
    assert book.remaining("nvidia", now=1000.0) == 600.0
    assert book.reason("nvidia") == "529"
    assert book.is_cooled("nvidia", now=1600.0) is False
    assert book.remaining("nvidia", now=1600.0) == 0.0


def test_clear_one_and_all():
    book = CooldownBook()
    book.record("nvidia", "402", now=0.0)
    book.record("groq", "429", now=0.0)
    book.clear("nvidia")
    assert book.is_cooled("nvidia", now=1.0) is False
    assert book.is_cooled("groq", now=1.0) is True
    book.clear()
    assert book.is_cooled("groq", now=1.0) is False


def test_default_window_is_ten_minutes():
    assert COOLDOWN_SECONDS == 600
    book = CooldownBook()
    book.record("sambanova", "402", now=0.0)
    assert book.is_cooled("sambanova", now=599.0) is True
    assert book.is_cooled("sambanova", now=600.0) is False
