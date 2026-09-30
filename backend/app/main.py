from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Skynex Food Rescue API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Skynex Food Rescue API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}

On Wed, 30 Sept 2026, 10:25 ELAKKIYA SELLI P ., <9125110014@kcgcollege.com> wrote:
skynex-food-rescue/
├── .github/
│   ├── workflows/ci.yml
│   ├── pull_request_template.md
│   └── ISSUE_TEMPLATE/
├── backend/
│   ├── app/ (main.py, routers/, models/, services/)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/   (Vite + React PWA)
├── docs/
├── docker-compose.yml
├── .gitignore
├── .env.example
└── README.md




