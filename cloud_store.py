# cloud_store.py
import os, json, uuid
from datetime import datetime

try:
    from supabase import create_client
except ImportError:  # Optional dependency for local-only mode.
    create_client = None


def read_json(path: str, fallback=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


class CloudStore:
    """
    Minimal cloud save store.

    Identity is a stable user_id stored on disk (no Supabase auth).
    For your use-case (single person), you will make this user_id the SAME
    on every device (by copying the json file or setting it manually).
    """

    def __init__(self, *, url: str, anon_key: str, table: str, storage_dir: str):
        self.url = (url or "").strip()
        self.anon_key = (anon_key or "").strip()
        self.table = table
        self.storage_dir = storage_dir

        # this file is the whole reason you got multiple rows (each device generated a new one)
        self.user_id_path = os.path.join(storage_dir, "user_id.json")

        self.sb = None
        self.user_id = self._load_or_create_user_id()

    def enabled(self) -> bool:
        return bool(self.url and self.anon_key and create_client is not None)

    def connect(self):
        if not self.enabled():
            return None
        if self.sb is None:
            self.sb = create_client(self.url, self.anon_key)
        return self.sb

    def _load_or_create_user_id(self) -> str:
        obj = read_json(self.user_id_path, None)
        if isinstance(obj, dict) and obj.get("user_id"):
            return str(obj["user_id"])

        new_id = str(uuid.uuid4())
        write_json(self.user_id_path, {"user_id": new_id})
        return new_id

    def get_user_id(self) -> str:
        return self.user_id

    def set_user_id(self, uid: str):
        uid = (uid or "").strip()
        if not uid:
            raise ValueError("user_id cannot be empty")
        # basic sanity check: uuid format
        try:
            uuid.UUID(uid)
        except Exception as e:
            raise ValueError("user_id must be a valid UUID string") from e

        self.user_id = uid
        write_json(self.user_id_path, {"user_id": uid})

    # List saves for the CURRENT user_id
    def list_slots(self):
        try:
            sb = self.connect()
            if not sb:
                return []

            resp = (
                sb.table(self.table)
                .select("id,user_id,slot,name,updated_at,data")
                .eq("user_id", self.user_id)
                .order("updated_at", desc=True)
                .execute()
            )
            rows = getattr(resp, "data", None) or []
            if isinstance(rows, dict):
                rows = [rows]
            return rows
        except Exception:
            return []

    def pull(self, slot: str):
        try:
            sb = self.connect()
            if not sb:
                return None
            slot = (slot or "default").strip()

            resp = (
                sb.table(self.table)
                .select("data,updated_at")
                .eq("user_id", self.user_id)
                .eq("slot", slot)
                .limit(1)
                .execute()
            )
            rows = getattr(resp, "data", None) or []
            if isinstance(rows, dict):
                rows = [rows]
            if not rows:
                return None
            return rows[0].get("data")
        except Exception:
            return None

    def push(self, slot: str, name: str, state: dict, meta: dict | None = None):
        try:
            sb = self.connect()
            if not sb:
                return False

            slot = (slot or "default").strip()
            name = (name or slot).strip()

            payload = {
                "user_id": self.user_id,
                "slot": slot,
                "name": name,
                "data": state,
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }
            if meta:
                payload.update(meta)

            # Requires a unique constraint on (user_id, slot).
            resp = (
                sb.table(self.table)
                .upsert(payload, on_conflict="user_id,slot")
                .execute()
            )
            err = getattr(resp, "error", None)
            return err is None
        except Exception:
            return False
