"""
Pydantic models and utilities for batch URL processing
"""

import re
from typing import List, Tuple


def parse_url_file(content: str) -> Tuple[List[str], List[str]]:
    """
    Parse a text file containing URLs.

    Args:
        content: File content as a string

    Returns:
        Tuple of (valid_urls, errors)
        - valid_urls: List of valid URLs
        - errors: List of error messages for invalid lines
    """
    valid_urls = []
    errors = []

    lines = content.strip().split('\n')

    for line_num, line in enumerate(lines, 1):
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip comments (lines starting with #)
        if line.startswith('#'):
            continue

        # Validate URL format
        if not (line.startswith('http://') or line.startswith('https://')):
            errors.append(f"Line {line_num}: Invalid URL format (must start with http:// or https://): {line[:50]}")
            continue

        # Basic URL validation using regex
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        if not url_pattern.match(line):
            errors.append(f"Line {line_num}: Malformed URL: {line[:50]}")
            continue

        valid_urls.append(line)

    return valid_urls, errors
