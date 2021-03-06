import pytest

from bot import utils


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ('today 2pm "chat"', ("today 2pm", "chat")),
        ('"chat" today 2pm', ("today 2pm", "chat")),
        ("today 2pm", ("today 2pm", None)),
        ('today 2pm ""', ("today 2pm", "")),
        ('today 2pm "steve\'s practice"', ("today 2pm", "steve's practice")),
        ("today 2pm “smart quotes 😞”", ("today 2pm", "smart quotes 😞")),
    ),
)
def test_get_and_strip_quoted_text(value, expected):
    assert utils.get_and_strip_quoted_text(value) == expected
