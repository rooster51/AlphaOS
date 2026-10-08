"""Negative authorization tests. No live database or credentials required."""
import unittest
from dataclasses import FrozenInstanceError
from uuid import UUID

from alphaos_api.identity_foundation import (
    IdentityUnavailable, require_ledger_principal,
    research_only_grant_has_ledger_access,
)
from alphaos_api.tenancy import (
    AuthenticatedActor, TenantMembership, TenantAccessDenied,
    authorize_tenant, ledger_owner,
)


class AuthorizationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.a = AuthenticatedActor(UUID(int=101), "https://auth.example")
        self.b = AuthenticatedActor(UUID(int=102), "https://auth.example")
        self.workspace = UUID(int=201)

    def membership(self, user, role="owner", active=True):
        return TenantMembership(self.workspace, user.user_id, role, active)

    def test_other_user_cannot_use_owner_or_admin_membership(self):
        for role in ("owner", "admin", "analyst", "viewer"):
            for operation in ("read", "write", "manage"):
                with self.subTest(role=role, operation=operation):
                    with self.assertRaises(TenantAccessDenied):
                        authorize_tenant(self.b, self.membership(self.a, role), operation=operation)

    def test_inactive_membership_rejected_for_every_operation(self):
        for operation in ("read", "write", "manage"):
            with self.assertRaises(TenantAccessDenied):
                authorize_tenant(self.a, self.membership(self.a, active=False), operation=operation)

    def test_role_matrix(self):
        permissions = {
            "owner": {"read", "write", "manage"},
            "admin": {"read", "write", "manage"},
            "analyst": {"read", "write"},
            "viewer": {"read"},
        }
        for role, allowed in permissions.items():
            for operation in ("read", "write", "manage"):
                with self.subTest(role=role, operation=operation):
                    if operation in allowed:
                        self.assertEqual(authorize_tenant(
                            self.a, self.membership(self.a, role), operation=operation
                        ).tenant_id, self.workspace)
                    else:
                        with self.assertRaises(TenantAccessDenied):
                            authorize_tenant(self.a, self.membership(self.a, role), operation=operation)

    def test_invalid_operations_and_untrusted_membership_rejected(self):
        for operation in ("delete", "", None, "manage:all"):
            with self.assertRaises(TenantAccessDenied):
                authorize_tenant(self.a, self.membership(self.a), operation=operation)
        with self.assertRaises(TenantAccessDenied):
            authorize_tenant(self.a, {"user_id": self.a.user_id, "role": "owner"})

    def test_legacy_owner_never_authorizes_private_ledger(self):
        self.assertFalse(research_only_grant_has_ledger_access())
        for subject in ("owner", str(self.a.user_id)):
            with self.assertRaises(IdentityUnavailable):
                require_ledger_principal(verified_subject=subject,
                    issuer="https://auth.example", audience="authenticated")

    def test_private_ledger_is_person_scoped(self):
        self.assertEqual(ledger_owner(self.a), self.a.user_id)
        self.assertNotEqual(ledger_owner(self.a), ledger_owner(self.b))
        with self.assertRaises(TenantAccessDenied):
            ledger_owner(self.membership(self.a))

    def test_context_cannot_be_mutated(self):
        context = authorize_tenant(self.a, self.membership(self.a))
        with self.assertRaises(FrozenInstanceError):
            context.role = "superuser"


if __name__ == "__main__":
    unittest.main()
