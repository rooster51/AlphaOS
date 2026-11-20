import unittest
from uuid import UUID

from alphaos_api.tenancy import (
    AuthenticatedActor, TenantAccessDenied, TenantMembership,
    authorize_tenant, ledger_owner,
)


class TenantIsolationTests(unittest.TestCase):
    def setUp(self):
        self.alice = AuthenticatedActor(UUID(int=101), "supabase-auth")
        self.bob = AuthenticatedActor(UUID(int=102), "supabase-auth")
        self.membership = TenantMembership(UUID(int=201), self.alice.user_id,
                                            "analyst", True)

    def test_membership_requires_matching_verified_user(self):
        with self.assertRaises(TenantAccessDenied):
            authorize_tenant(self.bob, self.membership)
        with self.assertRaises(TenantAccessDenied):
            authorize_tenant(None, self.membership)

    def test_inactive_membership_denied(self):
        inactive = TenantMembership(self.membership.tenant_id,
                                    self.alice.user_id, "owner", False)
        with self.assertRaises(TenantAccessDenied):
            authorize_tenant(self.alice, inactive)

    def test_roles_enforced(self):
        self.assertEqual(authorize_tenant(self.alice, self.membership,
                                         operation="write").role, "analyst")
        with self.assertRaises(TenantAccessDenied):
            authorize_tenant(self.alice, self.membership, operation="manage")
        viewer = TenantMembership(self.membership.tenant_id,
                                  self.alice.user_id, "viewer", True)
        with self.assertRaises(TenantAccessDenied):
            authorize_tenant(self.alice, viewer, operation="write")

    def test_personal_ledger_always_user_scoped(self):
        self.assertEqual(ledger_owner(self.alice), UUID(int=101))
        self.assertNotEqual(ledger_owner(self.alice), ledger_owner(self.bob))

    def test_invalid_role_and_actor_rejected(self):
        with self.assertRaises(TenantAccessDenied):
            TenantMembership(UUID(int=1), self.alice.user_id, "superuser", True)
        with self.assertRaises(TenantAccessDenied):
            AuthenticatedActor(UUID(int=0), "supabase-auth")


if __name__ == "__main__":
    unittest.main()
