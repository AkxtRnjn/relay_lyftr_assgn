import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

const base = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const newId = () => crypto.randomUUID();
const samples = ['Explain why the sky is blue in two sentences.', 'Help me plan a weekend learning Python.'];

const historyKey = 'relay.recent.v1:' + base;
function readRecent() {
  try {
    const rows = JSON.parse(localStorage.getItem(historyKey) || '[]');
    return rows.filter(row => row && typeof row.id === 'string' && typeof row.title === 'string');
  } catch { return []; }
}

function Mark() {
  return <span aria-hidden="true" className="mark"><i/><i/><i/></span>;
}

function Reply({message}) {
  const m = message.metadata;
  const fields = [
    ['Source', 'source', m.resolution_source], ['Model', 'model', m.model],
    ['Latency', 'latency', m.latency_ms + ' ms'], ['Input tokens', 'input-tokens', m.input_tokens],
    ['Output tokens', 'output-tokens', m.output_tokens],
  ];
  return <article data-testid="assistant-message"><h3><Mark/> Relay</h3><p>{message.content}</p>
    <dl>{fields.map(([label, id, value]) => <div key={id}><dt>{label}</dt><dd data-testid={'meta-' + id}>{value}</dd></div>)}</dl>
  </article>;
}

function App() {
  const [sid, setSid] = useState(newId);
  const [turns, setTurns] = useState([]);
  const [input, setInput] = useState('');
  const [prompt, setPrompt] = useState('');
  const [recent, setRecent] = useState(readRecent);
  const [lookup, setLookup] = useState('');
  const [opening, setOpening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [health, setHealth] = useState(null);
  const bottom = useRef(null), field = useRef(null), sending = useRef(false);
  useEffect(() => {
    const ctrl = new AbortController();
    const probe = async () => {
      try {
        const r = await fetch(base + '/health', {signal: ctrl.signal});
        if (!r.ok) throw Error();
        const data = await r.json();
        if (!ctrl.signal.aborted) setHealth(data);
      } catch { if (!ctrl.signal.aborted) setHealth(false); }
    };
    probe();
    const timer = setInterval(probe, 30000);
    return () => { clearInterval(timer); ctrl.abort(); };
  }, []);
  useEffect(() => { bottom.current?.scrollIntoView({block:'nearest'}); }, [turns, busy, error]);
  function remember(id, firstMessage) {
    const entry = {id, title:firstMessage.slice(0, 72)};
    const merged = new Map([...readRecent(), ...recent].map(row => [row.id, row]));
    merged.delete(id);
    const next = [entry, ...merged.values()];
    setRecent(next);
    try { localStorage.setItem(historyKey, JSON.stringify(next)); } catch { /* Session remains available in this tab. */ }
  }
  async function openChat(id) {
    if (!id || sending.current) return;
    sending.current = true; setBusy(true); setOpening(true); setError('');
    try {
      const response = await fetch(base + '/sessions/' + encodeURIComponent(id) + '/messages');
      if (!response.ok) throw Error(response.status === 404 ? 'No saved chat has that session ID.' : 'Could not load chat history.');
      const {messages} = await response.json();
      setSid(id); setTurns(messages); setPrompt(''); setInput(''); setLookup('');
      remember(id, messages.find(m => m.role === 'user')?.content || id);
    } catch (err) { setError(err.message); }
    finally { sending.current = false; setBusy(false); setOpening(false); }
  }
  function reset() {
    setSid(newId()); setTurns([]); setPrompt(''); setInput(''); setError(''); field.current?.focus();
  }
  async function send(e) {
    e?.preventDefault();
    const message = input.trim();
    if (!message || sending.current) return;
    sending.current = true; setBusy(true); setError(''); setInput('');
    setTurns(t => [...t, {role:'user', content:message}]);
    try {
      const r = await fetch(base + '/chat', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({session_id:sid, message, ...(prompt.trim() && {system_prompt:prompt.trim()})})});
      const data = await r.json();
      if (!r.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Please check your message and try again.');
      setTurns(t => [...t, {role:'assistant', content:data.reply, metadata:data.metadata}]);
      remember(sid, turns[0]?.content || message);
    } catch (err) {
      setTurns(t => t.slice(0, -1)); setInput(message);
      setError(err.message === 'Failed to fetch' ? 'Could not reach the backend. Check the connection and retry.' : err.message);
    } finally { sending.current = false; setBusy(false); }
  }
  return <><header><strong><Mark/> Relay</strong><span>Lyftr AI</span></header>
    <div className="shell"><aside><div className="tag">WORKSPACE</div><h2>Session</h2>
      <button className="new" onClick={reset} disabled={busy}>＋ New chat</button>
      <div className="history"><label>Recent chats<select aria-label="Recent chats" value={recent.some(row => row.id === sid) ? sid : ''} disabled={busy || !recent.length} onChange={e => openChat(e.target.value)}>
        <option value="" disabled>Select a saved chat</option>
        {recent.map(row => <option key={row.id} value={row.id}>{row.title} · {row.id.slice(-6)}</option>)}
      </select></label>
      <details><summary>Open by session ID</summary><label>Session ID<input value={lookup} maxLength={128} onChange={e=>setLookup(e.target.value)}/></label>
        <button type="button" disabled={busy || !lookup.trim()} onClick={()=>openChat(lookup.trim())}>Open chat</button></details></div>
      <div className="info"><small>Session ID</small><code>{sid}</code></div>
      <div className="info"><small>Gateway</small><b>{health ? '● Online' : health === false ? 'Unavailable' : 'Connecting…'}</b>
      {health && <small>{health.keys_configured} keys configured</small>}</div>
      <label className="info"><small>System prompt</small><textarea data-testid="system-prompt-input" placeholder={turns.length ? "Using saved session prompt" : "You are a helpful assistant."} value={prompt} disabled={busy || turns.length > 0} onChange={e=>setPrompt(e.target.value)}/></label>
    </aside><main><div className="chat" role="log" aria-label="Conversation">
      {!turns.length && <section className="intro"><div className="signal" aria-hidden="true">{Array.from({length:44}, (_,i)=><i key={i} style={{height:8+Math.abs(Math.sin(i*.22)*Math.cos(i*.47))*68}}/>)}</div>
        <div className="tag">CONVERSATION</div><h1>Start a chat.</h1><p>Ask a question, then explore how Relay answered it.</p>
        <div className="samples">{samples.map(s=><button key={s} onClick={()=>{setInput(s);field.current?.focus();}}>{s} ↗</button>)}</div></section>}
      {turns.map((m,i)=>m.role==='assistant'?<Reply message={m} key={i}/>:<article className="user" key={i}><h3>You</h3><p>{m.content}</p></article>)}
      {busy && <p role="status">{opening ? 'Loading chat…' : 'Relay is thinking…'}</p>}{error && <p role="alert">{error}</p>}<div ref={bottom}/>
      </div><form onSubmit={send}><textarea ref={field} aria-label="Message" data-testid="chat-input" placeholder="Message Relay…" maxLength={4000} value={input} disabled={busy} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();send();}}}/>
      <div className="actions"><small>Shift + Enter for a new line</small><button data-testid="send-button" disabled={busy || !input.trim()}>Send ↑</button></div></form></main></div></>;
}
createRoot(document.getElementById('root')).render(<App/>);
