"""Run from repository root: python scripts/connect_company.py [--send-test]."""
import argparse
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.llm.playwright_adapter import PlaywrightGLM
from playwright.async_api import async_playwright


async def main(send_test):
    cfg = Settings()
    if not cfg.glm_url or 'your-internal-glm.example' in cfg.glm_url:
        raise SystemExit('.env의 LOCAL_LLM_GLM_URL을 실제 회사 URL로 설정하세요.')
    print('앱/Reflection을 종료한 후 사용하세요. 열린 브라우저에서 회사 계정으로 로그인하세요.')
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(cfg.glm_user_data_dir, headless=False)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(cfg.glm_url, wait_until='domcontentloaded', timeout=cfg.glm_timeout_ms)
            await asyncio.to_thread(input, '로그인이 끝나면 이 터미널에서 Enter: ')
            for label, selector in [('입력창', cfg.glm_input_selector), ('전송', cfg.glm_submit_selector),
                                    ('답변', cfg.glm_response_selector), ('생성중/중지', cfg.glm_stop_selector)]:
                if selector:
                    print(label, '일치 개수:', await page.locator(selector).count())
            print('입력창과 전송 버튼은 각각 1개를 가리키도록 설정하세요. 답변은 첫 응답 전 0개일 수 있습니다.')
        finally:
            await context.close()
    if send_test:
        print(await PlaywrightGLM(cfg).generate('연결 테스트입니다. 연결 성공이라고만 답해주세요.'))
    else:
        print('메시지를 보내지 않았습니다. 실제 전송 테스트: python scripts/connect_company.py --send-test')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--send-test', action='store_true')
    asyncio.run(main(parser.parse_args().send_test))
