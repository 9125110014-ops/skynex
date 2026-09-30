"""SKYNEX - time-aware food redistribution API (FastAPI + MongoDB geo + Redis + WebSockets)."""
import asyncio, os, secrets
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
import redis.asyncio as aioredis

db = AsyncIOMotorClient(os.getenv("MONGO_URL", "mongodb://localhost:27017")).skynex
rds = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
OFFER_MINUTES = int(os.getenv("OFFER_MINUTES", "5"))
ADMIN_KEY = os.getenv("ADMIN_KEY", "change-me")
RADIUS_M = int(os.getenv("MATCH_RADIUS_M", "15000"))

app = FastAPI(title="SKYNEX Food Redistribution")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def oid(x):
    try:
        return ObjectId(x)
    except Exception:
        raise HTTPException(400, "Invalid id")


def ser(d):
    if isinstance(d, list): return [ser(x) for x in d]
    if isinstance(d, dict): return {k: ser(v) for k, v in d.items() if k not in ("otp", "queue")}
    if isinstance(d, ObjectId): return str(d)
    if isinstance(d, datetime): return d.isoformat() + "Z"
    return d


async def notify(user, text):
    """Hook point: send via FCM push, WhatsApp Cloud API or SMS (Twilio/MSG91). Prints in dev."""
    print(f"[notify -> {user.get('name')} {user.get('phone')}] {text}")


class UserIn(BaseModel):
    name: str
    role: str = Field(pattern="^(donor|ngo|volunteer)$")
    phone: str
    lat: float
    lng: float
    capacity: int = 100                 # people an NGO can feed
    avoid_allergens: list[str] = []     # allergens the NGO's recipients cannot have
    language: str = "en"


class ListingIn(BaseModel):
    donor_id: str
    title: str
    serves: int = Field(gt=0)
    allergens: list[str] = Field(min_length=1)   # mandatory declaration; use ["none"] if none
    safe_until: datetime
    lat: float
    lng: float
    photo_url: str | None = None


class DeliverIn(BaseModel):
    otp: str
    lat: float
    lng: float
    photo_url: str | None = None


@app.on_event("startup")
async def startup():
    await db.users.create_index([("loc", "2dsphere")])
    await db.listings.create_index("status")
    asyncio.create_task(expiry_loop())


# ---------- users ----------
@app.post("/users")
async def register(u: UserIn):
    doc = u.model_dump()
    doc.update(loc={"type": "Point", "coordinates": [u.lng, u.lat]},
               verified=(u.role != "ngo"))  # NGOs must be verified by an admin
    r = await db.users.insert_one(doc)
    doc["_id"] = r.inserted_id
    return ser(doc)


@app.post("/admin/verify/{uid}")
async def verify_ngo(uid: str, x_admin_key: str = Header("")):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(403, "Forbidden")
    await db.users.update_one({"_id": oid(uid)}, {"$set": {"verified": True}})
    return {"verified": True}


# ---------- matching ----------
async def build_queue(l):
    cur = db.users.find({
        "role": "ngo", "verified": True,
        "capacity": {"$gte": l["serves"]},
        "avoid_allergens": {"$nin": l["allergens"]},
        "loc": {"$near": {"$geometry": l["loc"], "$maxDistance": RADIUS_M}},
    }).limit(10)   # $near returns nearest first
    return [u["_id"] async for u in cur]


async def offer_next(lid):
    l = await db.listings.find_one({"_id": lid})
    i = l["offer_idx"] + 1
    # not enough time left to deliver -> stop
    if i >= len(l["queue"]) or l["safe_until"] < now() + timedelta(minutes=15):
        await db.listings.update_one({"_id": lid}, {"$set": {"status": "unmatched", "offered_to": None}})
        return
    ngo = await db.users.find_one({"_id": l["queue"][i]})
    expires = min(now() + timedelta(minutes=OFFER_MINUTES), l["safe_until"])
    await db.listings.update_one({"_id": lid}, {"$set": {
        "status": "offered", "offer_idx": i, "offered_to": ngo["_id"], "offer_expires": expires}})
    await notify(ngo, f"Food offer: {l['title']} (serves {l['serves']}). Claim before {expires:%H:%M} UTC.")


async def expiry_loop():
    """Countdown fallback: unclaimed offers move to the next recipient; spoiled food is closed."""
    while True:
        try:
            async for l in db.listings.find({"status": "offered", "offer_expires": {"$lt": now()}}):
                await offer_next(l["_id"])
            await db.listings.update_many(
                {"status": {"$in": ["offered", "claimed"]}, "safe_until": {"$lt": now()}},
                {"$set": {"status": "expired"}})
        except Exception as e:
            print("expiry_loop error", e)
        await asyncio.sleep(10)


# ---------- listings ----------
@app.post("/listings")
async def create_listing(b: ListingIn):
    donor = await db.users.find_one({"_id": oid(b.donor_id), "role": "donor"})
    if not donor:
        raise HTTPException(404, "Donor not found")
    su = b.safe_until.astimezone(timezone.utc).replace(tzinfo=None) if b.safe_until.tzinfo else b.safe_until
    if su <= now():
        raise HTTPException(400, "safe_until must be in the future")
    doc = b.model_dump()
    doc.update(safe_until=su, donor_id=donor["_id"], loc={"type": "Point", "coordinates": [b.lng, b.lat]},
               status="listed", offer_idx=-1, offered_to=None, created_at=now())
    doc.pop("lat"); doc.pop("lng")
    r = await db.listings.insert_one(doc)
    doc["_id"] = r.inserted_id
    doc["queue"] = await build_queue(doc)
    await db.listings.update_one({"_id": r.inserted_id}, {"$set": {"queue": doc["queue"]}})
    await offer_next(r.inserted_id)
    return ser(await db.listings.find_one({"_id": r.inserted_id}))


@app.get("/listings")
async def listings(donor_id: str | None = None):
    q = {"donor_id": oid(donor_id)} if donor_id else {}
    return ser(await db.listings.find(q).sort("safe_until", 1).to_list(100))


@app.get("/offers/{ngo_id}")
async def offers(ngo_id: str):
    q = {"offered_to": oid(ngo_id), "status": "offered"}
    return ser(await db.listings.find(q).sort("safe_until", 1).to_list(50))  # most urgent first


@app.get("/jobs")
async def jobs():
    """Claimed listings waiting for a volunteer."""
    return ser(await db.listings.find({"status": "claimed"}).sort("safe_until", 1).to_list(50))


@app.post("/listings/{lid}/claim")
async def claim(lid: str, ngo_id: str):
    l = await db.listings.find_one({"_id": oid(lid)})
    if (not l or l["status"] != "offered" or str(l["offered_to"]) != ngo_id
            or l["offer_expires"] < now()):
        raise HTTPException(409, "Offer is no longer available")
    if not await rds.set(f"claim:{lid}", ngo_id, nx=True, ex=3600):   # atomic first-accept lock
        raise HTTPException(409, "Already claimed")
    otp = f"{secrets.randbelow(10**6):06d}"
    await db.listings.update_one({"_id": l["_id"]}, {"$set": {
        "status": "claimed", "claimed_by": oid(ngo_id), "otp": otp}})
    donor = await db.users.find_one({"_id": l["donor_id"]})
    await notify(donor, f"'{l['title']}' was claimed. A volunteer will collect it soon.")
    return {"status": "claimed", "otp": otp}   # OTP is shown to the NGO only; volunteer asks for it at handover


@app.post("/listings/{lid}/pickup")
async def pickup(lid: str, volunteer_id: str):
    r = await db.listings.update_one({"_id": oid(lid), "status": "claimed"},
                                     {"$set": {"status": "in_transit", "volunteer_id": oid(volunteer_id),
                                               "picked_at": now()}})
    if not r.modified_count:
        raise HTTPException(409, "Not available for pickup")
    return {"status": "in_transit"}


@app.post("/listings/{lid}/deliver")
async def deliver(lid: str, b: DeliverIn):
    l = await db.listings.find_one({"_id": oid(lid), "status": "in_transit"})
    if not l:
        raise HTTPException(404, "No delivery in transit")
    if not secrets.compare_digest(l["otp"], b.otp):
        raise HTTPException(403, "Wrong OTP")
    await db.listings.update_one({"_id": l["_id"]}, {"$set": {
        "status": "delivered", "delivered_at": now(),
        "proof": {"lat": b.lat, "lng": b.lng, "photo_url": b.photo_url, "at": now()}}})
    return {"status": "delivered"}


@app.get("/stats")
async def stats():
    d = await db.listings.find({"status": "delivered"}).to_list(10000)
    meals = sum(x["serves"] for x in d)
    return {"deliveries": len(d), "meals_saved": meals, "co2e_kg_est": round(meals * 0.4 * 2.5, 1)}


# ---------- live tracking ----------
rooms: dict[str, set[WebSocket]] = {}


@app.websocket("/ws/track/{lid}")
async def track(ws: WebSocket, lid: str):
    """Volunteer sends {"lat":..,"lng":..}; donors and NGOs watching the same listing receive it."""
    await ws.accept()
    rooms.setdefault(lid, set()).add(ws)
    try:
        while True:
            msg = await ws.receive_text()
            for peer in list(rooms[lid]):
                if peer is not ws:
                    await peer.send_text(msg)
    except WebSocketDisconnect:
        rooms[lid].discard(ws)
