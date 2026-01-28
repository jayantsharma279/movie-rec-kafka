#!/bin/bash
set -e

cp /app/var/log/recsys/ratings.log /app/dataset/ratings.log
echo "[CRON] Training file copied to dataset"

echo "[CRON] Starting automated training at $(date)"

/opt/conda/envs/scheduler_env/bin/python /app/scripts/automated_retraining.py --pull-latest

echo "[CRON] Training completed at $(date)"
