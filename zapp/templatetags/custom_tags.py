# zapp/templatetags/custom_tags.py
from django import template

register = template.Library()

@register.filter
def split(value, delimiter=","):
    return value.split(delimiter)

@register.filter
def get_value(d, key):
    if isinstance(d, dict):
        return d.get(key, "")
    return getattr(d, key, "")


@register.filter
def get_query_param(get, key):
    return get.get(key, "")


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None