import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mailsync import config, plan, sync  # noqa: E402


class PlanTest(unittest.TestCase):
    def test_uid_set(self):
        self.assertEqual(plan.uid_set([9, 1, 2, 3, 7, 10]), "1:3,7,9:10")
        self.assertEqual(plan.uid_set([5]), "5")

    def test_mail_key_uses_message_id(self):
        h = plan.unfold(b"Message-ID:\r\n <abc@example.org>\r\nSubject: Hallo\r\n")
        self.assertEqual(plan.mail_key(h), "<abc@example.org>")

    def test_mail_key_without_message_id_is_stable(self):
        h = "Date: Mon, 1 Jan 2024\nFrom: a@b.de\nSubject: x\n"
        self.assertTrue(plan.mail_key(h).startswith("nomid:"))
        self.assertEqual(plan.mail_key(h), plan.mail_key(h))

    def test_quote(self):
        self.assertEqual(plan.quote('a "b" \\c'), '"a \\"b\\" \\\\c"')

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.txt")
            self.assertEqual(plan.load_state(p), set())
            plan.save_state(p, {"<b>", "<a>"})
            self.assertEqual(plan.load_state(p), {"<a>", "<b>"})


class SyncTest(unittest.TestCase):
    def test_lock_is_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "lock")
            with sync.Lock(p):
                with self.assertRaises(sync.AlreadyRunning):
                    with sync.Lock(p):
                        pass
            with sync.Lock(p):
                pass

    def test_suggest_target_user(self):
        s = config.Settings(target_user_rule="localpart")
        self.assertEqual(s.suggest_target_user("c.muster@schule.de"), "c.muster")
        self.assertEqual(config.Settings().suggest_target_user("c.muster@schule.de"), "")


class ProfileTest(unittest.TestCase):
    def test_example_profile(self):
        path = os.path.join(os.path.dirname(__file__), "..", "examples", "mailsync-profil.json")
        base = config.Settings(source_user="a@b.de", target_user="a")
        s = config.load_profile(path, base)
        self.assertEqual(s.source_host, "imap.alter-anbieter.example.org")
        self.assertEqual(s.target_port, 993)
        self.assertEqual(s.exclude, [r"^INBOX\.Trash$"])
        self.assertEqual((s.source_user, s.target_user), ("a@b.de", "a"))
        self.assertEqual(base.source_host, "")  # Original unveraendert

    def test_broken_profile(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            with open(p, "w") as f:
                f.write('{"source": {}}')
            with self.assertRaises(config.ProfileError):
                config.load_profile(p, config.Settings())


if __name__ == "__main__":
    unittest.main()
