"""Utility functions for endpoint controllers."""

from random import choice
import string


def generate_id(
    charset: str = ''.join([string.ascii_letters, string.digits]),
    length: int = 6,
) -> str:
    """Generate random string based on allowed set of characters.

    Args:
        charset: String of allowed characters.
        length: Length of returned string.

    Returns:
        Random string of specified length and composed of defined set of
        allowed characters.
    """
    return ''.join(choice(charset) for __ in range(length))
