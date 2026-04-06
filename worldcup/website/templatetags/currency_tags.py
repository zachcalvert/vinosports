from django import template

register = template.Library()

CURRENCY_CONFIG = {
    "USD": {"symbol": "$"},
    "GBP": {"symbol": "£"},
    "EUR": {"symbol": "€"},
}


def format_currency(value, currency_code="USD", decimals=2):
    """Format a numeric value with the given currency symbol."""
    config = CURRENCY_CONFIG.get(currency_code, CURRENCY_CONFIG["USD"])
    if decimals == 0:
        return f"{config['symbol']}{round(float(value)):,d}"
    return f"{config['symbol']}{float(value):,.2f}"


def get_currency_symbol(user):
    """Get the currency symbol for a user."""
    code = getattr(user, "currency", "USD") if user else "USD"
    return CURRENCY_CONFIG.get(code, CURRENCY_CONFIG["USD"])["symbol"]


@register.filter
def currency(value, user):
    """Usage: {{ amount|currency:user }}"""
    if value is None or value == "":
        return ""
    code = getattr(user, "currency", "USD") if user else "USD"
    return format_currency(value, code)


@register.filter
def currency_rounded(value, user):
    """Round to the nearest whole unit. Usage: {{ amount|currency_rounded:user }}"""
    if value is None or value == "":
        return ""
    code = getattr(user, "currency", "USD") if user else "USD"
    return format_currency(value, code, decimals=0)


@register.simple_tag
def currency_symbol(user):
    """Returns just the symbol: $, £, €"""
    return get_currency_symbol(user)


@register.filter
def negate(value):
    """Negate a numeric value. Usage: {{ value|negate }}"""
    try:
        return -value
    except (TypeError, ValueError):
        return value
