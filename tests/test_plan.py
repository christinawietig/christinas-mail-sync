import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mailsync import config, plan, setupcode, sync  # noqa: E402


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

    def test_mail_key_ignores_imapsync_substitute_id(self):
        # Die Kopie (mit Ersatz-ID von imapsync --addheader) passt zum Original
        h = "Date: Mon, 1 Jan 2024\nFrom: a@b.de\nSubject: x\n"
        self.assertEqual(plan.mail_key("Message-Id: <17@imapsync>\n" + h), plan.mail_key(h))

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


class SetupCodeTest(unittest.TestCase):
    ARGS = ("imap.alt.example.org", 993, "imap.neu.example.org", 143, "localpart", ["INBOX.Trash", "Spam"])

    def test_roundtrip(self):
        d = setupcode.decode(setupcode.encode(*self.ARGS))
        self.assertEqual((d["source_host"], d["source_port"]), ("imap.alt.example.org", 993))
        self.assertEqual((d["target_host"], d["target_port"]), ("imap.neu.example.org", 143))
        self.assertEqual(d["target_user_rule"], "localpart")
        self.assertEqual(d["exclude_folders"], ["INBOX.Trash", "Spam"])

    def test_export_from_settings(self):
        s = config.Settings(source_host="imap.alt.example.org", source_user="max.muster@alt.example.org",
                            target_host="imap.neu.example.org", target_user="max.muster",
                            exclude_folders=["INBOX.Trash"])
        d = setupcode.decode(setupcode.from_settings(s))
        self.assertEqual(d["target_user_rule"], "localpart")
        self.assertNotIn("max.muster", setupcode.from_settings(s))
        self.assertEqual(d["exclude_folders"], ["INBOX.Trash"])

    def test_tolerant_input(self):
        code = setupcode.encode(*self.ARGS)
        messy = "  \n " + code.lower().replace("-", " - \n").replace("0", "o") + "\t  "
        self.assertEqual(setupcode.decode(messy), setupcode.decode(code))

    def test_detects_typos_and_truncation(self):
        code = setupcode.encode(*self.ARGS)
        body = code[4:]
        for i in range(len(body)):
            c = body[i]
            if c == "-":
                continue
            wrong = "X" if c != "X" else "Y"
            with self.assertRaises(setupcode.CodeError):
                setupcode.decode(code[:4] + body[:i] + wrong + body[i + 1:])
        with self.assertRaises(setupcode.CodeError):
            setupcode.decode(code[:-3])
        with self.assertRaises(setupcode.CodeError):
            setupcode.decode("hallo")

    def test_apply_code_keeps_users(self):
        base = config.Settings(source_user="a@b.de", target_user="a")
        s = config.apply_code(setupcode.encode(*self.ARGS), base)
        self.assertEqual((s.source_user, s.target_user, s.source_host), ("a@b.de", "a", "imap.alt.example.org"))
        self.assertEqual(base.source_host, "")


if __name__ == "__main__":
    unittest.main()
