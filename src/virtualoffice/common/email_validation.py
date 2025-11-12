"""
Email address validation utilities.

Provides centralized email validation logic to ensure consistency across
email server, simulation gateway, and other components.
"""

from typing import Iterable


def validate_email_address(email: str, *, normalize: bool = True) -> str:
    """
    Validate and optionally normalize an email address.

    Args:
        email: Email address to validate
        normalize: Whether to normalize (strip + lowercase) the address

    Returns:
        Validated (and optionally normalized) email address

    Raises:
        ValueError: If email is invalid
    """
    if not isinstance(email, str):
        raise ValueError(f"Email must be a string, got {type(email).__name__}")

    cleaned = email.strip()
    if normalize:
        cleaned = cleaned.lower()

    # Basic validation: must have @ and not be at edges
    if not cleaned:
        raise ValueError("Email address cannot be empty")
    if "@" not in cleaned:
        raise ValueError(f"Invalid email address (missing @): {email}")
    if cleaned.startswith("@"):
        raise ValueError(f"Invalid email address (starts with @): {email}")
    if cleaned.endswith("@"):
        raise ValueError(f"Invalid email address (ends with @): {email}")

    return cleaned


def filter_valid_emails(addresses: Iterable[str], *, normalize: bool = True, strict: bool = False) -> list[str]:
    """
    Filter a list of email addresses, returning only valid ones.

    Args:
        addresses: Iterable of email addresses to filter
        normalize: Whether to normalize valid addresses
        strict: If True, raise ValueError on any invalid address. If False, skip invalid addresses.

    Returns:
        List of valid (and optionally normalized) email addresses

    Raises:
        ValueError: If strict=True and any address is invalid
    """
    valid = []
    for addr in addresses:
        try:
            validated = validate_email_address(addr, normalize=normalize)
            valid.append(validated)
        except ValueError as exc:
            if strict:
                raise ValueError(f"Invalid email in list: {addr}") from exc
            # Skip invalid addresses in non-strict mode
            continue

    return valid


def is_valid_email(email: str) -> bool:
    """
    Check if an email address is valid without raising exceptions.

    Args:
        email: Email address to check

    Returns:
        True if valid, False otherwise
    """
    try:
        validate_email_address(email, normalize=False)
        return True
    except ValueError:
        return False
