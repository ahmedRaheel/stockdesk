import { useEffect, useState } from 'react';
import { api, send } from './api';
import { newRequestId } from './requestId';

type Location = { id: string; code: string; name: string; kind: string };
type Balance = { location: string; product: string; quantity: number };
type Product = { id: string; name: string; stock: number };

export default function OperationsDesk({tenant, products}: {tenant: string; products: Product[]}) {
  const base = `/api/v1/tenants/${tenant}`;
  const [locations, setLocations] = useState<Location[]>([]);
  const [balances, setBalances] = useState<Balance[]>([]);
  const [transfers, setTransfers] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [newCode, setNewCode] = useState('');
  const [newName, setNewName] = useState('');
  const [newKind, setNewKind] = useState<'store'|'warehouse'>('warehouse');
  const [source, setSource] = useState('');
  const [destination, setDestination] = useState('');
  const [product, setProduct] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [operation, setOperation] = useState<'allocate'|'transfer'>('allocate');
  async function refresh() {
    const [l, b, t] = await Promise.all([
      api<{items: Location[]}>(base+'/locations'),
      api<{items: Balance[]}>(base+'/warehouse-stock'),
      api<{items: any[]}>(base+'/warehouse-transfers'),
    ]);
    setLocations(l.items); setBalances(b.items); setTransfers(t.items);
  }
  useEffect(() => {refresh().catch(e => setError(e.message));}, [tenant]);
  async function createLocation(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      await send(base+'/locations', {code:newCode.trim(),name:newName.trim(),kind:newKind});
      setNewCode(''); setNewName(''); setMessage('Location created.'); await refresh();
    } catch(e:any) {setError(e.message);} finally {setBusy(false);}
  }
  async function stockAction(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      if (operation==='allocate') {
        await send(base+'/warehouse-stock/allocate', {request:newRequestId(),location:destination,product,quantity});
      } else {
        await send(base+'/warehouse-transfers', {request:newRequestId(),source,destination,lines:[{product,quantity}]});
      }
      setMessage(operation==='allocate'?'Stock assigned.':'Transfer posted.'); await refresh();
    } catch(e:any) {setError(e.message);} finally {setBusy(false);}
  }
  return <div className="operations-desk container-fluid px-0">
    <section className="panel mb-4">
      <h2>Stores & warehouses</h2>
      <p>Locations are isolated by business. Transfers preserve the total stock across locations. Assign existing stock to a location before making a transfer.</p>
      {error && <p role="alert" className="form-error">{error}</p>}
      {message && <p role="status">{message}</p>}
      <form onSubmit={createLocation} className="toolbar">
        <label>Code<input required maxLength={30} value={newCode} onChange={e=>setNewCode(e.target.value)} placeholder="KHI-01" /></label>
        <label>Location name<input required maxLength={120} value={newName} onChange={e=>setNewName(e.target.value)} placeholder="Main store" /></label>
        <label>Type<select value={newKind} onChange={e=>setNewKind(e.target.value as 'store'|'warehouse')}><option value="warehouse">Warehouse</option><option value="store">Store</option></select></label>
        <button disabled={busy}>Add location</button>
      </form>
      <div className="d-flex flex-wrap gap-2 mt-3">{locations.map(l=><span className="badge text-bg-light border p-2" key={l.id}>{l.code} · {l.name} · {l.kind}</span>)}</div>
    </section>
    <section className="panel mb-4">
      <h2>Stock assignment & transfers</h2>
      <form onSubmit={stockAction} className="toolbar">
        <label>Operation<select value={operation} onChange={e=>setOperation(e.target.value as 'allocate'|'transfer')}><option value="allocate">Assign existing stock</option><option value="transfer">Transfer stock</option></select></label>
        {operation==='transfer'&&<label>From<select required value={source} onChange={e=>setSource(e.target.value)}><option value="">Select source</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>}
        <label>{operation==='allocate'?'Assign to':'Destination'}<select required value={destination} onChange={e=>setDestination(e.target.value)}><option value="">Select location</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        <label>Product<select required value={product} onChange={e=>setProduct(e.target.value)}><option value="">Select product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Quantity<input type="number" required min="0.001" step="0.001" value={quantity} onChange={e=>setQuantity(e.target.value)} /></label>
        <button disabled={busy || (operation==='transfer'&&source===destination)}>Post {operation==='allocate'?'assignment':'transfer'}</button>
      </form>
      <h3>Location balances</h3>
      <div className="table-responsive"><table className="table table-hover align-middle"><thead><tr><th>Location</th><th>Product</th><th>Qty</th></tr></thead><tbody>{balances.map(b=><tr key={b.location+':'+b.product}><td>{locations.find(l=>l.id===b.location)?.name||b.location}</td><td>{products.find(p=>p.id===b.product)?.name||b.product}</td><td>{b.quantity}</td></tr>)}</tbody></table></div>
      <h3>Recent transfers</h3>
      <ul>{transfers.slice(0,20).map(t=><li key={t.id}>{locations.find(l=>l.id===t.source)?.name||t.source} → {locations.find(l=>l.id===t.destination)?.name||t.destination} · {new Date(t.created).toLocaleString()}</li>)}</ul>
    </section>
    <p><strong>Reconciliation note:</strong> Location balances are currently separate from legacy POS sales and purchase stock movement allocation. Reconcile and integrate location-aware checkout before using this as a multi-store production inventory source of truth.</p>
  </div>;
}
