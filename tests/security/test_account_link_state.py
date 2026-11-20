import unittest
from uuid import UUID
from alphaos_api.account_link_state import AccountLinkStore, LinkDenied, VerifiedGrant
from alphaos_api.identity_foundation import LedgerPrincipal


class AccountLinkStateTests(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.store = AccountLinkStore(clock=lambda: self.now[0])
        self.grant = VerifiedGrant("a" * 64, "chatgpt-client")
        self.other = VerifiedGrant("b" * 64, "chatgpt-client")
        self.user = LedgerPrincipal(UUID(int=11), "https://auth.example", "authenticated")

    def test_explicit_consent_and_one_time_ticket(self):
        ticket = self.store.begin(self.grant)
        with self.assertRaises(LinkDenied):
            self.store.approve(ticket, self.grant, self.user, explicit_consent=False)
        with self.assertRaises(LinkDenied):
            self.store.approve(ticket, self.grant, self.user, explicit_consent=True)
        ticket = self.store.begin(self.grant)
        linked = self.store.approve(ticket, self.grant, self.user, explicit_consent=True)
        self.assertEqual(self.store.resolve(self.grant), linked)
        with self.assertRaises(LinkDenied):
            self.store.approve(ticket, self.grant, self.user, explicit_consent=True)

    def test_cross_grant_approval_and_resolution_denied(self):
        ticket = self.store.begin(self.grant)
        with self.assertRaises(LinkDenied):
            self.store.approve(ticket, self.other, self.user, explicit_consent=True)
        with self.assertRaises(LinkDenied):
            self.store.resolve(self.other)
        self.assertEqual(len(self.store._linked), 0)

    def test_expired_ticket_and_expired_link(self):
        ticket = self.store.begin(self.grant)
        self.now[0] += 301
        with self.assertRaises(LinkDenied):
            self.store.approve(ticket, self.grant, self.user, explicit_consent=True)
        ticket = self.store.begin(self.grant)
        self.store.approve(ticket, self.grant, self.user, explicit_consent=True)
        self.now[0] += 901
        with self.assertRaises(LinkDenied):
            self.store.resolve(self.grant)

    def test_revocation_and_restart_fail_closed(self):
        ticket = self.store.begin(self.grant)
        self.store.approve(ticket, self.grant, self.user, explicit_consent=True)
        self.store.revoke(self.grant)
        with self.assertRaises(LinkDenied):
            self.store.resolve(self.grant)
        ticket = self.store.begin(self.grant)
        self.store.approve(ticket, self.grant, self.user, explicit_consent=True)
        with self.assertRaises(LinkDenied):
            AccountLinkStore(clock=lambda: self.now[0]).resolve(self.grant)

    def test_no_unverified_user_or_grant(self):
        with self.assertRaises(LinkDenied):
            self.store.begin("owner")
        ticket = self.store.begin(self.grant)
        with self.assertRaises(LinkDenied):
            self.store.approve(ticket, self.grant, "owner", explicit_consent=True)
        with self.assertRaises(LinkDenied):
            self.store.resolve(self.grant)

    def test_invalid_grant_identity_rejected(self):
        for fingerprint in ("owner", "A" * 64, "z" * 64):
            with self.assertRaises(LinkDenied):
                VerifiedGrant(fingerprint, "chatgpt-client")


if __name__ == "__main__":
    unittest.main()
