"""'Fichier supprimé' when staff print: documents must be stored durably (GridFS, shared by every backend instance,
kept across restarts) and stay readable until pickup — then deleted for that order only."""

import os
import shutil

from dotenv import load_dotenv
from pymongo import MongoClient

from tests.test_agent_notify import pair_agent
from tests.test_printers import fresh_owner, heartbeat
from tests.test_retention_pages import order_with, page_ids
from tests.test_stage1 import find_order

load_dotenv("/app/backend/.env")
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _doc(doc_id: str) -> dict:
    return mdb.documents.find_one({"id": doc_id}, {"_id": 0})


def test_documents_survive_local_disk_loss_and_live_until_pickup(client):
    owner, slug = fresh_owner()
    data, agent = pair_agent(owner, "PC cycle")
    heartbeat(agent, [{"name": "Imprimante cycle", "is_default": True, "status": "online"}])
    a = find_order(owner, order_with(client, slug, page_range="1-1", phone="0611111111")["code"])
    b = find_order(owner, order_with(client, slug, page_range="1-2", phone="0622222222")["code"])
    da, db_ = a["lines"][0]["document_id"], b["lines"][0]["document_id"]
    key = _doc(da)["storage_key"]
    assert key.startswith("gridfs:")
    # the container disk is ephemeral: wiping it must not lose any order document
    shutil.rmtree(os.environ.get("STORAGE_DIR", "/app/backend/storage_private"), ignore_errors=True)
    assert page_ids(owner.get(f"/orders/{a['id']}/documents/{da}/file?variant=original&disposition=inline").content) == [1, 2, 3, 4]
    assert page_ids(owner.get(f"/orders/{a['id']}/documents/{da}/file?variant=print").content) == [1]
    assert page_ids(owner.get(f"/orders/{b['id']}/documents/{db_}/file?variant=print").content) == [1, 2]
    # explicit print → agent gets only the selected pages, no error
    assert owner.post(f"/orders/{a['id']}/print-direct", json={"dry_check": False}).json()["ok"]
    job = agent.post("/agent/jobs/claim").json()["jobs"][0]
    f = agent.get(job["download_url"].removeprefix("/api"))
    assert f.status_code == 200 and page_ids(f.content) == [1]
    rep = agent.post(f"/agent/jobs/{job['id']}/report", json={"status": "printed", "lease_id": job["lease_id"]})
    assert rep.status_code == 200, rep.text
    # still available after printing / ready / paid, and the hourly retention leaves active orders alone
    owner.post(f"/orders/{a['id']}/status", json={"status": "ready"})
    owner.post(f"/orders/{a['id']}/pay", json={"method": "card_terminal"}).raise_for_status()
    secret = os.environ["WEBHOOK_CRON_SECRET"]
    client.post("/cron/retention", headers={"X-Cron-Secret": secret, "Authorization": f"Bearer {secret}"})
    assert owner.get(f"/orders/{a['id']}/documents/{da}/file?variant=print").status_code == 200
    # pickup of A deletes A's file only (idempotent), order history kept; B untouched
    r = owner.post(f"/orders/{a['id']}/status", json={"status": "picked_up"})
    assert r.status_code == 200, r.text
    assert mdb["files.files"].count_documents({"_id": __import__("bson").ObjectId(key[7:])}) == 0
    assert _doc(da)["status"] == "purged"
    after = owner.get(f"/orders/{a['id']}").json()
    assert after["purged_at"] and after["payment_status"] != "unpaid" and after["history"][-1]["status"] == "picked_up"
    assert owner.get(f"/orders/{a['id']}/documents/{da}/file").status_code == 410
    assert page_ids(owner.get(f"/orders/{b['id']}/documents/{db_}/file?variant=print").content) == [1, 2]
    owner.post(f"/agents/{data['agent_id']}/revoke")
