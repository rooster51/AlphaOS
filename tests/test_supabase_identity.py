import unittest
from types import SimpleNamespace
from uuid import UUID
from alphaos_api.identity_foundation import IdentityUnavailable
from alphaos_api.supabase_identity import (
    SupabaseIdentityConfig, identity_config, verify_supabase_access_token,
)


class SupabaseIdentityTests(unittest.TestCase):
    def setUp(self):
        self.cfg = SupabaseIdentityConfig(
            "https://project.supabase.co", "public-anon-test-key")

    def factory(self, response=None, error=None):
        def build(url, key):
            self.assertEqual(url, self.cfg.url)
            self.assertEqual(key, self.cfg.publishable_key)
            def get_user(token):
                self.assertEqual(token, "signed-access-token")
                if error:
                    raise error
                return response
            return SimpleNamespace(auth=SimpleNamespace(get_user=get_user))
        return build

    def test_valid_server_verified_user(self):
        uid = str(UUID(int=17))
        response = SimpleNamespace(user=SimpleNamespace(id=uid))
        principal = verify_supabase_access_token("signed-access-token",
            config=self.cfg, client_factory=self.factory(response))
        self.assertEqual(str(principal.user_id), uid)
        self.assertEqual(principal.audience, "authenticated")

    def test_rejected_missing_user_and_bad_identity(self):
        for response in (None, SimpleNamespace(user=None),
                         SimpleNamespace(user=SimpleNamespace(id="owner")),
                         SimpleNamespace(user=SimpleNamespace(id="invalid"))):
            with self.subTest(response=response), self.assertRaises(IdentityUnavailable):
                verify_supabase_access_token("signed-access-token",
                    config=self.cfg, client_factory=self.factory(response))

    def test_auth_error_fails_closed(self):
        with self.assertRaises(IdentityUnavailable):
            verify_supabase_access_token("signed-access-token",
                config=self.cfg, client_factory=self.factory(
                    error=RuntimeError("secret network details")))

    def test_invalid_token_fails_before_provider_call(self):
        with self.assertRaises(IdentityUnavailable):
            verify_supabase_access_token("", config=self.cfg,
                client_factory=lambda *args: self.fail("unexpected provider call"))

    def test_config_requires_https_and_public_key(self):
        for url in ("http://project.supabase.co",
                    "https://project.supabase.co/other",
                    "https://user:pass@project.supabase.co"):
            with self.subTest(url=url), self.assertRaises(IdentityUnavailable):
                identity_config({"SUPABASE_URL": url, "SUPABASE_ANON_KEY": "test"})
        with self.assertRaises(IdentityUnavailable):
            identity_config({"SUPABASE_URL": "https://project.supabase.co"})


if __name__ == "__main__":
    unittest.main()
