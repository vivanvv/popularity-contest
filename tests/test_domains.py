import unittest

from popularity_contest.domains import domain_flags, is_excluded_by_default, normalize_domain


class DomainTests(unittest.TestCase):
    def test_normalize_domain_from_url(self):
        self.assertEqual(normalize_domain("https://www.Example.com/path?q=1"), "example.com")

    def test_infrastructure_domain_is_excluded(self):
        self.assertTrue(is_excluded_by_default("static.example.com"))
        self.assertIn("infrastructure_label", domain_flags("cdn.example.com"))

    def test_editorial_tokens_are_flagged_not_excluded(self):
        self.assertIn("editorial_review_token", domain_flags("bestcasino.example"))
        self.assertFalse(is_excluded_by_default("bestcasino.example"))


if __name__ == "__main__":
    unittest.main()
