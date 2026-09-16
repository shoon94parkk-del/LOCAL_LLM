(async () => {
  const auth = await chrome.runtime.sendMessage({type: 'authorize'}).catch(() => ({ok: false}));
  if (!auth?.ok) return;

  let enabled = false;
  let busy = false;
  const completed = new Set();
  const button = document.createElement('button');
  button.textContent = 'LOCAL Agent 연결 시작';
  Object.assign(button.style, {
    position: 'fixed', right: '16px', bottom: '16px', zIndex: 2147483647,
    padding: '12px', background: '#164d3f', color: 'white', border: '0',
    borderRadius: '8px', fontWeight: '700', boxShadow: '0 6px 20px #0002'
  });
  document.body.appendChild(button);
  button.onclick = () => {
    enabled = !enabled;
    button.textContent = enabled
      ? 'LOCAL Agent 연결됨 (클릭하여 중지)'
      : 'LOCAL Agent 연결 시작';
  };

  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const visible = e => e && e.getClientRects().length > 0;

  function fillInput(input, prompt) {
    input.focus();
    if ('value' in input) {
      const setter = Object.getOwnPropertyDescriptor(
        Object.getPrototypeOf(input), 'value'
      )?.set;
      if (setter) setter.call(input, prompt);
      else input.value = prompt;
    } else {
      input.textContent = '';
      document.execCommand('insertText', false, prompt);
    }
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
  }

  async function submit(input, selector) {
    if (selector) {
      const send = document.querySelector(selector);
      if (!send || send.disabled) {
        throw new Error('설정한 GLM 전송 버튼 selector를 찾을 수 없습니다.');
      }
      send.click();
      return;
    }
    for (const type of ['keydown', 'keypress', 'keyup']) {
      input.dispatchEvent(new KeyboardEvent(type, {
        key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
        bubbles: true, cancelable: true
      }));
    }
  }

  async function process(job) {
    const selectors = job.selectors || {};
    const inputSelector = selectors.input;
    const answerSelector = selectors.response;
    if (!inputSelector || !answerSelector) {
      throw new Error('GLM input/response selector 설정이 필요합니다.');
    }

    const input = document.querySelector(inputSelector);
    if (!input) throw new Error('GLM 입력창을 찾을 수 없습니다. selector를 확인하세요.');
    const existing = ('value' in input ? input.value : input.innerText || '').trim();
    if (existing) throw new Error('GLM 입력창에 작성 중인 내용이 있습니다. 비운 뒤 다시 실행하세요.');

    const before = document.querySelectorAll(answerSelector).length;
    fillInput(input, job.prompt);
    await delay(250);
    await submit(input, selectors.submit || '');

    const deadline = Date.now() + 240000;
    const stableMs = Math.max(1000, Number(selectors.stable_seconds || 5) * 1000);
    let previous = '';
    let stableSince = Date.now();

    while (Date.now() < deadline) {
      await delay(700);
      const answers = document.querySelectorAll(answerSelector);
      if (answers.length <= before) continue;
      const text = answers[answers.length - 1].innerText.trim();
      const stop = selectors.stop ? document.querySelector(selectors.stop) : null;
      if (text !== previous || visible(stop)) {
        previous = text;
        stableSince = Date.now();
      }
      if (text && !visible(stop) && Date.now() - stableSince >= stableMs) return text;
    }
    throw new Error('GLM 응답 시간 초과. 로그인 상태, selector 또는 사용량 제한을 확인하세요.');
  }

  setInterval(async () => {
    if (!enabled || busy) return;
    busy = true;
    let job;
    try {
      const data = await chrome.runtime.sendMessage({type: 'poll'});
      if (data.error) {
        button.textContent = data.error;
        return;
      }
      job = data.job;
      if (!job || completed.has(job.id)) return;
      completed.add(job.id);
      const answer = await process(job);
      const result = await chrome.runtime.sendMessage({type: 'result', id: job.id, answer});
      if (result.error) throw new Error(result.error);
      button.textContent = 'LOCAL Agent 연결됨 (클릭하여 중지)';
    } catch (e) {
      button.textContent = e.message;
      if (job) {
        await chrome.runtime.sendMessage({type: 'result', id: job.id, error: e.message}).catch(() => {});
      }
    } finally {
      busy = false;
    }
  }, 1500);
})();
