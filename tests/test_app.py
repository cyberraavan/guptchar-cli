"""Drives the Textual interface headlessly (no server needed)."""

import unittest

from textual.widgets import Input, Static

from guptchar.app import BootScreen, ChatScreen, GuptcharApp, TooSmallScreen
from guptchar import texts as T


def log_text(app: GuptcharApp) -> str:
    return "\n".join(str(w.render()) for w in app.screen.query("#log Static"))


class AppTest(unittest.IsolatedAsyncioTestCase):
    async def test_boot_then_commands(self):
        app = GuptcharApp(server_url="http://127.0.0.1:9")  # nothing listens there
        async with app.run_test(size=(120, 40)) as pilot:
            self.assertIsInstance(app.screen, BootScreen)
            await pilot.pause(4.0)
            self.assertIsInstance(app.screen, BootScreen, "boot must last 5 seconds")
            await pilot.pause(1.6)
            self.assertIsInstance(app.screen, ChatScreen)
            self.assertIn(T.IP_WARNING, log_text(app))

            await pilot.press(*"/help", "enter")
            await pilot.pause(0.2)
            self.assertIn("/key add", log_text(app))

            await pilot.press(*"/nick bad name", "enter")
            await pilot.pause(0.2)
            self.assertIn(T.INVALID_NAME, log_text(app))

            await pilot.press(*"/nick raavan", "enter")
            await pilot.press(*"/key add", "enter")
            await pilot.pause(0.2)
            await pilot.press(*"phone", "enter")
            await pilot.pause(0.1)
            self.assertTrue(app.screen.query_one(Input).password, "key input must be hidden")
            await pilot.press(*"Orbit-Kite-42#Lamp", "enter")
            await pilot.pause(0.2)
            self.assertFalse(app.screen.query_one(Input).password)
            self.assertEqual([k["label"] for k in app.session.keys], ["phone"])
            self.assertNotIn("Orbit-Kite-42#Lamp", log_text(app))
            self.assertIn("Key strength: strong", log_text(app))
            self.assertIn("raavan", str(app.screen.query_one("#prompt", Static).render()))

            await pilot.press(*"/mode", "enter")
            await pilot.pause(0.2)
            self.assertIn(T.WEB_ONLY, log_text(app))

            await pilot.press(*"/join valid-room-1", "enter")
            for _ in range(40):  # Windows takes ~2-4 s to refuse a closed port
                await pilot.pause(0.25)
                if T.OFFLINE in log_text(app):
                    break
            self.assertIn(T.OFFLINE, log_text(app))  # relay unreachable -> friendly error

    async def test_too_small_terminal(self):
        app = GuptcharApp(server_url="http://127.0.0.1:9")
        async with app.run_test(size=(50, 15)) as pilot:
            await pilot.pause(0.2)
            self.assertIsInstance(app.screen, TooSmallScreen)
            await pilot.resize_terminal(80, 30)
            await pilot.pause(0.3)
            self.assertNotIsInstance(app.screen, TooSmallScreen)


if __name__ == "__main__":
    unittest.main()
