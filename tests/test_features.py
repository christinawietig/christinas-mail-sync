"""Tests fuer Update-Hinweis, Vorschau beim ersten Lauf, Restzeit und Protokoll kopieren."""
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mailsync import config, plan, sync, update  # noqa: E402


class UpdateTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(update.parse("1.0.10"), (1, 0, 10))
        self.assertEqual(update.parse("1.1.0"), update.parse("1.1"))
        self.assertIsNone(update.parse("v1.0"))
        self.assertIsNone(update.parse(""))
        self.assertIsNone(update.parse(None))

    def test_is_newer(self):
        self.assertTrue(update.is_newer("1.0.2", "1.0.1"))
        self.assertTrue(update.is_newer("1.0.10", "1.0.9"))  # nicht als Text vergleichen
        self.assertTrue(update.is_newer("2", "1.9.9"))
        self.assertFalse(update.is_newer("1.0.1", "1.0.1"))
        self.assertFalse(update.is_newer("1.0.1.0", "1.0.1"))
        self.assertFalse(update.is_newer("1.0.0", "1.0.1"))
        self.assertFalse(update.is_newer("unsinn", "1.0.1"))

    def _fake_open(self, url):
        class Response:
            def geturl(self):
                return url

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass
        return lambda req, **kw: Response()

    def test_latest_version_from_redirect(self):
        with mock.patch("urllib.request.urlopen", self._fake_open(update.REPO_URL + "/releases/tag/v1.2.3")):
            self.assertEqual(update.latest_version(), "1.2.3")

    def test_latest_version_rejects_unexpected_page(self):
        # Noch kein Release: GitHub zeigt die Release-Liste statt eines Tags
        with mock.patch("urllib.request.urlopen", self._fake_open(update.REPO_URL + "/releases")):
            self.assertRaises(ValueError, update.latest_version)

    def test_check(self):
        with mock.patch.object(update, "latest_version", return_value="99.0"):
            self.assertEqual(update.check(), "99.0")
        with mock.patch.object(update, "latest_version", return_value=update.__version__):
            self.assertIsNone(update.check())

    def test_check_offline_is_silent(self):
        with mock.patch.object(update, "latest_version", side_effect=OSError("offline")):
            self.assertIsNone(update.check())


class RemainingTest(unittest.TestCase):
    def test_format_count(self):
        self.assertEqual(sync.format_count(7), "7")
        self.assertEqual(sync.format_count(1243), "1.243")
        self.assertEqual(sync.format_count(1234567), "1.234.567")

    def test_format_remaining(self):
        self.assertEqual(sync.format_remaining(10), "unter einer Minute")
        self.assertEqual(sync.format_remaining(70), "ca. 1 Minute")
        self.assertEqual(sync.format_remaining(5 * 60), "ca. 5 Minuten")
        self.assertEqual(sync.format_remaining(60 * 60), "ca. 1 Std.")
        self.assertEqual(sync.format_remaining(132 * 60), "ca. 2 Std. 10 Min.")
        self.assertEqual(sync.format_remaining(15 * 3600), "ca. 15 Stunden")

    def test_estimate_remaining(self):
        self.assertIsNone(sync.estimate_remaining(5, 100, 60))  # zu wenige Mails
        self.assertIsNone(sync.estimate_remaining(50, 100, 5))  # zu kurz
        self.assertIsNone(sync.estimate_remaining(100, 100, 60))  # fertig
        self.assertAlmostEqual(sync.estimate_remaining(20, 100, 40), 160)


class SupportTextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, "letzter-lauf.txt")

    def test_passwords_are_masked(self):
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("Login mit geheim123 und pw-2#?\nFertig\n")
        text = sync.support_text(self.log, ("geheim123", "pw-2#?", ""), "1.0.2", "macOS 15")
        self.assertNotIn("geheim123", text)
        self.assertNotIn("pw-2#?", text)
        self.assertIn("Fertig", text)
        self.assertTrue(text.startswith("Christinas Mail-Sync 1.0.2, macOS 15"))

    def test_long_log_is_shortened_in_the_middle(self):
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("".join("Zeile %d\n" % i for i in range(10000)))
        lines = sync.support_text(self.log, (), "1", "x").splitlines()
        self.assertIn("Zeile 0", lines)
        self.assertIn("Zeile 9999", lines)
        self.assertNotIn("Zeile 5000", lines)
        self.assertIn("… %d Zeilen ausgelassen …" % (10000 - sync.SUPPORT_HEAD - sync.SUPPORT_TAIL), lines)

    def test_missing_log(self):
        self.assertIn("Kein Protokoll", sync.support_text(self.log, (), "1", "x"))


class PreviewTest(unittest.TestCase):
    """Erster Lauf in ein Ziel: Vorschau, dann erst nach Bestaetigung kopieren."""

    TODO = [("INBOX", "1:3", 3), ("Archiv", "5", 1)]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {"MAILSYNC_DATA_DIR": self.tmp})
        env.start()
        self.addCleanup(env.stop)
        for target, kwargs in ((plan, {"plan": mock.DEFAULT, "update_state": mock.DEFAULT}),
                               (sync, {"imapsync_cmd": mock.DEFAULT})):
            p = mock.patch.multiple(target, **kwargs)
            mocks = p.start()
            self.addCleanup(p.stop)
            if target is plan:
                mocks["plan"].return_value = self.TODO
                mocks["update_state"].return_value = (set(), 0)
        self.settings = config.Settings(source_host="alt.example.org", source_user="a",
                                        target_host="neu.example.org", target_user="b")

    def run_sync(self, answer):
        """answer: was bei der Vorschau passiert ("proceed", "stop" oder None = kommt nicht)."""
        events, done = [], threading.Event()
        copied = []

        def on_event(kind, **data):
            events.append((kind, data))
            if kind == "preview":
                getattr(s, answer)()
            if kind in ("done", "error"):
                done.set()

        s = sync.Sync(self.settings, "pw1", "pw2", on_event)
        s._imapsync = lambda exe, tmp, p1, p2, folder, uids: (copied.append(folder), (1, 0))[1]
        s.start()
        self.assertTrue(done.wait(10))
        return [k for k, _ in events], dict(events), copied

    def test_first_run_waits_for_confirmation(self):
        kinds, data, copied = self.run_sync("proceed")
        self.assertEqual(kinds[:3], ["status", "preview", "planned"])
        self.assertEqual(data["preview"], {"total": 4, "folders": [("INBOX", 3), ("Archiv", 1)]})
        self.assertEqual(copied, ["INBOX", "Archiv"])
        self.assertEqual(data["done"]["result"].transferred, 2)
        # Zweiter Lauf: keine Vorschau mehr
        kinds, _, copied = self.run_sync(None)
        self.assertNotIn("preview", kinds)
        self.assertEqual(copied, ["INBOX", "Archiv"])

    def test_cancel_in_preview_copies_nothing(self):
        kinds, data, copied = self.run_sync("stop")
        self.assertEqual(copied, [])
        self.assertTrue(data["done"]["result"].stopped)
        self.assertNotIn("planned", kinds)
        # Nach dem Abbrechen kommt die Vorschau beim naechsten Start wieder
        kinds, _, _ = self.run_sync("proceed")
        self.assertIn("preview", kinds)

    def test_new_target_shows_preview_again(self):
        self.run_sync("proceed")
        self.settings.target_user = "c"
        kinds, _, _ = self.run_sync("proceed")
        self.assertIn("preview", kinds)

    def test_nothing_new_needs_no_confirmation(self):
        plan.plan.return_value = []
        kinds, _, copied = self.run_sync(None)
        self.assertNotIn("preview", kinds)
        self.assertEqual(copied, [])


class SyncFrameTest(unittest.TestCase):
    """Die Oberflaeche ohne echten Sync durchspielen (braucht einen Bildschirm)."""

    def setUp(self):
        from mailsync import gui
        try:
            self.app = gui.App()
        except Exception as e:  # tkinter.TclError ohne Bildschirm
            self.skipTest("kein Bildschirm: %s" % e)
        self.addCleanup(self.app.root.destroy)
        self.calls = calls = []

        class FakeSync:
            log_path = os.path.join(tempfile.mkdtemp(), "letzter-lauf.txt")

            def __init__(self, *a):
                pass

            def start(self):
                pass

            def proceed(self):
                calls.append("proceed")

            def stop(self):
                calls.append("stop")

        p = mock.patch.object(gui, "Sync", FakeSync)
        p.start()
        self.addCleanup(p.stop)
        self.app.show_sync("pw1", "pw2")
        self.f = self.app.frame

    def test_preview_then_progress_then_done(self):
        f = self.f
        f.on_event("preview", {"total": 1243, "folders": [("INBOX", 1200), ("Elternbriefe &AMQ-", 43)]})
        self.assertEqual(f.headline["text"], "Bereit zum Übertragen")
        self.assertEqual(str(f.detail["text"]), "1.243 neue Mail(s) werden ins neue Postfach kopiert.")
        self.assertFalse(f.bar.winfo_manager())
        f.main_button.invoke()  # "Übertragen"
        self.assertEqual(self.calls, ["proceed"])
        self.assertTrue(f.bar.winfo_manager())
        f.on_event("planned", {"total": 1243, "folders": []})
        f.on_event("folder", {"i": 1, "n": 2, "name": "INBOX"})
        f.started -= 60
        for _ in range(100):
            f.on_event("copied", {})
        self.assertEqual(str(f.detail["text"]), "Ordner 1 von 2 – 100 von 1.243 Mail(s)")
        self.assertTrue(str(f.eta["text"]).startswith("Noch ca. "))
        f.on_event("done", {"result": sync.Result(transferred=1243)})
        self.assertEqual(f.headline["text"], "Fertig.")
        self.assertFalse(f.help.winfo_manager())  # Hilfetext nur nach Fehlern
        self.assertEqual(str(f.eta["text"]), "")

    def test_cancel_in_preview(self):
        f = self.f
        f.on_event("preview", {"total": 3, "folders": [("INBOX", 3)]})
        f.cancel_button.invoke()
        self.assertEqual(self.calls, ["stop"])
        f.on_event("done", {"result": sync.Result(stopped=True)})
        self.assertEqual(f.headline["text"], "Abgebrochen.")

    def test_copy_log_after_failure(self):
        f = self.f
        with open(f.log_path, "w", encoding="utf-8") as fh:
            fh.write("Fehler mit pw1\n")
        f.on_event("done", {"result": sync.Result(transferred=1, failed_folders=1)})
        self.assertTrue(f.copy_button.winfo_manager())
        self.assertTrue(f.help.winfo_manager())
        self.assertIn("Zwischenablage", f.help["text"])
        f.copy_button.invoke()
        self.assertTrue(str(f.help["text"]).startswith("✓ Das Protokoll liegt jetzt in der Zwischenablage"))
        text = f.clipboard_get()
        self.assertIn("Fehler mit ********", text)
        self.assertNotIn("pw1", text)

    def test_update_banner_stays_on_top(self):
        self.app.show_update("9.9.9")
        self.app.show_update("9.9.9")  # nur einmal
        self.app.show_sync("pw1", "pw2")
        slaves = self.app.root.pack_slaves()
        self.assertIs(slaves[0], self.app.banner)
        self.assertIn("9.9.9", self.app.banner["text"])
        self.assertEqual(len(slaves), 2)


if __name__ == "__main__":
    unittest.main()
