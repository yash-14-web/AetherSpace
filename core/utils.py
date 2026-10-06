"""
AetherSpace Core Security Utilities.
Provides centralized URL safety validation and open-redirect hardening.
"""

from urllib.parse import urlparse, unquote
from django.shortcuts import redirect, resolve_url
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect_target(request, target, fallback=None):
    """
    Validates a candidate redirect target URL to eliminate Open Redirect vulnerabilities (py/url-redirection).
    Ensures that any destination is strictly bounded to the current application host and safe schemes.

    Args:
        request: HttpRequest instance providing host and scheme context.
        target: The candidate redirect URL (str, e.g. from 'next', 'HTTP_REFERER').
        fallback: Safe internal URL or view name if target is missing, external, or malformed.

    Returns:
        A validated safe internal redirect URL string.
    """
    # Determine the safe fallback URL string
    if fallback:
        try:
            safe_fallback = resolve_url(fallback)
        except Exception:
            safe_fallback = str(fallback)
    else:
        safe_fallback = "/"

    if not target or not isinstance(target, str):
        return safe_fallback

    clean_target = target.strip()
    if not clean_target:
        return safe_fallback

    # Reject control characters (prevent CRLF injection attacks)
    if "\r" in clean_target or "\n" in clean_target or "\0" in clean_target:
        return safe_fallback

    # Reject backslash variations and protocol-relative variations
    # e.g., \evil.example, /\evil.example, \\evil.example, https:\evil.example
    if clean_target.startswith("\\") or clean_target.startswith("/\\"):
        return safe_fallback

    # Unquote and check for obfuscated backslashes or protocol-relative schemes
    unquoted = unquote(clean_target).strip()
    double_unquoted = unquote(unquoted).strip()
    for check_str in (unquoted, double_unquoted):
        if (
            check_str.startswith("//")
            or check_str.startswith("\\")
            or check_str.startswith("/\\")
            or "\\" in check_str
        ):
            return safe_fallback

    # Check for dangerous schemes explicitly (javascript:, data:, vbscript:, file:)
    lower_target = clean_target.lower()
    for dangerous in ("javascript:", "data:", "vbscript:", "file:"):
        if lower_target.startswith(dangerous):
            return safe_fallback

    # Resolve allowed hosts dynamically from current request
    try:
        allowed_hosts = {request.get_host()}
    except Exception:
        return safe_fallback

    # Determine whether HTTPS is strictly required based on the incoming request
    require_https = request.is_secure()

    # Validate using Django's trusted url_has_allowed_host_and_scheme
    if url_has_allowed_host_and_scheme(
        url=clean_target,
        allowed_hosts=allowed_hosts,
        require_https=require_https
    ):
        return clean_target

    return safe_fallback


def safe_redirect(request, target, fallback=None, **redirect_kwargs):
    """
    Validates target using safe_redirect_target and returns an HttpResponseRedirect.
    """
    validated_url = safe_redirect_target(request, target, fallback=fallback)
    return redirect(validated_url, **redirect_kwargs)


def is_domain_match(hostname: str, allowed_domains: tuple[str, ...] | list[str] | set[str]) -> bool:
    """
    Authoritative domain check. Matches exact domain or valid subdomain suffix.
    Prevents incomplete URL substring sanitization (CWE-20 / py/incomplete-url-substring-sanitization)
    such as matching 'evil-github.com' or 'fakebox.com'.
    """
    if not hostname or not isinstance(hostname, str):
        return False
    norm_host = hostname.strip().lower().rstrip('.')
    for domain in allowed_domains:
        norm_domain = domain.strip().lower().rstrip('.')
        if norm_host == norm_domain or norm_host.endswith('.' + norm_domain):
            return True
    return False


def validate_external_url(url: str, allowed_schemes: tuple[str, ...] = ('http', 'https')) -> tuple[bool, str, str | None]:
    """
    Validates an external URL for storage, external linking, and launch.
    Ensures safe schemes, authoritative hostname parsing, no backslashes, control characters, or dangerous schemes.

    Returns:
        (is_valid: bool, cleaned_url: str, error_message: str | None)
    """
    if not url or not isinstance(url, str):
        return False, '', "URL is required."

    clean_url = url.strip()
    if not clean_url:
        return False, '', "URL cannot be empty."

    # Check for CRLF / null byte injection
    if '\r' in clean_url or '\n' in clean_url or '\0' in clean_url:
        return False, '', "URL contains illegal control characters."

    # Reject backslash variations
    if '\\' in clean_url:
        return False, '', "URL cannot contain backslashes."

    # Check unquoted representation for obfuscated backslashes or protocol-relative prefixes
    unquoted = unquote(clean_url).strip()
    double_unquoted = unquote(unquoted).strip()
    for check_str in (unquoted, double_unquoted):
        if '\\' in check_str or check_str.startswith('//') or check_str.startswith('/\\'):
            return False, '', "URL contains obfuscated or unsafe path characters."

    # Reject dangerous schemes explicitly
    lower_url = clean_url.lower()
    for dangerous in ("javascript:", "data:", "vbscript:", "file:", "about:", "blob:"):
        if lower_url.startswith(dangerous):
            return False, '', f"The '{dangerous.rstrip(':')}' scheme is not permitted."

    try:
        parsed = urlparse(clean_url)
    except Exception:
        return False, '', "Malformed URL."

    if parsed.scheme.lower() not in allowed_schemes:
        allowed_list = ", ".join(s.upper() for s in allowed_schemes)
        return False, '', f"URL must use an allowed scheme ({allowed_list})."

    # Hostname must be present and valid
    hostname = parsed.hostname
    if not hostname:
        return False, '', "URL must contain a valid domain name."

    # Enforce basic hostname length & characters (RFC 1035)
    if len(hostname) > 253 or ' ' in hostname:
        return False, '', "Invalid domain name in URL."

    # Verify port if provided
    try:
        if parsed.port is not None and not (1 <= parsed.port <= 65535):
            return False, '', "Invalid port number in URL."
    except ValueError:
        return False, '', "Invalid port number in URL."

    return True, clean_url, None


def is_safe_external_url(url: str, allowed_schemes: tuple[str, ...] = ('http', 'https')) -> bool:
    """Returns True if the URL passes validate_external_url."""
    is_valid, _, _ = validate_external_url(url, allowed_schemes=allowed_schemes)
    return is_valid


def validate_image_url(url: str) -> tuple[bool, str, str | None]:
    """
    Validates external image URLs (avatars, banners, logos).
    Supports http/https schemes, preset identifiers, and local /media/ paths.
    Automatically normalizes domain-only strings to https:// if valid.
    Rejects dangerous schemes (javascript:, data:, file:), backslashes, control characters.
    """
    if not url or not isinstance(url, str):
        return False, '', "Image URL is required."

    clean_url = url.strip()
    if not clean_url:
        return False, '', "Image URL cannot be empty."

    # Check for preset or media
    if clean_url.startswith('preset:') or clean_url.startswith('/media/'):
        return True, clean_url, None

    if '\r' in clean_url or '\n' in clean_url or '\0' in clean_url or '\\' in clean_url:
        return False, '', "URL contains invalid or dangerous characters."

    lower_url = clean_url.lower()
    for dangerous in ("javascript:", "data:", "vbscript:", "file:", "about:", "blob:"):
        if lower_url.startswith(dangerous):
            return False, '', "Dangerous URL scheme is not allowed."

    try:
        parsed = urlparse(clean_url)
    except Exception:
        return False, '', "Malformed URL."

    # If no scheme was provided, e.g. "example.com/avatar.jpg"
    if not parsed.scheme:
        clean_url = 'https://' + clean_url
        try:
            parsed = urlparse(clean_url)
        except Exception:
            return False, '', "Malformed URL."

    if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname:
        return False, '', "Please enter a valid HTTP or HTTPS image URL."

    return True, clean_url, None
