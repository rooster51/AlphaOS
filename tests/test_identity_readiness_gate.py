import unittest
from uuid import UUID
from alphaos_api.identity_foundation import (
    IdentityUnavailable, require_ledger_principal,
    research_only_grant_has_ledger_access,
)
from alphaos_api.deployment_readiness import assess_readiness


class IdentityReadinessTests(unittest.TestCase):
    def test_unverified_subject_fails_closed(self):
        for subject in (None, "owner", "client-id", str(UUID(int=1))):
            with self.subTest(subject=subject), self.assertRaises(IdentityUnavailable):
                require_ledger_principal(verified_subject=subject,
                    issuer="https://identity.example", audience="alphaos-ledger")

    def test_verified_uuid_requires_explicit_verification(self):
        with self.assertRaises(IdentityUnavailable):
            require_ledger_principal(verified_subject=str(UUID(int=1)),
                issuer="https://identity.example", audience="alphaos-ledger")
        principal = require_ledger_principal(verified_subject=str(UUID(int=1)),
            issuer="https://identity.example", audience="alphaos-ledger",
            verified=True)
        self.assertEqual(principal.user_id, UUID(int=1))

    def test_invalid_verified_subject_rejected(self):
        for subject in ("owner", "not-a-uuid", str(UUID(int=0))):
            with self.subTest(subject=subject), self.assertRaises(IdentityUnavailable):
                require_ledger_principal(verified_subject=subject,
                    issuer="https://identity.example", audience="alphaos-ledger",
                    verified=True)

    def test_existing_research_grants_do_not_authorize_ledger(self):
        self.assertFalse(research_only_grant_has_ledger_access())

    def test_readiness_never_exposes_secrets(self):
        env = {"ALPHAOS_API_TOKEN": "secret-value",
               "PUBLIC_API_SECRET": "public-secret",
               "PUBLIC_ACCOUNT_NUMBER": "123",
               "SUPABASE_URL": "https://example.supabase.co",
               "SUPABASE_SERVICE_ROLE_KEY": "sensitive"}
        result = assess_readiness(env)
        self.assertTrue(result.ready)
        self.assertNotIn("secret-value", str(result.public()))
        self.assertNotIn("sensitive", str(result.public()))

    def test_missing_archive_config_blocks(self):
        result = assess_readiness({"ALPHAOS_API_TOKEN": "x"})
        self.assertFalse(result.ready)
        self.assertIn("missing_supabase_url", result.blockers)
        self.assertIn("missing_supabase_service_role_key", result.blockers)

    def test_invalid_origin_blocks(self):
        env = {k: "present" for k in (
            "ALPHAOS_API_TOKEN", "PUBLIC_API_SECRET",
            "PUBLIC_ACCOUNT_NUMBER", "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY")}
        env["ALPHAOS_PUBLIC_URL"] = "http://localhost:8000"
        self.assertIn("invalid_alphaos_public_url", assess_readiness(env).blockers)


if __name__ == "__main__":
    unittest.main()
