import base64
import json
import time
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes

from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from core.models import ModuleStatus
from meetings.models import Meeting, MeetingStatus, ParticipantRole
from meetings.services import (
    generate_jaas_jwt, get_jaas_status, validate_jaas_credentials, _b64url_encode
)

User = get_user_model()


class JaaSIntegrationAndSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Generate test RSA key pair once for the test suite
        cls.rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_key_pem = cls.rsa_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        cls.public_key = cls.rsa_key.public_key()

        # Users
        cls.host_user = User.objects.create_user(
            email='host@aetherspace.dev',
            username='hostuser',
            password='TestPassword123!',
            first_name='Host',
            last_name='User'
        )
        cls.attendee_user = User.objects.create_user(
            email='attendee@aetherspace.dev',
            username='attendeeuser',
            password='TestPassword123!',
            first_name='Attendee',
            last_name='User'
        )
        cls.outsider_user = User.objects.create_user(
            email='outsider@aetherspace.dev',
            username='outsideruser',
            password='TestPassword123!',
            first_name='Outsider',
            last_name='User'
        )

        # Workspace
        cls.workspace = Workspace.objects.create(
            name='JaaS Project Space',
            slug='jaas-project-space',
            owner=cls.host_user
        )

        # Memberships
        WorkspaceMembership.objects.create(
            workspace=cls.workspace,
            user=cls.host_user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=cls.workspace,
            user=cls.attendee_user,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # Ensure ModuleStatus is available by default
        ModuleStatus.objects.update_or_create(
            module_key='meetings',
            defaults={'status': ModuleStatus.STATUS_AVAILABLE}
        )

        # Meeting
        cls.meeting = Meeting.objects.create(
            workspace=cls.workspace,
            meeting_code='meet-jaas-test',
            title='JaaS Architecture Sync',
            host=cls.host_user,
            status=MeetingStatus.LIVE
        )

    def decode_token_unverified(self, token):
        parts = token.split('.')
        self.assertEqual(len(parts), 3, "JWT must contain header, payload, signature")
        def b64url_decode(s):
            padding_needed = len(s) % 4
            if padding_needed:
                s += '=' * (4 - padding_needed)
            return base64.urlsafe_b64decode(s.encode('utf-8'))

        header = json.loads(b64url_decode(parts[0]).decode('utf-8'))
        payload = json.loads(b64url_decode(parts[1]).decode('utf-8'))
        signature = b64url_decode(parts[2])
        return header, payload, signature, f"{parts[0]}.{parts[1]}".encode('utf-8')

    def test_jaas_unconfigured_returns_none(self):
        """When JAAS_APP_ID is empty, generate_jaas_jwt returns (None, None)."""
        with override_settings(JAAS_APP_ID=''):
            token, err = generate_jaas_jwt(self.meeting, self.host_user)
            self.assertIsNone(token)
            self.assertIsNone(err)
            status = get_jaas_status()
            self.assertFalse(status['is_configured'])

    def test_jaas_missing_api_key_id_returns_error(self):
        """When JAAS_APP_ID is present but JAAS_API_KEY_ID is missing, return error without falling back."""
        with override_settings(JAAS_APP_ID='vpaas-magic-cookie-test', JAAS_API_KEY_ID=''):
            token, err = generate_jaas_jwt(self.meeting, self.host_user)
            self.assertIsNone(token)
            self.assertIn("JAAS_API_KEY_ID is missing", err)

    def test_jaas_placeholder_api_key_id_returns_error(self):
        """When JAAS_API_KEY_ID has placeholder text, detect and report error."""
        with override_settings(
            JAAS_APP_ID='vpaas-magic-cookie-test',
            JAAS_API_KEY_ID='vpaas-magic-cookie-test/your_api_key_id',
            JAAS_PRIVATE_KEY=self.private_key_pem
        ):
            token, err = generate_jaas_jwt(self.meeting, self.host_user)
            self.assertIsNone(token)
            self.assertIn("placeholder value", err)

    def test_validate_jaas_credentials_helper(self):
        """Test validate_jaas_credentials utility across different configurations."""
        # Unconfigured
        with override_settings(JAAS_APP_ID=''):
            is_valid, err = validate_jaas_credentials()
            self.assertTrue(is_valid)
            self.assertIsNone(err)

        # Placeholder
        with override_settings(
            JAAS_APP_ID='vpaas-magic-cookie-test',
            JAAS_API_KEY_ID='vpaas-magic-cookie-test/replace_me',
            JAAS_PRIVATE_KEY=self.private_key_pem
        ):
            is_valid, err = validate_jaas_credentials()
            self.assertFalse(is_valid)
            self.assertIn("placeholder", err)

        # Fully valid
        with override_settings(
            JAAS_APP_ID='vpaas-magic-cookie-test',
            JAAS_API_KEY_ID='vpaas-magic-cookie-test/real-key-uuid',
            JAAS_PRIVATE_KEY=self.private_key_pem
        ):
            is_valid, err = validate_jaas_credentials()
            self.assertTrue(is_valid)
            self.assertIsNone(err)

    def test_jaas_missing_private_key_returns_error(self):
        """When JaaS keys are absent, return explicit authentication failure."""
        with override_settings(
            JAAS_APP_ID='vpaas-magic-cookie-test',
            JAAS_API_KEY_ID='test-key-id',
            JAAS_PRIVATE_KEY='',
            JAAS_PRIVATE_KEY_PATH=''
        ):
            token, err = generate_jaas_jwt(self.meeting, self.host_user)
            self.assertIsNone(token)
            self.assertIn("private key is not configured", err)

    def test_jaas_corrupt_private_key_returns_error(self):
        """When private key PEM is corrupted, error is reported gracefully."""
        with override_settings(
            JAAS_APP_ID='vpaas-magic-cookie-test',
            JAAS_API_KEY_ID='test-key-id',
            JAAS_PRIVATE_KEY='-----BEGIN PRIVATE KEY-----\nNOT_A_VALID_KEY\n-----END PRIVATE KEY-----'
        ):
            token, err = generate_jaas_jwt(self.meeting, self.host_user)
            self.assertIsNone(token)
            self.assertIn("Invalid or unparseable RSA private key", err)

    def test_jaas_valid_jwt_header_payload_and_signature(self):
        """Generate valid JaaS JWT and verify official claims, audience, issuer, and RS256 signature."""
        app_id = 'vpaas-magic-cookie-aether-test'
        key_id = 'key-uuid-1234'
        with override_settings(
            JAAS_APP_ID=app_id,
            JAAS_API_KEY_ID=key_id,
            JAAS_PRIVATE_KEY=self.private_key_pem,
            JAAS_JWT_EXP_SECONDS=3600
        ):
            token, err = generate_jaas_jwt(self.meeting, self.host_user, is_moderator=True)
            self.assertIsNone(err)
            self.assertIsNotNone(token)

            header, payload, signature, signed_bytes = self.decode_token_unverified(token)

            # Header verification
            self.assertEqual(header['alg'], 'RS256')
            self.assertEqual(header['typ'], 'JWT')
            self.assertEqual(header['kid'], f"{app_id}/{key_id}")

            # Payload claims verification
            self.assertEqual(payload['aud'], 'jitsi')
            self.assertEqual(payload['iss'], 'chat')
            self.assertEqual(payload['sub'], app_id)
            self.assertEqual(payload['room'], self.meeting.jitsi_room_name)
            self.assertTrue(payload['exp'] > payload['nbf'])
            self.assertEqual(payload['exp'] - payload['nbf'], 3610)  # 3600 + 10s leeway

            # User & Feature claims
            user_claims = payload['context']['user']
            self.assertEqual(user_claims['id'], str(self.host_user.id))
            self.assertEqual(user_claims['name'], 'Host User')
            self.assertEqual(user_claims['email'], self.host_user.email)
            self.assertTrue(user_claims['moderator'])

            features = payload['context']['features']
            self.assertTrue(features['recording'])
            self.assertTrue(features['livestreaming'])
            self.assertTrue(features['file-upload'])

            # Cryptographic signature verification using public key
            self.public_key.verify(
                signature,
                signed_bytes,
                padding.PKCS1v15(),
                hashes.SHA256()
            )

    def test_jaas_attendee_has_no_moderator_rights(self):
        """Standard contributors receive moderator=False and disabled recording/livestreaming."""
        app_id = 'vpaas-magic-cookie-aether-test'
        with override_settings(
            JAAS_APP_ID=app_id,
            JAAS_API_KEY_ID='test-key',
            JAAS_PRIVATE_KEY=self.private_key_pem
        ):
            token, err = generate_jaas_jwt(self.meeting, self.attendee_user, is_moderator=False)
            self.assertIsNone(err)
            _, payload, _, _ = self.decode_token_unverified(token)
            self.assertFalse(payload['context']['user']['moderator'])
            self.assertFalse(payload['context']['features']['recording'])
            self.assertFalse(payload['context']['features']['livestreaming'])

    def test_meeting_room_view_with_jaas_enabled(self):
        """Room view passes JWT, prefixes JaaS room, and includes companion workspace nav links."""
        app_id = 'vpaas-magic-cookie-aether-test'
        self.client.force_login(self.host_user)
        with override_settings(
            JAAS_APP_ID=app_id,
            JAAS_API_KEY_ID='test-key',
            JAAS_PRIVATE_KEY=self.private_key_pem
        ):
            url = reverse('meetings:meeting_room', kwargs={
                'slug': self.workspace.slug,
                'meeting_code': self.meeting.meeting_code
            })
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.context['is_jaas'])
            self.assertIsNotNone(resp.context['jaas_jwt'])
            self.assertIsNone(resp.context['jaas_error'])
            self.assertEqual(resp.context['jitsi_domain'], '8x8.vc')
            self.assertEqual(resp.context['jitsi_room_name'], f"{app_id}/{self.meeting.jitsi_room_name}")

            # Verify companion navigation links exist
            workspace_nav = resp.context['workspace_nav']
            self.assertIn('dashboard', workspace_nav)
            self.assertIn('tasks', workspace_nav)
            self.assertIn('calendar', workspace_nav)
            self.assertIn('chat', workspace_nav)
            self.assertContains(resp, 'Companion Workspace Navigation')
            self.assertContains(resp, 'Pop-out')

    def test_meeting_room_view_with_jaas_error_no_fallback(self):
        """When JaaS is configured but credentials fail, show error and do not load public Jitsi."""
        self.client.force_login(self.host_user)
        with override_settings(
            JAAS_APP_ID='vpaas-magic-cookie-aether-test',
            JAAS_API_KEY_ID='test-key',
            JAAS_PRIVATE_KEY='INVALID_KEY'
        ):
            url = reverse('meetings:meeting_room', kwargs={
                'slug': self.workspace.slug,
                'meeting_code': self.meeting.meeting_code
            })
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertIsNotNone(resp.context['jaas_error'])
            self.assertIsNone(resp.context['jaas_jwt'])
            self.assertContains(resp, '8×8 JaaS Service Configuration Error')

    def test_meeting_maintenance_gate_blocks_room_view(self):
        """Coming Soon / Maintenance gate returns 503 Service Unavailable."""
        ModuleStatus.objects.filter(module_key='meetings').update(status=ModuleStatus.STATUS_COMING_SOON)
        self.client.force_login(self.attendee_user)
        url = reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 503)

        # Restore
        ModuleStatus.objects.filter(module_key='meetings').update(status=ModuleStatus.STATUS_AVAILABLE)

    def test_workspace_isolation_blocks_outsider(self):
        """Non-members are denied access to meeting room."""
        self.client.force_login(self.outsider_user)
        url = reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)
