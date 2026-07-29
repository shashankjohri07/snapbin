import random
import string

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, TextLexer


BASE62_CHARS = string.ascii_letters + string.digits


def generate_short_code(length=8):
    return "".join(random.choices(BASE62_CHARS, k=length))


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
