import asyncio
import secrets


class BrowserBridge:
    """Local queue consumed by a browser extension or an authorized browser operator."""

    def __init__(self, cfg, timeout=180):
        self.cfg = cfg
        self.timeout = timeout
        self.lock = asyncio.Lock()
        self.pending = None
        self.future = None

    def selector_config(self):
        return {
            "input": self.cfg.glm_input_selector,
            "submit": self.cfg.glm_submit_selector,
            "response": self.cfg.glm_response_selector,
            "stop": self.cfg.glm_stop_selector,
            "stable_seconds": self.cfg.glm_stable_seconds,
        }

    async def generate(self, prompt):
        async with self.lock:
            job_id = secrets.token_hex(16)
            self.future = asyncio.get_running_loop().create_future()
            self.pending = {
                "id": job_id,
                "prompt": prompt,
                "selectors": self.selector_config(),
            }
            try:
                return await asyncio.wait_for(self.future, self.timeout)
            finally:
                self.pending = None
                self.future = None

    def complete(self, job_id, answer, error=""):
        if (
            not self.pending
            or self.pending["id"] != job_id
            or self.future is None
            or self.future.done()
        ):
            raise ValueError("만료되었거나 이미 처리한 요청입니다")
        if error:
            self.future.set_exception(RuntimeError(error))
        elif answer.strip():
            self.future.set_result(answer)
        else:
            raise ValueError("빈 응답은 완료할 수 없습니다")
