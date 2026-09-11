from django import template

register = template.Library()


@register.filter(name='get_dict_item')
def get_dict_item(dictionary, key):
    """Retrieve value from dictionary by key."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter(name='slice_remaining')
def slice_remaining(items, offset):
    """Return count of items beyond offset (for +X more chips)."""
    if items and len(items) > offset:
        return len(items) - offset
    return 0
