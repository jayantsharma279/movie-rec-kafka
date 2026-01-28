# Shawshank Prediction 🎬  
*Machine Learning in Production – Group Project*  

## Collaborators  
- Dhruva Byrapatna  
- Jayant Sharma  
- Sonal Bhatia  
- Kabir Kakkar  
- Suraksha Sadana  

---

##  Getting Started 

### 1. Clone the Repository  
```bash
git clone https://github.com/<your-org>/shawshank-prediction-mlip-project.git
cd shawshank-prediction-mlip-project
```

### 3. Create a Conda Environment  
```bash
conda create -n shawshank-prediction python=3.10 -y
conda activate shawshank-prediction

```
### 2. Install Requirements
```bash
pip install -r requirements.txt
```

## Training Models

### 1. Train SVD
```bash
python scripts/models/train_svd.py
```
Artifacts saved to models/:

svd_model.pkl → trained Surprise SVD model
popular_top20.pkl → fallback top-20 movies

### 2. Train Collaborative Filtering
```bash
python scripts/models/train_cf.py
```
Artifacts saved to models/:
cf_model.pkl → trained CF model

## Evaluation
Run evaluation (accuracy, training time, inference latency, model size):

```bash
python scripts/models/eval_models.py
```
This prints metrics like RMSE/MAE, training duration, per-request latency, and model file size for each algorithm.

## Serving Recommendations

Start the Flask service
```bash
python app/app_flask.py
```

Endpoint
```bash
GET http://localhost:8082/recommend/<userid>
```

-> Known user (warm start): returns up to top-20 movies predicted by the SVD model.

-> Unknown user (cold start): returns a random sample from the top-20 popular movies.

-> Response format: comma-separated movie IDs (not JSON).

Example:
123,456,789,101,112

## Automated Updates (Milestone 3)

Our retraining/rollout workflow is driven by `scripts/automated_retraining.py`, which can:
- optionally pull the latest ratings from Kafka (`--pull-latest`)
- retrain the Surprise SVD model + fallback list
- version artifacts under `scripts/models/` and update `model_metadata.json`
- publish the active artifacts (`svd_model.pkl`, `popular_top20.pkl`) and metadata (`active_model.json`)

Typical cron entry (every 3 days, guarded by `flock` via `scripts/cron/run_retraining.sh`):
```
0 2 */3 * * /bin/bash /path/to/repo/scripts/cron/run_retraining.sh >> /var/log/retrain.log 2>&1
```

For Kubernetes-based deployments use `scripts/docker/retrain-deployment.yaml`, which mounts the shared model volume and runs the same Python entry point inside the retrainer image.

## Provenance & Versioning

- `scripts/models/model_metadata.json`: append-only history of every automated update (model version, git SHA, dataset version info such as path/rows/size/mtime, training notes).
- `scripts/models/active_model.json`: pointer to the model currently in production; hot-reloaded by `app/app_flask.py`.
- `/var/log/recsys/provenance.log`: every `/recommend` response is logged with `{timestamp, route, user_id, model_version, pipeline_git_sha, dataset_version_id, dataset_rows, dataset_size_bytes, dataset_path, latency_ms, rec_ids}` for traceability.

To answer “who produced this recommendation?” find the user/timestamp in `provenance.log`, note `model_version`, then inspect the matching entry in `model_metadata.json` to recover the exact dataset and git commit that produced it.
