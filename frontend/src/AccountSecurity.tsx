import {useEffect,useState} from 'react';
import {api,send} from './api';

type Status={enabled:boolean};
export default function AccountSecurity() {
  const [enabled,setEnabled]=useState(false),[password,setPassword]=useState(''),
    [code,setCode]=useState(''),[secret,setSecret]=useState(''),[uri,setUri]=useState(''),
    [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
  const path='/api/v1/auth/mfa';
  useEffect(()=>{api<Status>(path+'/status').then(v=>setEnabled(v.enabled)).catch(e=>setError(String(e)));},[]);
  async function run(work:()=>Promise<void>) {
    setBusy(true);setError('');setMessage('');
    try {await work();} catch(e){setError(e instanceof Error?e.message:'Request failed');}
    finally {setBusy(false);}
  }
  async function setup(){await run(async()=>{
    const result=await send<{secret:string;provisioning_uri:string}>(path+'/setup',{password});
    setSecret(result.secret);setUri(result.provisioning_uri);setMessage('Enter the six-digit code from your authenticator to enable MFA.');
  });}
  async function enable(){await run(async()=>{
    await send(path+'/enable',{code});setEnabled(true);setSecret('');setUri('');setCode('');
    setMessage('Authenticator enabled. Existing sessions were revoked; sign in again with your password and code.');
  });}
  async function disable(){await run(async()=>{
    await send(path+'/disable',{password,code});setEnabled(false);setCode('');
    setMessage('Authenticator disabled. Existing sessions were revoked.');
  });}
  return <section className="panel mt-4" aria-label="Account security">
    <div className="panel-heading"><h2>Account security</h2>
      <span className={`badge ${enabled?'text-bg-success':'text-bg-secondary'}`}>{enabled?'Authenticator enabled':'Not enabled'}</span></div>
    <p>Protect your account with a six-digit code from an authenticator app. Keep your account recovery process with your administrator.</p>
    <div className="row g-3">
      <div className="col-12 col-md-6"><label className="field">Current account password
        <input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label></div>
      <div className="col-12 col-md-6"><label className="field">Authenticator code
        <input value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,'').slice(0,6))} inputMode="numeric" autoComplete="one-time-code" placeholder="6 digits"/></label></div>
    </div>
    {secret&&<div className="alert alert-warning mt-3"><strong>Enroll authenticator</strong>
      <p className="my-2">Add this secret manually in your authenticator app. Do not share it.</p>
      <code className="user-select-all">{secret}</code>
      <details className="mt-2"><summary>Manual provisioning URI</summary><code className="text-break">{uri}</code></details>
    </div>}
    <div className="d-flex gap-2 mt-3 flex-wrap">
      {!enabled&&!secret&&<button className="primary" disabled={busy||!password} onClick={setup}>Set up authenticator</button>}
      {!enabled&&!!secret&&<button className="primary" disabled={busy||code.length!==6} onClick={enable}>Verify and enable</button>}
      {enabled&&<button className="secondary" disabled={busy||!password||code.length!==6} onClick={disable}>Disable authenticator</button>}
    </div>
    {message&&<div role="status" className="alert alert-info mt-3">{message}</div>}
    {error&&<div role="alert" className="alert alert-danger mt-3">{error}</div>}
  </section>;
}
