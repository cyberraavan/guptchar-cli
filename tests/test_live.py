"""Against a running relay. Skipped unless GUPTCHAR_E2E_URL is set, e.g.
    GUPTCHAR_E2E_URL=http://127.0.0.1:8000 python -m unittest tests.test_live
"""

import os
import unittest
import uuid

from textual.widgets import Input, Static

from guptchar.app import CaptchaScreen, ChatScreen, GuptcharApp
from guptchar.session import Session

from .captcha_peek import APP_KEY, answer

URL = os.environ.get("GUPTCHAR_E2E_URL")


@unittest.skipUnless(URL and APP_KEY, "set GUPTCHAR_E2E_URL and GUPTCHAR_APP_KEY to run against a live relay")
class LiveTest(unittest.IsolatedAsyncioTestCase):
    async def test_captcha_screen_then_join(self):
        app = GuptcharApp(server_url=URL)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(10.6)
            self.assertIsInstance(app.screen, CaptchaScreen)
            for _ in range(20):
                if app.screen.challenge:
                    break
                await pilot.pause(0.2)

            await pilot.press(*"WRONG", "enter")  # one attempt per captcha -> new one
            await pilot.pause(1.0)
            self.assertIn("Wrong answer", str(app.screen.query_one("#cap-status", Static).render()))

            self.assertTrue(str(app.screen.query_one("#cap-prompt", Static).render()).strip())
            await pilot.press(*answer(app.screen.challenge), "enter")
            await pilot.pause(1.0)
            self.assertIsInstance(app.screen, ChatScreen)

            room = "cli-live-" + uuid.uuid4().hex[:8]
            for line in ("/nick raavan", "/key add"):
                await pilot.press(*line, "enter")
                await pilot.pause(0.2)
            await pilot.press("enter")  # default label
            await pilot.pause(0.2)
            await pilot.press(*"Orbit-Kite-42#Lamp", "enter")
            await pilot.pause(0.2)
            await pilot.press(*f"/join {room}", "enter")
            for _ in range(40):
                await pilot.pause(0.25)
                if app.session.joined:
                    break
            self.assertTrue(app.session.joined)
            await app.session.leave(quiet=True)

    async def test_session_asks_for_captcha_when_needed(self):
        asked = []
        s = None

        async def captcha():
            asked.append(1)
            c = await s.new_captcha()
            await s.solve_captcha(c["challenge"], answer(c["challenge"]))

        s = Session(URL, on_entry=lambda e: None, captcha=captcha)
        s.set_name("bot_test")
        s.add_key("", "Orbit-Kite-42#Lamp")
        await s.join("cli-live-" + uuid.uuid4().hex[:8])
        self.assertEqual(asked, [1])
        await s.close()


if __name__ == "__main__":
    unittest.main()
