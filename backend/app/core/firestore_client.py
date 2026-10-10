import os
import sys
import threading
import logging
from typing import Dict, Any, Optional, List, Callable
from app.core.config import settings

logger = logging.getLogger(__name__)


class FirestoreConnectionError(Exception):
    """Raised when Firestore emulator is unreachable."""
    pass


class StorageConnectionError(Exception):
    """Raised when Storage emulator is unreachable."""
    pass


# ==============================================================================
# In-Memory Test Fakes (Used exclusively for pytest per requirement #2)
# ==============================================================================

class FakeBlob:
    def __init__(self, name: str, bucket: "FakeBucket"):
        self.name = name
        self.bucket = bucket
        self._data: Optional[bytes] = None
        self.content_type: Optional[str] = None

    def upload_from_string(self, data: bytes, content_type: Optional[str] = None):
        self._data = bytes(data)
        self.content_type = content_type
        self.bucket._blobs[self.name] = self

    def download_as_bytes(self) -> bytes:
        if self._data is None:
            raise FileNotFoundError(f"Blob '{self.name}' has not been uploaded.")
        return self._data

    def exists(self) -> bool:
        return self._data is not None

    def generate_signed_url(self, expiration: Any = None, **kwargs) -> str:
        return f"http://127.0.0.1:9199/v0/b/{self.bucket.name}/o/{self.name}?alt=media&token=fake_signed_token"


class FakeBucket:
    def __init__(self, name: str):
        self.name = name
        self._blobs: Dict[str, FakeBlob] = {}

    def blob(self, blob_name: str) -> FakeBlob:
        if blob_name not in self._blobs:
            self._blobs[blob_name] = FakeBlob(blob_name, self)
        return self._blobs[blob_name]


class FakeStorageClient:
    def __init__(self):
        self._buckets: Dict[str, FakeBucket] = {}

    def bucket(self, name: str) -> FakeBucket:
        if name not in self._buckets:
            self._buckets[name] = FakeBucket(name)
        return self._buckets[name]


class FakeDocumentSnapshot:
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]], ref: "FakeDocumentReference"):
        self.id = doc_id
        self.reference = ref
        self._data = dict(data) if data is not None else None

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return dict(self._data) if self._data is not None else None


class FakeDocumentReference:
    def __init__(self, path: str, client: "FakeFirestoreClient"):
        self.path = path.strip("/")
        self.id = self.path.split("/")[-1]
        self.client = client

    def collection(self, subcollection_name: str) -> "FakeCollectionReference":
        return FakeCollectionReference(f"{self.path}/{subcollection_name}", self.client)

    def get(self, transaction: Optional["FakeTransaction"] = None) -> FakeDocumentSnapshot:
        if transaction is not None:
            return transaction.get(self)
        with self.client._lock:
            data = self.client._store.get(self.path)
            return FakeDocumentSnapshot(self.id, data, self)

    def set(self, data: Dict[str, Any], merge: bool = False):
        with self.client._lock:
            if merge and self.path in self.client._store:
                self.client._store[self.path].update(data)
            else:
                self.client._store[self.path] = dict(data)
            self.client._versions[self.path] = self.client._versions.get(self.path, 0) + 1

    def update(self, data: Dict[str, Any]):
        with self.client._lock:
            if self.path not in self.client._store:
                raise KeyError(f"Document at path '{self.path}' does not exist.")
            self.client._store[self.path].update(data)
            self.client._versions[self.path] = self.client._versions.get(self.path, 0) + 1

    def delete(self):
        with self.client._lock:
            self.client._store.pop(self.path, None)
            self.client._versions[self.path] = self.client._versions.get(self.path, 0) + 1


class FakeCollectionReference:
    def __init__(self, path: str, client: "FakeFirestoreClient"):
        self.path = path.strip("/")
        self.client = client
        self._filters: List[tuple] = []
        self._order_by_field: Optional[str] = None
        self._order_descending: bool = False

    def document(self, doc_id: Optional[str] = None) -> FakeDocumentReference:
        if not doc_id:
            import uuid
            doc_id = f"auto_{uuid.uuid4().hex[:12]}"
        return FakeDocumentReference(f"{self.path}/{doc_id}", self.client)

    def where(self, field: str, op: str, value: Any) -> "FakeCollectionReference":
        new_ref = FakeCollectionReference(self.path, self.client)
        new_ref._filters = list(self._filters) + [(field, op, value)]
        new_ref._order_by_field = self._order_by_field
        new_ref._order_descending = self._order_descending
        return new_ref

    def order_by(self, field: str, direction: str = "ASCENDING") -> "FakeCollectionReference":
        new_ref = FakeCollectionReference(self.path, self.client)
        new_ref._filters = list(self._filters)
        new_ref._order_by_field = field
        new_ref._order_descending = (direction.upper() == "DESCENDING")
        return new_ref

    def stream(self) -> List[FakeDocumentSnapshot]:
        with self.client._lock:
            prefix = f"{self.path}/"
            snapshots: List[FakeDocumentSnapshot] = []
            for path, data in list(self.client._store.items()):
                if path.startswith(prefix):
                    subpath = path[len(prefix):]
                    if "/" not in subpath:
                        # Direct child of this collection
                        doc_id = subpath
                        ref = FakeDocumentReference(path, self.client)
                        snap = FakeDocumentSnapshot(doc_id, data, ref)
                        
                        # Apply filters
                        match = True
                        for f_field, f_op, f_val in self._filters:
                            doc_val = data.get(f_field)
                            if f_op == "==" and doc_val != f_val:
                                match = False
                                break
                            elif f_op == "!=" and doc_val == f_val:
                                match = False
                                break
                        if match:
                            snapshots.append(snap)

            if self._order_by_field:
                def get_sort_key(snap: FakeDocumentSnapshot):
                    d = snap.to_dict() or {}
                    return str(d.get(self._order_by_field, ""))
                snapshots.sort(key=get_sort_key, reverse=self._order_descending)

            return snapshots

    def get(self) -> List[FakeDocumentSnapshot]:
        return self.stream()


class FakeTransaction:
    def __init__(self, client: "FakeFirestoreClient"):
        self.client = client
        self._read_versions: Dict[str, int] = {}
        self._staged_updates: List[tuple] = []
        self._staged_sets: List[tuple] = []

    def get(self, doc_ref: FakeDocumentReference) -> FakeDocumentSnapshot:
        with self.client._lock:
            data = self.client._store.get(doc_ref.path)
            self._read_versions[doc_ref.path] = self.client._versions.get(doc_ref.path, 0)
            return FakeDocumentSnapshot(doc_ref.id, data, doc_ref)

    def update(self, doc_ref: FakeDocumentReference, data: Dict[str, Any]):
        self._staged_updates.append((doc_ref, data))

    def set(self, doc_ref: FakeDocumentReference, data: Dict[str, Any], merge: bool = False):
        self._staged_sets.append((doc_ref, data, merge))

    def commit(self):
        with self.client._lock:
            # Check version conflicts across all read documents
            for path, read_ver in self._read_versions.items():
                current_ver = self.client._versions.get(path, 0)
                if current_ver != read_ver:
                    raise Exception(f"Firestore Concurrency Conflict on '{path}': modified by concurrent writer.")

            # Apply staged writes
            for doc_ref, data, merge in self._staged_sets:
                doc_ref.set(data, merge=merge)
            for doc_ref, data in self._staged_updates:
                doc_ref.update(data)


class FakeFirestoreClient:
    """A single, clearly named in-memory Fake Firestore client used only in tests."""
    def __init__(self, shared_store: Optional[Dict[str, Dict[str, Any]]] = None):
        self._store: Dict[str, Dict[str, Any]] = shared_store if shared_store is not None else {}
        self._versions: Dict[str, int] = {}
        self._lock = threading.RLock()
        self.is_fake = True

    def collection(self, name: str) -> FakeCollectionReference:
        return FakeCollectionReference(name, self)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)


# ==============================================================================
# Transaction Decorator
# ==============================================================================

def firestore_transactional(client):
    """
    Unified transaction decorator.
    For FakeFirestoreClient: runs func(tx) and commits tx atomically with conflict detection.
    For google.cloud.firestore: delegates to firestore.transactional runner.
    """
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            if hasattr(client, "is_fake") and client.is_fake:
                tx = client.transaction()
                res = func(tx, *args, **kwargs)
                tx.commit()
                return res
            else:
                from google.cloud import firestore
                tx = client.transaction()
                @firestore.transactional
                def _tx_runner(t):
                    return func(t, *args, **kwargs)
                return _tx_runner(tx)
        return wrapper
    return decorator


# ==============================================================================
# Client Singletons & Factories
# ==============================================================================

_firestore_client: Optional[Any] = None
_storage_client: Optional[Any] = None
_client_lock = threading.Lock()


def is_testing_environment() -> bool:
    return (
        os.environ.get("TESTING") == "1"
        or "pytest" in sys.modules
        or "pytest" in os.environ.get("_", "").lower()
        or "PYTEST_CURRENT_TEST" in os.environ
    )


def get_firestore_client():
    """
    Returns the Firestore client.
    - If TESTING=1 or running under pytest: returns the single FakeFirestoreClient.
    - If in production/emulator mode: connects to FIRESTORE_EMULATOR_HOST (127.0.0.1:8080).
      If emulator is unreachable, fails immediately with a clear error message (no silent fallback).
    """
    global _firestore_client
    with _client_lock:
        if _firestore_client is not None:
            return _firestore_client

        if is_testing_environment():
            _firestore_client = FakeFirestoreClient()
            logger.info("Initialized FakeFirestoreClient for test environment.")
            return _firestore_client

        # Production / Emulator Mode
        host = os.environ.get("FIRESTORE_EMULATOR_HOST", settings.FIRESTORE_EMULATOR_HOST)
        if host:
            os.environ["FIRESTORE_EMULATOR_HOST"] = host

        try:
            import socket
            if host:
                h_parts = host.split(":")
                s_host = h_parts[0]
                s_port = int(h_parts[1]) if len(h_parts) > 1 else 8080
                with socket.create_connection((s_host, s_port), timeout=2.0):
                    pass
        except Exception as e:
            raise FirestoreConnectionError(
                f"Firestore emulator is unreachable at {host} ({e}). "
                "Please ensure the Firebase emulator is running before starting the backend."
            )

        from google.cloud import firestore
        _firestore_client = firestore.Client(project=settings.FIREBASE_PROJECT_ID)
        return _firestore_client


def get_storage_client():
    """
    Returns the Storage client.
    - If TESTING=1 or running under pytest: returns FakeStorageClient.
    - If in production/emulator mode: connects to FIREBASE_STORAGE_EMULATOR_HOST (127.0.0.1:9199).
      If emulator is unreachable, fails immediately with a clear error message (no silent fallback).
    """
    global _storage_client
    with _client_lock:
        if _storage_client is not None:
            return _storage_client

        if is_testing_environment():
            _storage_client = FakeStorageClient()
            logger.info("Initialized FakeStorageClient for test environment.")
            return _storage_client

        host = os.environ.get("STORAGE_EMULATOR_HOST", settings.FIREBASE_STORAGE_EMULATOR_HOST)
        if host:
            os.environ["STORAGE_EMULATOR_HOST"] = f"http://{host}" if not host.startswith("http") else host

        try:
            import socket
            h_clean = host.replace("http://", "").replace("https://", "")
            h_parts = h_clean.split(":")
            s_host = h_parts[0]
            s_port = int(h_parts[1]) if len(h_parts) > 1 else 9199
            with socket.create_connection((s_host, s_port), timeout=2.0):
                pass
        except Exception as e:
            raise StorageConnectionError(
                f"Storage emulator is unreachable at {host} ({e}). "
                "Please ensure the Firebase emulator is running before starting the backend."
            )

        from google.cloud import storage
        _storage_client = storage.Client(project=settings.FIREBASE_PROJECT_ID)
        return _storage_client


def reset_test_clients(fake_db: Optional[FakeFirestoreClient] = None, fake_storage: Optional[FakeStorageClient] = None):
    """Explicitly resets or injects test clients (used for testing and restart simulations)."""
    global _firestore_client, _storage_client
    with _client_lock:
        _firestore_client = fake_db if fake_db is not None else FakeFirestoreClient()
        _storage_client = fake_storage if fake_storage is not None else FakeStorageClient()
