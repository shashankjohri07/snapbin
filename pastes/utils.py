import secrets
import string

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_all_lexers, get_lexer_by_name, TextLexer


BASE62_CHARS = string.ascii_letters + string.digits


def generate_short_code(length=8):
    return "".join(secrets.choice(BASE62_CHARS) for _ in range(length))


def get_unique_short_code(model_class, length=8):
    for _ in range(10):
        code = generate_short_code(length)
        if not model_class.objects.filter(short_code=code).exists():
            return code
    raise RuntimeError("Failed to generate a unique short code after 10 attempts")


def highlight_code(content, language):
    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except Exception:
        lexer = TextLexer()
    formatter = HtmlFormatter(nowrap=False, cssclass="highlight")
    return highlight(content, lexer, formatter)


def _supported_languages():
    return {alias for _, aliases, _, _ in get_all_lexers() for alias in aliases}


def normalize_language(language):
    """Return a Pygments-supported language alias, falling back to plain text."""
    language = (language or "text").strip().lower()
    return language if language in _supported_languages() else "text"


def generate_delete_token():
    return secrets.token_urlsafe(24)


def record_view(paste_or_code, language=None):
    """Increment the counter atomically and append a raw view event."""
    from django.db.models import F

    from .models import Paste, PasteViewEvent

    code = getattr(paste_or_code, "short_code", paste_or_code)
    language = language or getattr(paste_or_code, "language", "text")
    Paste.objects.filter(short_code=code, is_active=True).update(view_count=F("view_count") + 1)
    PasteViewEvent.objects.create(short_code=code, language=language)
