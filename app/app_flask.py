from flask import Flask, Response
import joblib, random, os, time, json, threading
from datetime import datetime, timezone
import fcntl
from pathlib import Path
from prometheus_flask_exporter.multiprocess import GunicornInternalPrometheusMetrics
from prometheus_client import Gauge
import hashlib

app = Flask(__name__)

metrics = GunicornInternalPrometheusMetrics(app, group_by='endpoint')
import os


# metrics.exclude_paths([
#     r'^/metrics$',
# ])
# metrics.exclude_paths([r'^/metrics$', r'^/recommend/healthcheck$'])



from prometheus_client import Counter, REGISTRY

def get_or_create_counter(name, documentation, labelnames):
    # Avoid duplicate registration if module is reloaded (e.g., in tests)
    existing = REGISTRY._names_to_collectors.get(name)  # private but pragmatic
    if existing:
        return existing
    return Counter(name, documentation, labelnames)

route_counter = get_or_create_counter(
    "recsys_route_total",
    "Requests by route",
    ["route"],
)

ROOT_DIR = Path(__file__).resolve().parents[1]
# If that doesn't have scripts/models (e.g. in Docker), fall back to the app dir.
if not (ROOT_DIR / "scripts" / "models").exists():
    ROOT_DIR = Path(__file__).resolve().parent
MODEL_DIR = ROOT_DIR / "scripts" / "models"
ACTIVE_METADATA_PATH = MODEL_DIR / "active_model.json"


#setup telemetry
# TELEMETRY_DIR = "/var/log/recsys"
TELEMETRY_DIR = os.environ.get("TELEMETRY_DIR", "/var/log/recsys")
os.makedirs(TELEMETRY_DIR, exist_ok=True)
TELEMETRY_COLDWARM_FILE = os.path.join(TELEMETRY_DIR, "telemetry_cw.log")
TELEMETRY_RECS_FILE = os.path.join(TELEMETRY_DIR, "telemetry_recs.log")
PROVENANCE_FILE = os.path.join(TELEMETRY_DIR, "provenance.log")
SAMPLE_RATE = float(os.getenv("RECSYS_TELEMETRY_SAMPLE", "0.02"))  #allow us to tune sample rate with os env


class ModelRegistry:
    """Loads artifacts based on scripts/models/active_model.json and hot-reloads on change."""

    def __init__(self, metadata_path: Path):
        self.metadata_path = metadata_path
        self._model = None
        self._popular = None
        self._metadata = None
        self._mtime = 0
        self._lock = threading.Lock()
        self._fallback_version = os.getenv("RECSYS_MODEL_VERSION", "svd-1")
        self.ensure_loaded(force=True)

    def _resolve_path(self, raw_path: str | None, default: Path) -> Path:
        if not raw_path:
            return default
        candidate = ROOT_DIR / raw_path
        if candidate.exists():
            return candidate
        return default

    def ensure_loaded(self, force: bool = False):
        try:
            mtime = self.metadata_path.stat().st_mtime
        except FileNotFoundError:
            if self._model is None:
                # Fall back to legacy artifacts once
                legacy_model = MODEL_DIR / "svd_model.pkl"
                legacy_pop = MODEL_DIR / "popular_top20.pkl"
                if legacy_model.exists() and legacy_pop.exists():
                    self._model = joblib.load(legacy_model)
                    self._popular = joblib.load(legacy_pop)
                    self._metadata = {
                        "model_version": self._fallback_version,
                        "model_artifact": str(legacy_model),
                        "fallback_artifact": str(legacy_pop),
                        "pipeline_git_sha": os.getenv("RECSYS_PIPELINE_SHA", "unknown"),
                        "data": {},
                    }
            return

        if not force and mtime == self._mtime:
            return

        with self._lock:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            model_path = self._resolve_path(
                data.get("model_artifact"),
                MODEL_DIR / "svd_model.pkl",
            )
            pop_path = self._resolve_path(
                data.get("fallback_artifact"),
                MODEL_DIR / "popular_top20.pkl",
            )

            model_obj = joblib.load(model_path)
            if isinstance(model_obj, tuple):
                model_obj = model_obj[0]
            popular_obj = joblib.load(pop_path)

            self._model = model_obj
            self._popular = popular_obj
            self._metadata = data
            self._mtime = mtime

    def get(self):
        self.ensure_loaded()
        return self._model, self._popular, self._metadata

    def current_version(self) -> str:
        if self._metadata:
            return self._metadata.get("model_version", self._fallback_version)
        return self._fallback_version
    
    def get_model_paths(self):
        """
        Returns paths to both models:
        - v1: fallback model (svd_model.pkl)
        - v2: active model (from active_model.json)
        """
        fallback_model_path = MODEL_DIR / "svd_model.pkl"
        # active_model_path already resolved in ensure_loaded
        self.ensure_loaded()
        active_model_path = self._resolve_path(
            self._metadata.get("active_model_path") or self._metadata.get("model_artifact"),
            MODEL_DIR / "svd_model.pkl",
        )
        return fallback_model_path, active_model_path
    

model_registry = ModelRegistry(ACTIVE_METADATA_PATH)

#-- A/B testing ----

def assign_model_by_user(user_id):
    bucket = int(hashlib.sha256(user_id.encode()).hexdigest(), 16) % 100
    if bucket < 20:
        return "v2"   # 20% users → new model
    return "v1"       # 80% users -> old model
#----- rest in the route script-------

def get_or_create_gauge(name, doc, labelnames=()):
    existing = REGISTRY._names_to_collectors.get(name)  # pragmatic private lookup
    if existing:
        return existing
    return Gauge(name, doc, labelnames)


def get_or_create_counter(name, doc, labelnames=()):
    existing = REGISTRY._names_to_collectors.get(name)
    if existing:
        return existing
    return Counter(name, doc, labelnames)


# Emits a single sample tagged with the current model version
g_model_info = get_or_create_gauge("recsys_model_info", "Current model in service", ["model_version"])
g_model_info.labels(model_registry.current_version()).set(1)
model_version = model_registry.current_version() #model version


# Expose the sampling rate you already read from env
g_sample_rate = get_or_create_gauge("recsys_telemetry_sample_rate", "Telemetry sampling fraction (0..1)")
g_sample_rate.set(SAMPLE_RATE)



def is_known_user(model, raw_uid):
    """True if raw_uid was seen in training."""
    try:
        model.trainset.to_inner_uid(raw_uid)
        return True
    except ValueError:
        return False


def top_k_for_user(model, user_id, k=5):
    """
    Return top-k (movie_id, predicted_rating) for a given user_id.

    - Uses the model's trainset to list all candidate movie_ids seen in training.
    - Does NOT exclude items the user may have already rated (per your request).
    """
    ts = model.trainset
    raw_item_ids = [ts.to_raw_iid(i) for i in ts.all_items()]

    scored = []
    for mid in raw_item_ids:
        est = model.predict(user_id, mid).est
        scored.append((mid, est))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


#helper function to log the cold-warm route, user id, latency, and timestamp for telemetry purposes
def log_cw_route(route: str, user_id: str, latency_ms: float, model_version: str):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"{ts},{route},{user_id},{latency_ms:.3f}, {model_version}\n"
    try:
        with open(TELEMETRY_COLDWARM_FILE, "a", encoding="utf-8") as f:
            # simple inter-process lock
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        # Avoid throwing in request path
        print(f"{TELEMETRY_COLDWARM_FILE} write-failed: {e}", flush=True)

def log_recs(route: str, user_id: str, rec_ids: list[str], latency_ms: float, model_version:str):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # rec_ids pipe-delimited to avoid commas clashing with CSV
    body = "|".join(map(str, rec_ids))
    line = f"{ts},{route},{user_id},{latency_ms:.3f}, {model_version},{body}\n"
    try:
        with open(TELEMETRY_RECS_FILE, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        print(f"{TELEMETRY_RECS_FILE} write-failed: {e}", flush=True)

def telemetry_logger(route: str, user_id: str, rec_ids: list[str], latency_ms: float, model_version:str):
    log_cw_route(route, user_id, latency_ms, model_version)
    log_recs(route,user_id, rec_ids, latency_ms, model_version)
    

def log_provenance(metadata: dict | None, route: str, user_id: str, rec_ids: list[str], latency_ms: float):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = metadata or {}
    data = meta.get("data", {})
    rec_body = "|".join(map(str, rec_ids))
    line = ",".join(
        [
            ts,
            route,
            user_id,
            meta.get("model_version", "unknown"),
            meta.get("pipeline_git_sha", "unknown"),
            data.get("version_id", "unknown"),
            str(data.get("rows", "")),
            str(data.get("size_bytes", "")),
            data.get("path", ""),
            f"{latency_ms:.3f}",
            rec_body,
        ]
    ) + "\n"
    try:
        with open(PROVENANCE_FILE, "a", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
            fcntl.flock(fh, fcntl.LOCK_UN)
    except Exception as exc:
        print(f"{PROVENANCE_FILE} write-failed: {exc}", flush=True)
    
_v1_model = None
_v1_popular = None
_v1_lock = threading.Lock()

def load_v1_model():
    global _v1_model, _v1_popular
    if _v1_model is None or _v1_popular is None:
        with _v1_lock:
            if _v1_model is None or _v1_popular is None:
                v1_model_path = MODEL_DIR / "svd_model.pkl"
                v1_popular_path = MODEL_DIR / "popular_top20.pkl"
                _v1_model = joblib.load(v1_model_path)
                _v1_popular = joblib.load(v1_popular_path)
    return _v1_model, _v1_popular


@app.get("/recommend/<user_id>")
def recommend(user_id: str):
    start = time.time()
    telemetry_on = random.random() < SAMPLE_RATE #if our random gen is < 0.02 (happens 2% of the time, turn telemetry on for this request)
    
     # --- NEW: A/B testing route ---

    model_tag = assign_model_by_user(user_id)

    if model_tag == "v1": #80% users -> svd_model.pkl
        model_obj, popular = load_v1_model()
        metadata = {"model_version": "v1", "model_artifact": "svd_model.pkl"}
    else:
        model_obj, popular, metadata = model_registry.get()
        metadata["model_version"] = "v2"
    
    g_model_info.labels(metadata["model_version"]).set(1)

    if model_obj is None or popular is None:
        return Response("model-unavailable", status=503, mimetype="text/plain")
    
    
    if not is_known_user(model_obj, user_id):
        k = 10
        picks = random.sample(popular, k) if k > 0 else []
        body = ",".join(map(str, picks))
        print(f"[cold-start] user={user_id} → {body}")
        end = time.time()
        train_time = (end - start)*1000
        print(f"Latency: {train_time:.4f} milliseconds")
        if telemetry_on:
            telemetry_logger(route="cold", user_id=user_id, rec_ids=picks, latency_ms=train_time, model_version=metadata['model_version'])
        log_provenance(metadata, "cold", user_id, picks, train_time)
        route_counter.labels("cold").inc()
        return Response(body, mimetype="text/plain")

    # Warm-start: score and return top-10
    top10 = top_k_for_user(model_obj, user_id, k=10)
    movie_ids = [mid for (mid, _est) in top10]
    body = ",".join(map(str, movie_ids))
    print(f"[warm] user={user_id} → {body}")
    end = time.time()
    train_time = (end - start)*1000
    print(f"Latency: {train_time:.4f} milliseconds")
    if telemetry_on:
        telemetry_logger(route="warm", user_id=user_id, rec_ids=movie_ids, latency_ms=train_time, model_version = metadata['model_version'] )
    log_provenance(metadata, "warm", user_id, movie_ids, train_time)
    
    route_counter.labels("warm").inc()
    return Response(body, mimetype="text/plain")

@metrics.do_not_track()
@app.get("/recommend/healthcheck")
def healthcheck():
    return Response("ok", mimetype="text/plain")

@metrics.do_not_track()
@app.get("/health")
def health():
    """Health check endpoint for Docker"""
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    
    app.run(host="0.0.0.0", port=8082)
