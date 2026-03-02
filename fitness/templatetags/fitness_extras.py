"""Custom template tags for fitness app."""
from django import template

register = template.Library()


@register.filter
def get_item(d, key):
    """Return d[key] or None. Use for dict lookup with variable key in templates."""
    if d is None:
        return None
    return d.get(key)
