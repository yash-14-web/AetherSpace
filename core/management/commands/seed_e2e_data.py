from django.core.management.base import BaseCommand
from accounts.models import User, UserRole
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus


class Command(BaseCommand):
    help = "Seed database with standardized users and workspaces for E2E Playwright tests"

    def handle(self, *args, **options):
        self.stdout.write("Seeding E2E test data...")

        # 1. Admin user
        admin_user, _ = User.objects.get_or_create(
            email="admin@aetherspace.dev",
            defaults={
                "full_name": "Admin User",
                "role": UserRole.ADMIN,
                "is_verified": True,
                "is_staff": True,
            }
        )
        admin_user.set_password("AdminPassword123!")
        admin_user.is_verified = True
        admin_user.save()
        self.stdout.write(f"  - Admin: {admin_user.email}")

        # 2. Contributor user (Alex)
        alex_user, _ = User.objects.get_or_create(
            email="alex@aetherspace.dev",
            defaults={
                "full_name": "Alex Contributor",
                "role": UserRole.CONTRIBUTOR,
                "is_verified": True,
            }
        )
        alex_user.set_password("SecurePassword123!")
        alex_user.is_verified = True
        alex_user.save()
        self.stdout.write(f"  - Contributor: {alex_user.email}")

        # 3. Standard Workspace: Smart Classroom
        ws, _ = Workspace.objects.get_or_create(
            slug="smart-classroom",
            defaults={
                "name": "Smart Classroom",
                "description": "AI-driven classroom workspace for educational workflows.",
                "owner": admin_user,
            }
        )
        WorkspaceMembership.objects.get_or_create(
            workspace=ws,
            user=admin_user,
            defaults={
                "role": WorkspaceRole.ADMIN,
                "status": MembershipStatus.ACTIVE,
            }
        )
        self.stdout.write(f"  - Workspace: {ws.name} ({ws.slug})")

        # 4. Restricted Private Workspace (for 403 test)
        r_ws, _ = Workspace.objects.get_or_create(
            slug="restricted-private-ws",
            defaults={
                "name": "Restricted Private WS",
                "description": "Confidential internal workspace for administrators.",
                "owner": admin_user,
            }
        )
        self.stdout.write(f"  - Restricted Workspace: {r_ws.name} ({r_ws.slug})")

        self.stdout.write(self.style.SUCCESS("Successfully seeded E2E test data!"))
