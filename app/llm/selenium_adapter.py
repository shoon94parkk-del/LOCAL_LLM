import asyncio
import time
from threading import Lock

import pyperclip
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


END_MARKER = "[[END]]"
DEFAULT_INPUT_SELECTORS = (
    "textarea",
    "[data-testid='stChatInputTextArea']",
    "[contenteditable='true']",
)
DEFAULT_RESPONSE_SELECTORS = (
    "[data-message-author-role='assistant']",
    "[data-testid='stChatMessage']",
    ".stChatMessage",
)


class SeleniumGLM:
    """Selenium adapter for a company LLM exposed only through a web UI.

    The browser is created lazily on the first request. Calls are serialized with
    a thread lock because Selenium WebDriver is not thread-safe. `generate()`
    keeps the Agent's async interface by moving blocking browser work to a
    worker thread.
    """

    def __init__(
        self,
        url: str,
        *,
        timeout_ms: int = 1_800_000,
        input_selector: str = "textarea",
        submit_selector: str = "",
        response_selector: str = "[data-message-author-role='assistant'], [data-testid='stChatMessage']",
        stop_selector: str = "",
        stable_seconds: float = 5.0,
        max_continuations: int = 6,
    ):
        if not url.strip():
            raise ValueError("Selenium GLM URL 설정이 필요합니다")
        self.url = url.strip()
        self.timeout_seconds = max(10.0, timeout_ms / 1000.0)
        self.input_selector = input_selector.strip()
        self.submit_selector = submit_selector.strip()
        self.response_selector = response_selector.strip()
        self.stop_selector = stop_selector.strip()
        self.stable_seconds = max(1.0, float(stable_seconds))
        self.max_continuations = max(0, int(max_continuations))
        self._driver = None
        self._lock = Lock()

    async def generate(self, prompt: str) -> str:
        return await asyncio.to_thread(self._generate_locked, prompt)

    def _generate_locked(self, prompt: str) -> str:
        with self._lock:
            return self._generate_sync(prompt)

    def _generate_sync(self, prompt: str) -> str:
        driver = self._ensure_driver()
        request = self._with_end_marker_instruction(prompt)
        accumulated = ""

        for continuation in range(self.max_continuations + 1):
            before_count = len(self._response_elements(driver))
            sent = request if continuation == 0 else self._continuation_prompt(accumulated)
            self._send(driver, sent)
            segment = self._wait_for_response(driver, sent, before_count)
            accumulated = self._merge_segments(accumulated, segment)
            if END_MARKER in accumulated:
                return accumulated.split(END_MARKER, 1)[0].rstrip()

        raise RuntimeError(
            f"GLM 응답이 {self.max_continuations}회 이어쓰기 후에도 {END_MARKER} 마커 없이 종료되었습니다"
        )

    @staticmethod
    def _with_end_marker_instruction(prompt: str) -> str:
        return (
            prompt.rstrip()
            + "\n\n[응답 전송 규칙]\n"
            + f"답변을 끝까지 작성하고, 전체 답변의 마지막 줄에 반드시 {END_MARKER}를 출력하세요. "
            + "답변이 길어도 임의로 요약하거나 생략하지 마세요."
        )

    @staticmethod
    def _continuation_prompt(accumulated: str) -> str:
        tail = accumulated[-2500:] if accumulated else ""
        return (
            "직전 답변이 종료 마커 없이 중간에서 끊겼습니다. "
            "이미 작성한 내용을 처음부터 반복하지 말고 끊긴 다음 내용부터 이어서 작성하세요. "
            f"모든 내용이 끝나면 마지막 줄에 반드시 {END_MARKER}를 출력하세요.\n\n"
            "[직전 답변의 끝부분]\n"
            + tail
        )

    @staticmethod
    def _merge_segments(accumulated: str, segment: str) -> str:
        segment = segment.strip()
        if not accumulated:
            return segment
        if not segment:
            return accumulated
        max_overlap = min(4000, len(accumulated), len(segment))
        for size in range(max_overlap, 20, -1):
            if accumulated[-size:] == segment[:size]:
                return accumulated + segment[size:]
        return accumulated.rstrip() + "\n" + segment

    def _ensure_driver(self):
        if self._driver is not None:
            try:
                _ = self._driver.current_url
                return self._driver
            except WebDriverException:
                self._driver = None

        errors = []
        for factory in (webdriver.Chrome, webdriver.Edge):
            try:
                driver = factory()
                driver.set_page_load_timeout(self.timeout_seconds)
                driver.get(self.url)
                self._driver = driver
                return driver
            except Exception as exc:
                errors.append(f"{factory.__name__}: {exc}")

        raise RuntimeError(
            "Chrome/Edge Selenium WebDriver를 시작하지 못했습니다. 브라우저/드라이버 설치를 확인하세요. "
            + " | ".join(errors)
        )

    def _find_input(self, driver):
        selectors = [self.input_selector] if self.input_selector else []
        selectors.extend(s for s in DEFAULT_INPUT_SELECTORS if s not in selectors)
        for selector in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            visible = [element for element in elements if element.is_displayed() and element.is_enabled()]
            if visible:
                return visible[-1]
        raise RuntimeError("GLM 입력창을 찾지 못했습니다. LOCAL_LLM_GLM_INPUT_SELECTOR를 확인하세요")

    def _response_elements(self, driver):
        selectors = [self.response_selector] if self.response_selector else []
        selectors.extend(s for s in DEFAULT_RESPONSE_SELECTORS if s not in selectors)
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue
            visible = [element for element in elements if element.is_displayed()]
            if visible:
                return visible
        return []

    def _send(self, driver, prompt: str) -> None:
        input_element = self._find_input(driver)
        input_element.click()
        input_element.send_keys(Keys.CONTROL, "a")
        input_element.send_keys(Keys.BACKSPACE)
        pyperclip.copy(prompt)
        input_element.send_keys(Keys.CONTROL, "v")
        time.sleep(0.15)

        if self.submit_selector:
            submit = driver.find_elements(By.CSS_SELECTOR, self.submit_selector)
            visible = [element for element in submit if element.is_displayed() and element.is_enabled()]
            if not visible:
                raise RuntimeError("설정한 GLM 전송 버튼 selector를 찾지 못했습니다")
            visible[-1].click()
        else:
            input_element.send_keys(Keys.ENTER)

    def _stop_visible(self, driver) -> bool:
        if not self.stop_selector:
            return False
        try:
            return any(
                element.is_displayed()
                for element in driver.find_elements(By.CSS_SELECTOR, self.stop_selector)
            )
        except Exception:
            return False

    def _wait_for_response(self, driver, sent_prompt: str, before_count: int) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        previous = ""
        stable_since = time.monotonic()

        while time.monotonic() < deadline:
            time.sleep(0.7)
            elements = self._response_elements(driver)
            if not elements:
                continue

            latest = elements[-1].text.strip()
            if not latest:
                continue
            if len(elements) <= before_count and latest == sent_prompt.strip():
                continue
            if latest == sent_prompt.strip():
                continue

            if latest != previous:
                previous = latest
                stable_since = time.monotonic()

            if END_MARKER in latest:
                return latest
            if not self._stop_visible(driver) and time.monotonic() - stable_since >= self.stable_seconds:
                return latest

        if previous:
            return previous
        raise TimeoutError("사내 GLM 응답 대기 시간이 초과되었습니다")

    def close(self) -> None:
        with self._lock:
            if self._driver is not None:
                try:
                    self._driver.quit()
                finally:
                    self._driver = None
