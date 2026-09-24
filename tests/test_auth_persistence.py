"""Checks for the shared-account remember-login token."""

import unittest

from auth_persistence import LOGIN_LIFETIME_SECONDS, create_login_token, validate_login_token


class LoginTokenTests(unittest.TestCase):
    def test_valid_until_expiration(self):
        token = create_login_token("admin", "test-secret", now=1000)
        self.assertTrue(validate_login_token(token, "admin", "test-secret", now=1001))
        self.assertFalse(validate_login_token(token, "admin", "test-secret", now=1000 + LOGIN_LIFETIME_SECONDS))

    def test_password_change_revokes_existing_token(self):
        token = create_login_token("admin", "old-secret", now=1000)
        self.assertFalse(validate_login_token(token, "admin", "new-secret", now=1001))
        self.assertFalse(validate_login_token(token, "other-user", "old-secret", now=1001))

    def test_tampering_and_malformed_tokens_are_rejected(self):
        token = create_login_token("admin", "test-secret", now=1000)
        self.assertFalse(validate_login_token(token[:-1] + ("A" if token[-1] != "A" else "B"), "admin", "test-secret", now=1001))
        self.assertFalse(validate_login_token("not-a-token", "admin", "test-secret", now=1001))
        self.assertFalse(validate_login_token("", "admin", "test-secret", now=1001))


if __name__ == "__main__":
    unittest.main()
