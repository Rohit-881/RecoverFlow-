"""
RecoverFlow AI — Backend API
Razorpay Buildathon 2026

A context-aware revenue recovery engine that:
1. Receives Razorpay webhooks (payment.failed, subscription.pending, etc.)
2. Scores recovery potential using ML features
3. Selects optimal intervention strategy
4. Executes bounded recovery with merchant rules
5. Tracks every rupee recovered with full audit trail

Run: uvicorn main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from seed import seed_data
from routers import merchants, metrics, transactions, webhooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed data on startup
    await seed_data()
    yield


app = FastAPI(title="RecoverFlow AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles

app.include_router(webhooks.router)
app.include_router(transactions.router)
app.include_router(metrics.router)
app.include_router(merchants.router)

# Mount current directory to serve dashboard.html
app.mount("/", StaticFiles(directory=".", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
