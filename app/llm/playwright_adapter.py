import asyncio
import time

from playwright.async_api import async_playwright

from app.config import Settings


class PlaywrightGLM:
    """Adapter for an internal GLM website without a public API.

    The company URL and CSS selectors are intentionally configured by environment
    variables because they differ by deployment and must not be committed.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = asyncio.Lock()

    async def generate(self, prompt: str) -> str:
        async with self.lock:
            return await self._generate(prompt)

    async def _generate(self, prompt: str) -> str:
        if not self.settings.glm_url:
            raise RuntimeError("LOCAL_LLM_GLM_URL is required in playwright mode")

        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.settings.glm_user_data_dir,
                headless=self.settings.glm_headless,
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                if not page.url.startswith(self.settings.glm_url):
                    await page.goto(
                        self.settings.glm_url,
                        wait_until="domcontentloaded",
                        timeout=self.settings.glm_timeout_ms,
                    )

                input_box = page.locator(self.settings.glm_input_selector).last
                await input_box.wait_for(state="visible", timeout=self.settings.glm_timeout_ms)

                responses = page.locator(self.settings.glm_response_selector)
                before_count = await responses.count()

                await input_box.fill(prompt)
                if self.settings.glm_submit_selector:
                    await page.locator(self.settings.glm_submit_selector).last.click()
                else:
                    await input_box.press("Enter")

                return await self._wait_for_new_response(responses, before_count, page)
            finally:
                await context.close()

    async def _wait_for_new_response(self, responses, before_count: int, page=None) -> str:
        deadline = time.monotonic() + self.settings.glm_timeout_ms / 1000
        previous = ""
        stable_since = time.monotonic()

        while time.monotonic() < deadline:
            count = await responses.count()
            if count > before_count:
                text = (await responses.nth(count - 1).inner_text()).strip()
                if text:
                    if text != previous:
                        previous = text
                        stable_since = time.monotonic()
                    generating = False
                    if self.settings.glm_stop_selector and page is not None:
                        generating = await page.locator(self.settings.glm_stop_selector).last.is_visible()
                    if generating:
                        stable_since = time.monotonic()
                    elif time.monotonic() - stable_since >= self.settings.glm_stable_seconds:
                        return text
            await asyncio.sleep(0.8)

        raise TimeoutError("GLM response did not finish before timeout")
