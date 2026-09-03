"""Restore canonical test environment: single admin, no lockouts, kill switch engaged."""
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/app/frontend/.env")
be = dotenv_values("/app/app/backend/.env")
BASE = fe["REACT_APP_BACKEND_URL"].rstrip("/")
TOKEN = be["ARBICORE_BOOTSTRAP_TOKEN"].strip()
db = MongoClient(be.get("MONGO_URL") or "mongodb://localhost:27017")[be.get("DB_NAME") or "arbicore_x"]

USER, PW = "admin", "ArbiCoreAdmin2026"

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"username": USER, "password": PW}, timeout=30)
if r.status_code != 200:
    db.users.delete_many({})
    db.settings.delete_many({"key": "auth_bootstrap_lock"})
    db.login_attempts.delete_many({})
    r = s.post(f"{BASE}/api/auth/setup", json={"username": USER, "password": PW},
               headers={"X-Bootstrap-Token": TOKEN}, timeout=30)
    print("bootstrap:", r.status_code, r.text[:200])
db.login_attempts.delete_many({})
s = requests.Session()
print("login:", s.post(f"{BASE}/api/auth/login", json={"username": USER, "password": PW}, timeout=30).status_code)

st = requests.get(f"{BASE}/api/arbicore/safety/status", timeout=30).json()
if not (st.get("kill") or {}).get("engaged"):
    e = s.post(f"{BASE}/api/arbicore/safety/kill/engage",
               params={"reason": "restore_fail_closed_posture"}, timeout=30)
    print("engage:", e.status_code, e.text[:200])
st = requests.get(f"{BASE}/api/arbicore/safety/status", timeout=30).json()
print("users:", db.users.count_documents({}), "attempts:", db.login_attempts.count_documents({}))
print("live_execution_enabled:", st.get("live_execution_enabled"), "kill.engaged:", (st.get("kill") or {}).get("engaged"))
