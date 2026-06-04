from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.storage import LOCAL_DB, Storage, utc_now


def main() -> None:
    store = Storage()
    if store.firestore is None:
        raise SystemExit(f"Firebase is not connected: {store.diagnostics()}")

    data = json.loads(LOCAL_DB.read_text(encoding="utf-8")) if LOCAL_DB.exists() else {}
    counts = {"news": 0, "logs": 0, "documents": 0, "ingestion_runs": 0}

    for item in data.get("news", []):
        if item.get("id"):
            store.firestore.collection("news").document(item["id"]).set(item, merge=True)
            counts["news"] += 1

    for idx, message in enumerate(data.get("logs", [])):
        log_id = uuid5(NAMESPACE_URL, f"ntkma-log:{message}:{idx}").hex
        store.firestore.collection("logs").document(log_id).set(
            {"id": log_id, "message": message, "created_at": utc_now()},
            merge=True,
        )
        counts["logs"] += 1

    for item in data.get("documents", []):
        doc_id = item.get("id") or uuid5(NAMESPACE_URL, json.dumps(item, sort_keys=True)).hex
        item["id"] = doc_id
        store.firestore.collection("documents").document(doc_id).set(item, merge=True)
        counts["documents"] += 1

    for item in data.get("ingestion_runs", []):
        run_id = item.get("id") or uuid5(NAMESPACE_URL, json.dumps(item, sort_keys=True)).hex
        item["id"] = run_id
        store.firestore.collection("ingestion_runs").document(run_id).set(item, merge=True)
        counts["ingestion_runs"] += 1

    print({"backend": store.backend_name(), "project_id": store.project_id, "migrated": counts})


if __name__ == "__main__":
    os.environ.setdefault("AUTO_SCRAPE_ENABLED", "false")
    main()
