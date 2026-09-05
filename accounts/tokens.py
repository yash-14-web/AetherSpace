from django.contrib.auth.tokens import PasswordResetTokenGenerator


class AccountVerificationTokenGenerator(PasswordResetTokenGenerator):
    """
    Generates a secure cryptographic one-time token for account email verification.
    The hash includes user pk, timestamp, and verification status so the token is invalidated
    as soon as is_verified transitions to True.
    """
    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{timestamp}{user.is_verified}{user.is_active}"


account_verification_token = AccountVerificationTokenGenerator()
