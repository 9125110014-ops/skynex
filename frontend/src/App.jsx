import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API || "/api";
const call = async (path, opts = {}) => {
  const r = await fetch(API + path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
};
const here = () =>
  new Promise(res =>
    navigator.geolocation
      ? navigator.geolocation.getCurrentPosition(
          p => res([p.coords.latitude, p.coords.longitude]),
          () => res([13.0827, 80.2707]))
      : res([13.0827, 80.2707]));
const left = iso => Math.max(0, Math.round((new Date(iso) - Date.now()) / 60000));

function Register({ onDone }) {
  const [f, setF] = useState({ name: "", phone: "", role: "donor", capacity: 100, avoid: "" });
  const set = k => e => setF({ ...f, [k]: e.target.value });
  const go = async () => {
    const [lat, lng] = await here();
    const u = await call("/users", { method: "POST", body: {
      name: f.name, phone: f.phone, role: f.role, lat, lng, capacity: +f.capacity,
      avoid_allergens: f.avoid.split(",").map(s => s.trim().toLowerCase()).filter(Boolean) } });
    localStorage.setItem("user", JSON.stringify(u));
    onDone(u);
  };
  return (
    <div className="card">
      <h2>Join SKYNEX</h2>
      <input placeholder="Name" value={f.name} onChange={set("name")} />
      <input placeholder="Phone" value={f.phone} onChange={set("phone")} />
      <select value={f.role} onChange={set("role")}>
        <option value="donor">Donor (restaurant, event, home)</option>
        <option value="ngo">NGO / shelter / community kitchen</option>
        <option value="volunteer">Volunteer</option>
      </select>
      {f.role === "ngo" && <>
        <input type="number" placeholder="People you can feed" value={f.capacity} onChange={set("capacity")} />
        <input placeholder="Allergens to avoid (comma separated)" value={f.avoid} onChange={set("avoid")} />
        <p>An admin must verify your NGO before you receive offers.</p>
      </>}
      <button onClick={go}>Register</button>
    </div>
  );
}

function Donor({ user }) {
  const [f, setF] = useState({ title: "", serves: 10, allergens: "", hours: 3 });
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");
  const load = () => call(`/listings?donor_id=${user._id}`).then(setItems);
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, []);
  const post = async () => {
    setErr("");
    try {
      const [lat, lng] = await here();
      await call("/listings", { method: "POST", body: {
        donor_id: user._id, title: f.title, serves: +f.serves, lat, lng,
        allergens: f.allergens.split(",").map(s => s.trim().toLowerCase()).filter(Boolean),
        safe_until: new Date(Date.now() + f.hours * 3600e3).toISOString() } });
      load();
    } catch (e) { setErr(e.message); }
  };
  return (
    <>
      <div className="card">
        <h2>Post surplus food</h2>
        <input placeholder="What food is it?" value={f.title} onChange={e => setF({ ...f, title: e.target.value })} />
        <input type="number" placeholder="Serves how many people" value={f.serves} onChange={e => setF({ ...f, serves: e.target.value })} />
        <input placeholder='Allergens (required, type "none" if none)' value={f.allergens} onChange={e => setF({ ...f, allergens: e.target.value })} />
        <input type="number" placeholder="Safe to eat for (hours)" value={f.hours} onChange={e => setF({ ...f, hours: e.target.value })} />
        {err && <p className="warn">{err}</p>}
        <button onClick={post}>Post food</button>
      </div>
      {items.length === 0 && <p>No listings yet. Post your first surplus above.</p>}
      {items.map(i => (
        <div className="card" key={i._id}>
          <b>{i.title}</b> - serves {i.serves}<br />
          Status: {i.status} | Safe for {left(i.safe_until)} more min | Allergens: {i.allergens.join(", ")}
        </div>
      ))}
    </>
  );
}

function Ngo({ user }) {
  const [offers, setOffers] = useState([]);
  const [otps, setOtps] = useState({});
  const load = () => call(`/offers/${user._id}`).then(setOffers);
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);
  const claim = async id => {
    try {
      const r = await call(`/listings/${id}/claim?ngo_id=${user._id}`, { method: "POST" });
      setOtps({ ...otps, [id]: r.otp });
      load();
    } catch (e) { alert(e.message); }
  };
  return (
    <>
      <h2>Offers for you</h2>
      {offers.length === 0 && Object.keys(otps).length === 0 && <p>No offers right now. New ones appear here automatically.</p>}
      {offers.map(o => (
        <div className="card" key={o._id}>
          <b>{o.title}</b> - serves {o.serves}<br />
          Allergens: <b>{o.allergens.join(", ")}</b><br />
          Safe for {left(o.safe_until)} more min | Claim within {left(o.offer_expires)} min
          <div><button onClick={() => claim(o._id)}>Claim food</button></div>
        </div>
      ))}
      {Object.entries(otps).map(([id, otp]) => (
        <div className="card" key={id}>Claimed. Give this handover code to the volunteer: <b>{otp}</b></div>
      ))}
    </>
  );
}

function Volunteer({ user }) {
  const [jobs, setJobs] = useState([]);
  const [otp, setOtp] = useState({});
  const load = () => call("/jobs").then(setJobs);
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);
  const pick = async id => {
    await call(`/listings/${id}/pickup?volunteer_id=${user._id}`, { method: "POST" });
    const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + API + `/ws/track/${id}`);
    ws.onopen = () => navigator.geolocation.watchPosition(p =>
      ws.readyState === 1 && ws.send(JSON.stringify({ lat: p.coords.latitude, lng: p.coords.longitude })));
    load();
  };
  const done = async id => {
    const [lat, lng] = await here();
    try { await call(`/listings/${id}/deliver`, { method: "POST", body: { otp: otp[id] || "", lat, lng } }); load(); }
    catch (e) { alert(e.message); }
  };
  return (
    <>
      <h2>Pickups waiting</h2>
      {jobs.length === 0 && <p>No pickups waiting. Check back soon.</p>}
      {jobs.map(j => (
        <div className="card" key={j._id}>
          <b>{j.title}</b> - safe for {left(j.safe_until)} more min<br />
          <button onClick={() => pick(j._id)}>Start pickup</button>
          <input placeholder="Handover code from NGO" onChange={e => setOtp({ ...otp, [j._id]: e.target.value })} />
          <button onClick={() => done(j._id)}>Confirm delivery</button>
        </div>
      ))}
    </>
  );
}

function Impact() {
  const [s, setS] = useState(null);
  useEffect(() => { call("/stats").then(setS); }, []);
  return s ? (
    <div className="card">
      <h2>Impact so far</h2>
      {s.meals_saved} meals saved across {s.deliveries} deliveries (about {s.co2e_kg_est} kg CO2e avoided).
    </div>
  ) : null;
}

export default function App() {
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem("user") || "null"));
  const [tab, setTab] = useState("home");
  if (!user) return <main><h1>SKYNEX</h1><Register onDone={setUser} /></main>;
  const View = { donor: Donor, ngo: Ngo, volunteer: Volunteer }[user.role];
  return (
    <main>
      <h1>SKYNEX</h1>
      <nav>
        <button className={tab === "home" ? "" : "off"} onClick={() => setTab("home")}>My work</button>
        <button className={tab === "impact" ? "" : "off"} onClick={() => setTab("impact")}>Impact</button>
        <button className="off" onClick={() => { localStorage.removeItem("user"); setUser(null); }}>Sign out</button>
      </nav>
      <p>{user.name} ({user.role})</p>
      {tab === "home" ? <View user={user} /> : <Impact />}
    </main>
  );
}
