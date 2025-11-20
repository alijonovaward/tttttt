from django import template

register = template.Library()

@register.filter
def dict_get(dictionary, key):
    return dictionary.get(key, '')

@register.filter
def div(value, arg):
    try:
        return (value / arg) * 100
    except (ZeroDivisionError, TypeError):
        return 0