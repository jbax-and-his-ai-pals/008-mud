# engine/utils/articles.py
"""Put "the" in front of a thing's name, unless the name already starts with an article."""

_ARTICLES = ("the ", "a ", "an ", "some ")


def the(name, capital: bool = False) -> str:
    """"goblin" -> "the goblin"; "the chancellor" -> "the chancellor" (never "the the chancellor").

    A name that is a proper noun ("Maya Chen") is left as it is only by callers that check for
    that; this helper only guards against doubling an article.
    """
    text = str(name)
    if not text.lower().startswith(_ARTICLES):
        text = "the " + text
    return text[0].upper() + text[1:] if capital else text
