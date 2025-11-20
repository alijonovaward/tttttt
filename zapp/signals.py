# zapp/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.conf import settings
from .models import UserProfile, Organization, Prompt
from .services.amocrm_service import fetch_and_create_managers


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created and not hasattr(instance, "profile"):
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=Organization)
def create_default_prompt_and_managers_for_organization(sender, instance, created, **kwargs):
    """
    При создании новой организации:
    - создается дефолтный промпт
    - создаются менеджеры из amoCRM
    """
    if created and not instance.prompts.exists():
        Prompt.objects.create(
            organization=instance,
            name="Промпт по умолчанию",
            description=settings.DEFAULT_ORGANIZATION_PROMPT.strip()
        )
    fetch_and_create_managers(instance)