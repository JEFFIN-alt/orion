"""Small deterministic numeric checks for evidence-backed synthesis claims."""
import re


_NUMBER = re.compile(r'(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])')
_SOURCE_ID = re.compile(r'(doi|repository):\S+')


def numbers(text):
    """Return normalized numeric tokens, excluding numbers inside source IDs."""
    text = _SOURCE_ID.sub('', text)
    return [match.group().replace(',', '') for match in _NUMBER.finditer(text)]


def ungrounded_numbers(claim_text, allowed_texts):
    """Numbers with at least two digits or a decimal must occur in allowed evidence."""
    allowed = {number for text in allowed_texts for number in numbers(text)}
    return [number for number in numbers(claim_text)
            if ('.' in number or len(number) >= 2) and number not in allowed]
