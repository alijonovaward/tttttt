# your_app/templatetags/user_tags.py
from django import template

register = template.Library()

@register.filter
def is_admin_or_super(user):
    profile = getattr(user, "profile", None)
    return profile and profile.role in ("admin", "superadmin")

@register.filter
def is_admin_or_super_or_user(user):
    profile = getattr(user, "profile", None)
    return profile and profile.role in ("admin", "superadmin", "user")