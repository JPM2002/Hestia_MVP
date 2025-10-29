import os

class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-env")
    ENABLE_TECH_DEMO = os.getenv("ENABLE_TECH_DEMO", "0") == "1"

    # DB
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or None  # postgres DSN or None
    DATABASE_PATH = os.getenv("DATABASE_PATH", "hestia_V2.db")
    PG_POOL_MAX = int(os.getenv("PG_POOL_MAX", "2"))   # keep tiny if using pooler
    PG_STMT_TIMEOUT_MS = os.getenv("PG_STMT_TIMEOUT_MS")  # optional

    # WA notifications (external webhook)
    WA_NOTIFY_BASE = (os.getenv("WA_NOTIFY_BASE", "").rstrip("/") or None)
    WA_NOTIFY_TOKEN = os.getenv("WA_NOTIFY_TOKEN", "200220022002")

    # SLA default target (only used in later Phase 2 KPIs)
    SLA_TARGET = float(os.getenv("SLA_TARGET", "0.90"))  # 0.0–1.0
