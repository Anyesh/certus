"""Real-world utility functions for Certus proof-of-concept demo.

These are the kind of pure functions found in production utility libraries:
string manipulation, data transformation, validation, math helpers.
"""


def chunk_list(lst, size):
    """Split a list into chunks of the given size."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def flatten_dict(d, parent_key="", sep="."):
    """Flatten a nested dictionary into dot-notation keys."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def deduplicate(lst):
    """Remove duplicates from a list while preserving order."""
    seen = set()
    result = []
    for item in lst:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def clamp(value, minimum, maximum):
    """Clamp a value between minimum and maximum."""
    return max(minimum, min(value, maximum))


def is_palindrome(s):
    """Check if a string is a palindrome (case-insensitive, ignoring spaces)."""
    cleaned = "".join(c.lower() for c in s if c.isalpha())
    return cleaned == cleaned[::-1]


def merge_sorted(a, b):
    """Merge two sorted lists into a single sorted list."""
    result = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            result.append(a[i])
            i += 1
        else:
            result.append(b[j])
            j += 1
    result.extend(a[i:])
    result.extend(b[j:])
    return result


def pascal_row(n):
    """Return the nth row of Pascal's triangle."""
    row = [1]
    for k in range(1, n + 1):
        row.append(row[-1] * (n - k + 1) // k)
    return row


def group_by(items, key_func):
    """Group items by a key function, returning a dict of lists."""
    groups = {}
    for item in items:
        k = key_func(item)
        if k not in groups:
            groups[k] = []
        groups[k].append(item)
    return groups


def levenshtein_distance(s1, s2):
    """Compute the edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def matrix_transpose(matrix):
    """Transpose a 2D matrix."""
    if not matrix:
        return []
    return [[row[i] for row in matrix] for i in range(len(matrix[0]))]
