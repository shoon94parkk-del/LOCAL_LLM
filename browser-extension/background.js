importScripts('config.js');

const configuredOrigin = typeof GLM_WEB_ORIGIN === 'string'
  ? GLM_WEB_ORIGIN.replace(/\/$/, '')
  : '';

function senderAllowed(sender) {
  if (!sender.url || !configuredOrigin) return false;
  try {
    return new URL(sender.url).origin === configuredOrigin;
  } catch (_) {
    return false;
  }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.type === 'authorize') {
    respond({ok: senderAllowed(sender)});
    return;
  }
  if (!senderAllowed(sender)) {
    respond({error: '이 페이지는 LOCAL Agent 연결 대상으로 설정되지 않았습니다.'});
    return;
  }

  (async () => {
    const headers = {
      'X-Bridge-Token': BRIDGE_TOKEN,
      'Content-Type': 'application/json'
    };
    if (message.type === 'poll') {
      const r = await fetch('http://127.0.0.1:8000/api/browser/pending', {headers});
      if (!r.ok) throw new Error('Local agent connection: ' + r.status);
      return r.json();
    }
    if (message.type === 'result') {
      const r = await fetch(
        'http://127.0.0.1:8000/api/browser/result/' + encodeURIComponent(message.id),
        {
          method: 'POST',
          headers,
          body: JSON.stringify({answer: message.answer || '', error: message.error || ''})
        }
      );
      if (!r.ok) throw new Error('Local agent result: ' + r.status);
      return {ok: true};
    }
    throw new Error('Unknown bridge request');
  })().then(respond).catch(e => respond({error: e.message}));
  return true;
});
