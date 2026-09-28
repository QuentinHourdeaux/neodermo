"""One email identity policy for provisioning and future HTTP operations."""

from email_validator import validate_email


def normalize_email(value: str) -> str:
    """Validate syntax and apply a case-insensitive application identity policy.

    Use ASCII mailbox names and IDNA domains for local SMTP compatibility.
    DNS checks are deliberately disabled; trusted local provisioning confirms
    the mailbox. Do not collapse provider-specific dots or plus suffixes.
    """
    try:
        if not isinstance(value, str) or len(value.encode("utf-8")) > 1024:
            raise ValueError
        normalized = validate_email(
            value.strip(), check_deliverability=False, allow_smtputf8=False, strict=True
        ).ascii_email.lower()
        normalized = validate_email(
            normalized, check_deliverability=False, allow_smtputf8=False, strict=True
        ).ascii_email
        if len(normalized.encode("utf-8")) > 254:
            raise ValueError
    except ValueError:
        raise ValueError("Enter a valid email address within the length limit.") from None
    return normalized
