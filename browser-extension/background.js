importScripts('config.js');
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (!sender.url?.startsWith('https://gemini.google.com/')) return;
  (async () => {
    const headers = {'X-Bridge-Token': BRIDGE_TOKEN, 'Content-Type': 'application/json'};
    if (message.type === 'poll') {
      const r = await fetch('http://127.0.0.1:8000/api/browser/pending', {headers});
      if (!r.ok) throw new Error('Local agent connection: ' + r.status);
      const data = await r.json();
      return data;
    }
    if (message.type === 'result') {
      const r = await fetch('http://127.0.0.1:8000/api/browser/result/' + encodeURIComponent(message.id), {
        method: 'POST', headers, body: JSON.stringify({answer: message.answer || '', error: message.error || ''})
      });
      if (!r.ok) throw new Error('Local agent result: ' + r.status);
      return {ok: true};
    }
    throw new Error('Unknown bridge request');
  })().then(respond).catch(e => respond({error: e.message}));
  return true;
});
