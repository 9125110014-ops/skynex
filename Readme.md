# SKYNEX - Food Redistribution Platform (Innothon'26)

Donors list surplus food with a safe-until time and allergen declaration. The API matches it to the nearest
verified NGOs with enough capacity and no allergen conflict, falls back to the next NGO if nobody claims in time,
and a volunteer delivers it with live tracking and an OTP-verified handover.

## Run locally
```bash
docker compose up --build
```
- App: http://localhost:5173
- API docs: http://localhost:8000/docs (or http://localhost:5173/api/docs)

Without Docker: start MongoDB and Redis, then
`cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
and `cd frontend && npm install && npm run dev`.

## Try the flow
1. Register an NGO (allow location), then verify it:
   `curl -X POST localhost:8000/admin/verify/<ngo_id> -H "x-admin-key: change-me"`
2. Register a donor (use another browser profile), post food.
3. The NGO sees the offer and claims it, and gets a handover code.
4. Register a volunteer, start pickup, enter the code to confirm delivery.

## Put it on GitHub
```bash
git init && git add . && git commit -m "SKYNEX initial commit"
git branch -M main
git remote add origin https://github.com/<your-user>/skynex-food-platform.git
git push -u origin main
```

## Built here vs planned
Built: geo matching, allergen filter, claim lock, timed fallback, OTP handover, live tracking socket, PWA shell, impact stats.
Still to add: WhatsApp/SMS/FCM in `notify()`, OSRM route batching + Leaflet map, OpenCV face match, photo upload,
donor verification, admin panel, and DPDP Act consent handling for face data.
Set `ADMIN_KEY` and restrict CORS before deploying.
