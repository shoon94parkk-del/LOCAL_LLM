importScripts('config.js');
let claimed = null;
let claimUntil = 0;
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (!sender.url?.startsWith('https://gemini.google.com/')) return;
  (async () => {
    const headers = {'X-Bridge-Token': BRIDGE_TOKEN, 'Content-Type': 'application/json'};
    if (message.type === 'poll') {
      if (claimed && Date.now() < claimUntil && claimed !== sender.tab.id) return {job: null};
      const r = await fetch('http://127.0.0.1:8000/api/browser/pending', {headers});
      if (!r.ok) throw new Error('Local agent connection: ' + r.status);
      const data = await r.json();
      if (data.job) { claimed = sender.tab.id; claimUntil = Date.now() + 300000; }
      return data;
    }
    if (message.type === 'result' && claimed === sender.tab.id) {
      const r = await fetch('http://127.0.0.1:8000/api/browser/result/' + encodeURIComponent(message.id), {
        method: 'POST', headers, body: JSON.stringify({answer: message.answer || '', error: message.error || ''})
      });
      claimed = null;
      if (!r.ok) throw new Error('Local agent result: ' + r.status);
      return {ok: true};
    }
    throw new Error('Unknown bridge request');
  })().then(respond).catch(e => respond({error: e.message}));
  return true;
});
