"""Provider boundary regression tests, using fakes rather than live credentials."""
import unittest
from types import SimpleNamespace
from uuid import UUID

from alphaos_api.identity_foundation import IdentityUnavailable
from alphaos_api.supabase_identity import (
    SupabaseIdentityConfig, verify_supabase_access_token,
)


class IdentityFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.config = SupabaseIdentityConfig("https://project.supabase.co", "public-test-key")

    def test_bad_tokens_do_not_reach_provider(self):
        for token in (None, "", 123, "x" * 16385):
            with self.subTest(token_type=type(token).__name__):
                with self.assertRaises(IdentityUnavailable):
                    verify_supabase_access_token(token, config=self.config,
                        client_factory=lambda *_: self.fail("provider called"))

    def test_provider_failure_or_missing_user_denies_access(self):
        for response in (None, SimpleNamespace(user=None),
                         SimpleNamespace(user=SimpleNamespace(id="owner")),
                         SimpleNamespace(user=SimpleNamespace(id=str(UUID(int=0))))):
            client = SimpleNamespace(auth=SimpleNamespace(
                get_user=lambda _token, response=response: response))
            with self.subTest(response=response), self.assertRaises(IdentityUnavailable):
                verify_supabase_access_token("test-token", config=self.config,
                    client_factory=lambda *_args, client=client: client)

    def test_provider_exception_does_not_expose_secret(self):
        secret = "internal-provider-secret"
        def fail(_):
            raise RuntimeError(secret)
        client = SimpleNamespace(auth=SimpleNamespace(get_user=fail))
        with self.assertRaises(IdentityUnavailable) as caught:
            verify_supabase_access_token("test-token", config=self.config,
                client_factory=lambda *_: client)
        self.assertNotIn(secret, str(caught.exception))

    def test_verified_provider_subject_is_not_caller_supplied(self):
        subject = UUID(int=42)
        client = SimpleNamespace(auth=SimpleNamespace(
            get_user=lambda _: SimpleNamespace(user=SimpleNamespace(id=str(subject)))))
        principal = verify_supabase_access_token("test-token", config=self.config,
            client_factory=lambda *_: client)
        self.assertEqual(principal.user_id, subject)


if __name__ == "__main__":
    unittest.main()
