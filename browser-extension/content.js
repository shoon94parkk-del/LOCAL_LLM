(() => {
  let enabled = false, busy = false;
  const completed = new Set();
  const button = document.createElement('button');
  button.textContent = 'LOCAL Agent 연결 시작';
  Object.assign(button.style, {position:'fixed',right:'16px',bottom:'16px',zIndex:2147483647,padding:'12px',background:'#164d3f',color:'white',borderRadius:'8px'});
  document.body.appendChild(button);
  button.onclick = () => { enabled = !enabled; button.textContent = enabled ? 'LOCAL Agent 연결됨 (클릭하여 중지)' : 'LOCAL Agent 연결 시작'; };
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const inputSelector = 'div.ql-editor[contenteditable="true"][role="textbox"]';
  const answerSelector = 'message-content .markdown';
  const visible = e => e && e.getClientRects().length > 0;
  async function process(job) {
    const input = document.querySelector(inputSelector);
    if (!input) throw new Error('Gemini 입력창을 찾을 수 없습니다. 로그인/페이지 상태를 확인하세요.');
    if (input.innerText.trim()) throw new Error('입력창에 작성 중인 내용이 있습니다. 비운 뒤 다시 실행하세요.');
    const before = document.querySelectorAll(answerSelector).length;
    input.focus();
    document.execCommand('insertText', false, job.prompt);
    input.dispatchEvent(new Event('input', {bubbles:true}));
    await delay(500);
    const send = document.querySelector('button[aria-label="메시지 보내기"],button[aria-label="Send message"]');
    if (!send || send.disabled) throw new Error('Gemini 전송 버튼을 찾을 수 없습니다.');
    send.click();
    const deadline = Date.now() + 240000;
    let previous = '', stableSince = Date.now();
    while (Date.now() < deadline) {
      await delay(1000);
      const answers = document.querySelectorAll(answerSelector);
      if (answers.length <= before) continue;
      const text = answers[answers.length - 1].innerText.trim();
      const stop = document.querySelector('button[aria-label="대답 생성 중지"],button[aria-label="Stop response"]');
      if (text !== previous || visible(stop)) { previous = text; stableSince = Date.now(); }
      if (text && !visible(stop) && Date.now() - stableSince >= 5000) return text;
    }
    throw new Error('Gemini 응답 시간 초과. 사용량 제한 또는 로그인 상태를 확인하세요.');
  }
  setInterval(async () => {
    if (!enabled || busy) return;
    busy = true;
    let job;
    try {
      const data = await chrome.runtime.sendMessage({type:'poll'});
      if (data.error) { button.textContent = data.error; return; }
      job = data.job;
      if (!job || completed.has(job.id)) return;
      completed.add(job.id);
      const answer = await process(job);
      const result = await chrome.runtime.sendMessage({type:'result', id:job.id, answer});
      if (result.error) throw new Error(result.error);
      button.textContent = 'LOCAL Agent 연결됨 (클릭하여 중지)';
    } catch (e) {
      button.textContent = e.message;
      if (job) await chrome.runtime.sendMessage({type:'result',id:job.id,error:e.message}).catch(()=>{});
    } finally { busy = false; }
  }, 1500);
})();
