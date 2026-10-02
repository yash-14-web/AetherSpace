from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus

User = get_user_model()


class CoreViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"
        self.user = User.objects.create_user(
            email="nav.tester@aetherspace.dev",
            password=self.password,
            full_name="Nav Tester"
        )
        self.workspace = Workspace.objects.create(
            name="Nav Workspace",
            slug="nav-workspace",
            description="Testing navigation shell",
            owner=self.user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

    def test_landing_page_renders_successfully(self):
        url = reverse('core:landing')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AetherSpace")
        self.assertContains(response, "Your Team.")
        self.assertContains(response, "Get Started Free")

    def test_navigation_routes_require_authentication(self):
        destinations = [
            'core:calendar',
            'core:files',
            'core:meetings',
            'core:chat',
            'core:time_tracking',
            'core:notifications',
            'core:profile',
        ]
        for dest in destinations:
            url = reverse(dest)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, f"{dest} should redirect unauthenticated user")
            self.assertIn('/auth/login/', response.url)

    def test_authenticated_user_can_access_navigation_destinations(self):
        self.client.login(email="nav.tester@aetherspace.dev", password=self.password)
        destinations = [
            ('core:calendar', 'Calendar & Agenda'),
            ('core:files', 'Files & Storage'),
            ('core:meetings', 'Meet Hub'),
            ('core:chat', 'Team Chat & Channels'),
            ('core:time_tracking', 'Time Tracking & Logs'),
            ('core:notifications', 'Notifications Center'),
            ('core:profile', 'User Profile & Preferences'),
        ]
        for dest, expected_title in destinations:
            url = reverse(dest)
            response = self.client.get(url, follow=True)
            self.assertEqual(response.status_code, 200, f"Failed accessing {dest}")

    def test_workspace_project_details_and_chat_access(self):
        self.client.login(email="nav.tester@aetherspace.dev", password=self.password)
        
        # Project Details
        proj_url = reverse('workspaces:project_details', kwargs={'slug': self.workspace.slug})
        response = self.client.get(proj_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Project Details")
        self.assertContains(response, "Tech Stack")

        # Workspace Chat
        chat_url = reverse('workspaces:workspace_chat', kwargs={'slug': self.workspace.slug})
        response = self.client.get(chat_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Team Chat")

    def test_all_http_error_pages_and_copies(self):
        """Test all 8 required error pages + network error for status, headers, and UI copy."""
        error_expectations = [
            (400, 'core:test_400', "400", "Invalid Request", "The request could not be processed due to invalid parameters."),
            (401, 'core:test_401', "401", "Authentication Required", "Please sign in with your AetherSpace credentials"),
            (403, 'core:test_403', "403", "Access Restricted", "You don't have permission to access this page."),
            (404, 'core:test_404', "404", "Page Not Found", "The page you're looking for doesn't exist or may have been moved."),
            (408, 'core:test_408', "408", "Request Timed Out", "The request took too long to complete."),
            (429, 'core:test_429', "429", "Too Many Requests", "You've made too many requests in a short period."),
            (500, 'core:test_500', "500", "Something Went Wrong", "Something went wrong on our end."),
            (503, 'core:test_503', "503", "Service Temporarily Unavailable", "AetherSpace is temporarily unavailable."),
            (503, 'core:test_network', "Offline", "Connection Lost", "We couldn't connect to AetherSpace."),
        ]
        for expected_code, route_name, code_text, headline, copy_snippet in error_expectations:
            url = reverse(route_name)
            response = self.client.get(url)
            self.assertEqual(response.status_code, expected_code, f"Route {route_name} failed code check")
            self.assertContains(response, code_text, status_code=expected_code)
            self.assertContains(response, headline, status_code=expected_code)
            self.assertContains(response, copy_snippet, status_code=expected_code)
            # Ensure theme and support footer exist
            self.assertContains(response, "Contact support", status_code=expected_code)

    def test_429_rate_limit_header_present(self):
        """Verify 429 response includes the required Retry-After HTTP header."""
        url = reverse('core:test_429')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.has_header('Retry-After'))
        self.assertEqual(response['Retry-After'], '60')

    def test_500_error_sanitization_and_correlation_id(self):
        """Verify 500 error outputs safe correlation ID and NEVER exposes tracebacks or secrets."""
        url = reverse('core:test_500')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "ERR-500-", status_code=500)
        content = response.content.decode('utf-8')
        self.assertNotIn("Traceback (most recent call last)", content)
        self.assertNotIn("django.db.backends", content)
        self.assertNotIn("SECRET_KEY", content)

    def test_ajax_error_responses_receive_json(self):
        """Verify AJAX / API requests receive clean structured JSON instead of HTML on error codes."""
        for route_name, expected_code in [
            ('core:test_400', 400),
            ('core:test_401', 401),
            ('core:test_404', 404),
            ('core:test_408', 408),
            ('core:test_429', 429),
            ('core:test_500', 500),
            ('core:test_503', 503),
        ]:
            url = reverse(route_name)
            response = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(response.status_code, expected_code)
            self.assertEqual(response['Content-Type'], 'application/json')
            data = response.json()
            self.assertIn('error', data)
            self.assertEqual(data['status_code'], expected_code)

    def test_403_request_access_workflow(self):
        """
        Verify that 403 shows Request Access for authenticated users on existing workspaces,
        and dispatches a WorkspaceAccessRequest properly.
        """
        from workspaces.models import Workspace, WorkspaceAccessRequest, AccessRequestStatus
        other_user = get_user_model().objects.create_user(
            email="outside.user@aetherspace.dev",
            password=self.password,
            first_name="Outside",
            last_name="User",
            role="CONTRIBUTOR"
        )
        self.client.login(email="outside.user@aetherspace.dev", password=self.password)

        # 1. Access 403 for a protected workspace
        url = f"/workspaces/{self.workspace.slug}/settings/"
        response = self.client.get(url)
        # Should be 403 or redirect
        if response.status_code == 403:
            self.assertContains(response, "Request Access", status_code=403)

        # 2. Directly verify Request Access POST workflow creates access request
        req_url = reverse('workspaces:request_access', kwargs={'slug': self.workspace.slug})
        post_response = self.client.post(
            req_url,
            {'message': 'I need access to contribute to UI tasks.'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertIn(post_response.status_code, [200, 302])
        self.assertTrue(
            WorkspaceAccessRequest.objects.filter(
                workspace=self.workspace,
                user=other_user,
                status=AccessRequestStatus.PENDING
            ).exists()
        )

    def test_errors_showcase_page_renders(self):
        """Verify the Error & Empty States Showcase page renders successfully."""
        url = reverse('core:errors_showcase')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Error & Empty States System")
        self.assertContains(response, "Component-Level Error States")
        self.assertContains(response, "File & Calendar Micro-States")

    def test_real_403_renders_designed_ui_with_permission_reason(self):
        """
        Verify that when a view returns an HttpResponseForbidden with custom plain text
        (e.g. workspace creation restriction for Contributors), the middleware converts it
        into the designed AetherSpace 403 page preserving the exact reason.
        """
        contributor_user = User.objects.create_user(
            email="contributor.tester@aetherspace.dev",
            password=self.password,
            full_name="Contributor Tester",
            role="CONTRIBUTOR"
        )
        self.client.login(email="contributor.tester@aetherspace.dev", password=self.password)

        create_ws_url = reverse('workspaces:create')
        # Attempting GET to create workspace as a CONTRIBUTOR
        response = self.client.get(create_ws_url)

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "<!DOCTYPE html>", status_code=403)
        self.assertContains(response, "Access Restricted", status_code=403)
        self.assertContains(response, "Only Administrators and Managers can create workspaces.", status_code=403)
        self.assertContains(response, "403", status_code=403)

    def test_empty_states_rendered_in_tasks_and_bugs(self):
        """Verify designed vector empty states appear on zero-result queries."""
        self.client.login(email="nav.tester@aetherspace.dev", password=self.password)

        # 1. Empty Tasks in workspace
        tasks_url = reverse('tasks:task_list', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(tasks_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No Tasks Yet")
        self.assertContains(resp, "+ Create Task")

        # 2. Filtered Tasks (search query with 0 results)
        search_resp = self.client.get(tasks_url + "?q=NonExistentTask999")
        self.assertEqual(search_resp.status_code, 200)
        self.assertContains(search_resp, "No Tasks Found")
        self.assertContains(search_resp, "NonExistentTask999")
        self.assertContains(search_resp, "Clear Search")

        # 3. Empty Bugs in workspace
        bugs_url = reverse('bugs:bug_list', kwargs={'slug': self.workspace.slug})
        bug_resp = self.client.get(bugs_url)
        self.assertEqual(bug_resp.status_code, 200)
        self.assertContains(bug_resp, "No Bugs Found")
        self.assertContains(bug_resp, "All systems green")
        self.assertContains(bug_resp, "Raise Bug")

    def test_hover_card_returns_real_tagging_role(self):
        """Verify people hover card returns real tagging_role from WorkspaceMembership."""
        # Set role_tag on membership
        membership = WorkspaceMembership.objects.get(workspace=self.workspace, user=self.user)
        membership.role_tag = "Frontend"
        membership.functional_role = "UI Engineer"
        membership.save()

        self.client.login(email="nav.tester@aetherspace.dev", password=self.password)
        card_url = f"/auth/api/user-card/{self.user.id}/?workspace={self.workspace.slug}"
        resp = self.client.get(card_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['tagging_role'], "Frontend")
        self.assertEqual(data['functional_role'], "UI Engineer")
        self.assertEqual(data['designation'], "UI Engineer")
        self.assertEqual(data['workspace_name'], "Nav Workspace")
        self.assertTrue(data['is_owner'])
        self.assertEqual(data['full_name'], "Nav Tester")
        self.assertEqual(data['workspace_role'], "Admin")
        self.assertEqual(data['system_role'], "Contributor")


class ModuleMaintenanceTests(TestCase):
    """Test suite verifying global module maintenance status, server-side enforcement, and admin recovery."""

    def setUp(self):
        from core.models import ModuleStatus
        from workspaces.models import WorkspaceRole

        self.password = "Secr3tP@ssw0rd!"
        self.admin_user = User.objects.create_superuser(
            email="admin.maintenance@aetherspace.dev",
            password=self.password,
            username="admin_maintenance",
            role="ADMIN"
        )
        self.contributor = User.objects.create_user(
            email="contributor.maintenance@aetherspace.dev",
            password=self.password,
            username="contrib_maintenance",
            role="CONTRIBUTOR"
        )
        self.workspace = Workspace.objects.create(
            name="Maintenance Test Workspace",
            slug="maint-test-ws",
            owner=self.admin_user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )
        # Seed and ensure meetings is marked MAINTENANCE
        self.meet_status, _ = ModuleStatus.objects.get_or_create(
            module_key='meetings',
            defaults={
                'name': 'Meet Hub',
                'status': ModuleStatus.STATUS_MAINTENANCE,
                'public_message': 'Meet Hub is temporarily unavailable while we complete improvements.'
            }
        )
        self.meet_status.status = ModuleStatus.STATUS_MAINTENANCE
        self.meet_status.public_message = 'Meet Hub is temporarily unavailable while we complete improvements.'
        self.meet_status.save()

    def test_module_status_properties(self):
        self.assertTrue(self.meet_status.is_under_maintenance)
        self.assertFalse(self.meet_status.is_available)
        self.assertIn("Meet Hub is temporarily unavailable", self.meet_status.effective_message)

    def test_meetings_room_blocked_with_503(self):
        self.client.login(email="contributor.maintenance@aetherspace.dev", password=self.password)
        resp = self.client.get(f"/meetings/w/{self.workspace.slug}/room/meet-test-1234/")
        self.assertEqual(resp.status_code, 503)
        self.assertContains(resp, "Meet Hub", status_code=503)
        self.assertContains(resp, "Under Maintenance", status_code=503)

    def test_meetings_start_blocked_with_503(self):
        self.client.login(email="contributor.maintenance@aetherspace.dev", password=self.password)
        resp = self.client.get(f"/meetings/w/{self.workspace.slug}/start/")
        self.assertEqual(resp.status_code, 503)

    def test_meet_hub_overview_displays_maintenance_banner(self):
        self.client.login(email="contributor.maintenance@aetherspace.dev", password=self.password)
        resp = self.client.get(f"/meetings/w/{self.workspace.slug}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Meet Hub — Under Maintenance")
        self.assertContains(resp, "Meet Hub is temporarily unavailable while we complete improvements.")

    def test_admin_updates_status_to_available_restores_access(self):
        self.client.login(email="admin.maintenance@aetherspace.dev", password=self.password)
        update_url = reverse('admin_panel:update_module_status', kwargs={'module_key': 'meetings'})
        resp = self.client.post(update_url, {
            'status': 'AVAILABLE',
            'public_message': 'Meet Hub is fully operational.',
            'maintenance_explanation': 'Maintenance finished and verified.'
        })
        self.assertEqual(resp.status_code, 302)

        self.meet_status.refresh_from_db()
        self.assertEqual(self.meet_status.status, 'AVAILABLE')
        self.assertTrue(self.meet_status.is_available)


class MarkdownCentralPipelineTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
             email="markdown.tester@aetherspace.dev",
             password="SecurePassword123!",
             full_name="Markdown Tester"
         )
        self.client.force_login(self.user)

    def test_heading_rendering(self):
        from core.templatetags.rich_text import render_rich_text
        html = render_rich_text("### Sprint Agenda Topic")
        self.assertIn("<h3", html)
        self.assertIn("Sprint Agenda Topic", html)

    def test_bold_and_italic_rendering(self):
        from core.templatetags.rich_text import render_rich_text
        html = render_rich_text("**Critical Mission** and *Flexible Schedule*")
        self.assertIn("<strong>Critical Mission</strong>", html)
        self.assertIn("<em>Flexible Schedule</em>", html)

    def test_lists_rendering(self):
        from core.templatetags.rich_text import render_rich_text
        bullet_html = render_rich_text("- Feature A\n- Feature B")
        self.assertIn("<ul", bullet_html)
        self.assertIn("<li>Feature A</li>", bullet_html)

        numbered_html = render_rich_text("1. Step Alpha\n2. Step Beta")
        self.assertIn("<ol", numbered_html)
        self.assertIn("<li>Step Alpha</li>", numbered_html)

    def test_task_checkbox_rendering(self):
        from core.templatetags.rich_text import render_rich_text
        todo_html = render_rich_text("- [ ] Complete user testing")
        self.assertIn('type="checkbox"', todo_html)
        self.assertIn('disabled', todo_html)
        self.assertNotIn('checked', todo_html)
        self.assertIn("Complete user testing", todo_html)

        done_html = render_rich_text("- [x] Ship release v2.0")
        self.assertIn('type="checkbox"', done_html)
        self.assertIn('checked', done_html)
        self.assertIn('disabled', done_html)
        self.assertIn("Ship release v2.0", done_html)

    def test_quote_and_code_rendering(self):
        from core.templatetags.rich_text import render_rich_text
        quote_html = render_rich_text("> High quality code is paramount")
        self.assertIn("<blockquote", quote_html)
        self.assertIn("High quality code is paramount", quote_html)

        code_html = render_rich_text("Use `python manage.py test` to verify")
        self.assertIn("<code>python manage.py test</code>", code_html)

    def test_sanitization_prevents_xss_and_injection(self):
        from core.templatetags.rich_text import render_rich_text
        malicious = "<script>alert('pwned')</script>\n<img src=x onerror=alert(1)>\n<a href=\"javascript:alert('xss')\">Click</a>"
        safe_html = render_rich_text(malicious)
        self.assertNotIn("<script>", safe_html)
        self.assertNotIn("onerror", safe_html)
        self.assertNotIn("javascript:", safe_html)

    def test_markdown_preview_api_endpoint(self):
        import json
        url = reverse('core:markdown_preview')
        payload = {
            'markdown': '### Live Agenda Preview\n- [ ] Action item 1\n**Urgent**'
        }
        resp = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('status'), 'ok')
        html = data.get('html', '')
        self.assertIn('<h3', html)
        self.assertIn('Live Agenda Preview', html)
        self.assertIn('type="checkbox"', html)
        self.assertIn('<strong>Urgent</strong>', html)



