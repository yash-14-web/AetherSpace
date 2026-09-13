from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


class ContributorIdBackend(ModelBackend):
    """
    Authoritative authentication backend for AetherSpace.
    Authenticates primarily using Contributor ID (format #####C, e.g. 26457C) + Password.
    Also supports email + password for staff/system fallback.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        login_identifier = username or kwargs.get('contributor_id') or kwargs.get('email')
        if not login_identifier or not password:
            return None

        clean_id = str(login_identifier).strip()

        # 1. Primary lookup: Contributor ID (case-insensitive)
        user = User.objects.filter(contributor_id__iexact=clean_id).first()

        # 2. Secondary fallback lookup: Email (for superusers or administrative tools)
        if not user and '@' in clean_id:
            user = User.objects.filter(email__iexact=clean_id).first()

        if user and user.check_password(password):
            return user

        return None
