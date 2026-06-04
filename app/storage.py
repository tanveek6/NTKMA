from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore, storage as firebase_storage

from .models import LogEntry, NewsItem


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
LOCAL_DB = DATA_DIR / "local_db.json"


EMPTY_DB = {"news": [], "logs": [], "documents": [], "ingestion_runs": []}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self) -> None:
        self.firebase_error = ""
        self.project_id = ""
        self.bucket_name = ""
        self.firestore = self._connect_firestore()
        self.bucket = self._connect_bucket()
        if self.firestore is None:
            self._ensure_local_db()

    def _credential_project_id(self, cred_path: str) -> str:
        try:
            return json.loads(Path(cred_path).read_text(encoding="utf-8")).get("project_id", "")
        except Exception:
            return ""

    def _candidate_bucket_names(self) -> list[str]:
        names = [
            os.getenv("FIREBASE_STORAGE_BUCKET", "").strip(),
            f"{self.project_id}.firebasestorage.app" if self.project_id else "",
            f"{self.project_id}.appspot.com" if self.project_id else "",
        ]
        return list(dict.fromkeys(name for name in names if name))

    def _credentials_path_from_env(self) -> str:
        cred_path = os.getenv("FIREBASE_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or ""
        cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON") or ""
        if cred_path:
            return cred_path
        if cred_json:
            path = Path(tempfile.gettempdir()) / "firebase-service-account.json"
            path.write_text(cred_json, encoding="utf-8")
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)
            os.environ["FIREBASE_CREDENTIALS"] = str(path)
            return str(path)
        return ""

    def _connect_firestore(self):
        cred_path = self._credentials_path_from_env()
        project_id = os.getenv("FIREBASE_PROJECT_ID") or (self._credential_project_id(cred_path) if cred_path else "")
        self.project_id = project_id
        bucket = os.getenv("FIREBASE_STORAGE_BUCKET") or (f"{project_id}.firebasestorage.app" if project_id else "")
        try:
            if cred_path and Path(cred_path).exists():
                if not firebase_admin._apps:
                    opts = {"storageBucket": bucket} if bucket else None
                    firebase_admin.initialize_app(credentials.Certificate(cred_path), opts)
                return firestore.client()
            if project_id:
                if not firebase_admin._apps:
                    opts = {"projectId": project_id}
                    if bucket:
                        opts["storageBucket"] = bucket
                    firebase_admin.initialize_app(options=opts)
                return firestore.client()
        except Exception as exc:
            self.firebase_error = str(exc)
            return None
        return None

    def _connect_bucket(self):
        if self.firestore is None:
            return None
        for bucket_name in self._candidate_bucket_names():
            try:
                bucket = firebase_storage.bucket(bucket_name)
                if bucket.exists():
                    self.bucket_name = bucket_name
                    return bucket
            except Exception as exc:
                self.firebase_error = str(exc)
        if self._candidate_bucket_names() and not self.firebase_error:
            self.firebase_error = "Firebase Storage bucket does not exist. Enable Firebase Storage or create a project bucket."
        return None

    def refresh_bucket(self) -> None:
        if self.bucket is None:
            self.bucket = self._connect_bucket()

    def _candidate_upload_buckets(self) -> list[Any]:
        self.refresh_bucket()
        buckets: list[Any] = []
        if self.bucket is not None:
            buckets.append(self.bucket)
        for bucket_name in self._candidate_bucket_names():
            if self.bucket is not None and bucket_name == self.bucket.name:
                continue
            try:
                bucket = firebase_storage.bucket(bucket_name)
                if bucket.exists():
                    buckets.append(bucket)
            except Exception as exc:
                self.firebase_error = str(exc)
        return buckets

    def _ensure_local_db(self) -> None:
        if not LOCAL_DB.exists():
            LOCAL_DB.write_text(json.dumps(EMPTY_DB, indent=2), encoding="utf-8")

    def _read_local(self) -> dict[str, Any]:
        self._ensure_local_db()
        return json.loads(LOCAL_DB.read_text(encoding="utf-8"))

    def _write_local(self, data: dict[str, Any]) -> None:
        LOCAL_DB.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def backend_name(self) -> str:
        return "firebase" if self.firestore is not None else "local-json"

    def diagnostics(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name(),
            "project_id": self.project_id,
            "credential_configured": bool(os.getenv("FIREBASE_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
            "firestore": self.firestore is not None,
            "storage_bucket": self.bucket_name if self.bucket is not None else "",
            "storage": self.bucket is not None,
            "error": self.firebase_error,
        }

    def list_news(self) -> list[dict[str, Any]]:
        if self.firestore is not None:
            docs = self.firestore.collection("news").order_by("date", direction=firestore.Query.DESCENDING).stream()
            return [doc.to_dict() | {"id": doc.id} for doc in docs]
        return sorted(self._read_local()["news"], key=lambda x: x.get("date", ""), reverse=True)

    def existing_keys(self) -> set[str]:
        keys: set[str] = set()
        for item in self.list_news():
            for field in ("duplicate_key", "canonical_url", "url", "raw_url", "title"):
                value = str(item.get(field, "")).lower().strip()
                if value:
                    keys.add(value)
        return keys

    def add_news(self, item: NewsItem) -> dict[str, Any]:
        payload = item.model_dump()
        payload["created_at"] = payload.get("created_at") or utc_now()
        payload["updated_at"] = utc_now()
        if self.firestore is not None:
            self.firestore.collection("news").document(payload["id"]).set(payload)
        else:
            data = self._read_local()
            data["news"].insert(0, payload)
            self._write_local(data)
        return payload

    def add_many_news(self, items: list[NewsItem]) -> list[dict[str, Any]]:
        return [self.add_news(item) for item in items]

    def upsert_unique_news(self, items: list[NewsItem]) -> tuple[list[dict[str, Any]], int]:
        keys = self.existing_keys()
        inserted: list[dict[str, Any]] = []
        duplicates = 0
        for item in items:
            key = (item.duplicate_key or item.canonical_url or item.url or item.title).lower()
            if key in keys:
                duplicates += 1
                continue
            inserted.append(self.add_news(item))
            keys.add(key)
        return inserted, duplicates

    def list_logs(self) -> list[str]:
        if self.firestore is not None:
            docs = self.firestore.collection("logs").order_by("created_at", direction=firestore.Query.DESCENDING).limit(100).stream()
            return [doc.to_dict().get("message", "") for doc in docs]
        return self._read_local().get("logs", [])[:100]

    def add_log(self, message: str) -> None:
        line = f"{datetime.now().strftime('%d-%m-%Y %H:%M:%S')} | {message}"
        if self.firestore is not None:
            entry = LogEntry(message=line, created_at=utc_now())
            self.firestore.collection("logs").document(entry.id).set(entry.model_dump())
        else:
            data = self._read_local()
            data.setdefault("logs", []).insert(0, line)
            data["logs"] = data["logs"][:100]
            self._write_local(data)

    def add_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload["id"] = payload.get("id") or f"doc_{datetime.now().timestamp()}"
        payload["created_at"] = payload.get("created_at") or utc_now()
        if self.firestore is not None:
            self.firestore.collection("documents").document(payload["id"]).set(payload)
        else:
            data = self._read_local()
            data.setdefault("documents", []).insert(0, payload)
            self._write_local(data)
        return payload

    def list_documents(self) -> list[dict[str, Any]]:
        if self.firestore is not None:
            docs = self.firestore.collection("documents").order_by("created_at", direction=firestore.Query.DESCENDING).stream()
            return [doc.to_dict() | {"id": doc.id} for doc in docs]
        return self._read_local().get("documents", [])

    def add_ingestion_run(self, payload: dict[str, Any]) -> None:
        payload["created_at"] = payload.get("created_at") or utc_now()
        if self.firestore is not None:
            self.firestore.collection("ingestion_runs").document(payload.get("id", utc_now())).set(payload)
        else:
            data = self._read_local()
            data.setdefault("ingestion_runs", []).insert(0, payload)
            data["ingestion_runs"] = data["ingestion_runs"][:100]
            self._write_local(data)

    def list_ingestion_runs(self) -> list[dict[str, Any]]:
        if self.firestore is not None:
            docs = self.firestore.collection("ingestion_runs").order_by("created_at", direction=firestore.Query.DESCENDING).limit(100).stream()
            return [doc.to_dict() | {"id": doc.id} for doc in docs]
        return self._read_local().get("ingestion_runs", [])[:100]

    def upload_file_to_firebase(self, local_path: Path, destination: str) -> str:
        if self.firestore is None:
            return ""
        last_error = ""
        for bucket in self._candidate_upload_buckets():
            try:
                blob = bucket.blob(destination)
                blob.upload_from_filename(str(local_path))
                self.bucket = bucket
                self.bucket_name = bucket.name
                return f"gs://{bucket.name}/{destination}"
            except Exception as exc:
                last_error = str(exc)
        self.firebase_error = last_error
        return ""

