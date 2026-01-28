#!/usr/bin/env bash
set -euo pipefail

HIT_FILE="/var/log/recsys/rollups/hit_rate_30m.csv"
CW_FILE="/var/log/recsys/rollups/cold_warm_share.csv"
RDRIFT_FILE="/var/log/recsys/rollups/rating_drift.csv"
OUT="/var/lib/node_exporter/textfile/recsys_rollups.prom"

# Ensure target dir exists (owned/perm handled outside by unit install)
mkdir -p "$(dirname "$OUT")"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

# Helpers ----------------------------------------------------------------------

is_num() {
  # true if $1 looks like a number
  [[ "${1:-}" =~ ^-?[0-9]+([.][0-9]+)?$ ]]
}

to_frac() {
  # Convert percent to fraction if needed. Accepts "", returns 0 for non-numeric.
  local v="${1:-0}"
  if ! is_num "$v"; then
    printf '0'
    return
  fi
  # treat >1 as percent (e.g., 63.44) and divide by 100
  awk -v n="$v" 'BEGIN { if (n > 1) printf "%.6f", n/100.0; else printf "%.6f", n+0.0 }'
}

to_int() {
  local v="${1:-0}"
  if ! is_num "$v"; then
    printf '0'
  else
    printf '%.0f' "$v"
  fi
}

append() { echo "$@" >> "$tmp"; }

# Reset file
: > "$tmp"

# ------------------------- Hit rate rollup ------------------------------------
# header: ts_utc,total,hits,hit_rate_pct,cold_total,cold_hits,cold_hit_rate_pct,warm_total,warm_hits,warm_hit_rate_pct
if [[ -f "$HIT_FILE" ]]; then
  last="$(tail -n 1 "$HIT_FILE" || true)"
  IFS=',' read -r ts total hits hit_pct cold_total cold_hits cold_pct warm_total warm_hits warm_pct <<<"${last:-}"

  if [[ -n "${ts:-}" && "$ts" != "ts_utc" ]]; then
    total_frac="$(to_frac "${hit_pct:-0}")"
    cold_frac="$(to_frac  "${cold_pct:-0}")"
    warm_frac="$(to_frac  "${warm_pct:-0}")"

    total_i="$(to_int "${total:-0}")"
    hits_i="$(to_int  "${hits:-0}")"
    cold_total_i="$(to_int "${cold_total:-0}")"
    cold_hits_i="$(to_int  "${cold_hits:-0}")"
    warm_total_i="$(to_int "${warm_total:-0}")"
    warm_hits_i="$(to_int  "${warm_hits:-0}")"

    append "# HELP recsys_hitrate_30m Hit rate over the last 30 minutes (fraction 0..1)"
    append "# TYPE recsys_hitrate_30m gauge"
    append "recsys_hitrate_30m{route=\"total\"} ${total_frac}"
    append "recsys_hitrate_30m{route=\"cold\"} ${cold_frac}"
    append "recsys_hitrate_30m{route=\"warm\"} ${warm_frac}"

    append "# HELP recsys_hitrate_30m_counts Last window totals and hits"
    append "# TYPE recsys_hitrate_30m_counts gauge"
    append "recsys_hitrate_30m_counts{route=\"total\",type=\"total\"} ${total_i}"
    append "recsys_hitrate_30m_counts{route=\"total\",type=\"hits\"} ${hits_i}"
    append "recsys_hitrate_30m_counts{route=\"cold\",type=\"total\"} ${cold_total_i}"
    append "recsys_hitrate_30m_counts{route=\"cold\",type=\"hits\"} ${cold_hits_i}"
    append "recsys_hitrate_30m_counts{route=\"warm\",type=\"total\"} ${warm_total_i}"
    append "recsys_hitrate_30m_counts{route=\"warm\",type=\"hits\"} ${warm_hits_i}"
  fi
fi

# ------------------------- Cold/Warm share ------------------------------------
# header: ts_utc,total,cold,warm   (cold/warm may be percent or fraction)
if [[ -f "$CW_FILE" ]]; then
  last2="$(tail -n 1 "$CW_FILE" || true)"
  IFS=',' read -r ts2 total2 cold_share warm_share <<<"${last2:-}"

  if [[ -n "${ts2:-}" && "$ts2" != "ts_utc" ]]; then
    total2_i="$(to_int "${total2:-0}")"
    cold_share_f="$(to_frac "${cold_share:-0}")"
    warm_share_f="$(to_frac "${warm_share:-0}")"

    append "# HELP recsys_coldwarm_share Share of requests by route over last window (fraction 0..1)"
    append "# TYPE recsys_coldwarm_share gauge"
    append "recsys_coldwarm_share{route=\"cold\"} ${cold_share_f}"
    append "recsys_coldwarm_share{route=\"warm\"} ${warm_share_f}"

    append "# HELP recsys_coldwarm_total Total number of requests in the last window"
    append "# TYPE recsys_coldwarm_total gauge"
    append "recsys_coldwarm_total ${total2_i}"
  fi
fi

if [[ -f "$RDRIFT_FILE" ]]; then
  last="$(tail -n 1 "$RDRIFT_FILE" || true)"
  IFS=',' read -r ts3 total_ratings kl mean_diff flag_kl flag_mean frac_big big_flag kl_thresh mean_thresh <<<"$last"

  if [[ "$ts3" != "ts_utc" && -n "${ts3:-}" ]]; then
    echo "# HELP recsys_rating_drift_kl KL divergence between baseline and last 1h rating distribution" >> "$tmp"
    echo "# TYPE recsys_rating_drift_kl gauge" >> "$tmp"
    echo "recsys_rating_drift_kl{window=\"1h\"} ${kl:-0}" >> "$tmp"

    echo "# HELP recsys_rating_drift_mean_diff Absolute difference in mean rating (stars) between baseline and last 1h" >> "$tmp"
    echo "# TYPE recsys_rating_drift_mean_diff gauge" >> "$tmp"
    echo "recsys_rating_drift_mean_diff{window=\"1h\"} ${mean_diff:-0}" >> "$tmp"

    echo "# HELP recsys_rating_drift_flag Binary drift flags (1 == drift detected)" >> "$tmp"
    echo "# TYPE recsys_rating_drift_flag gauge" >> "$tmp"
    echo "recsys_rating_drift_flag{type=\"kl\"} ${flag_kl:-0}" >> "$tmp"
    echo "recsys_rating_drift_flag{type=\"mean\"} ${flag_mean:-0}" >> "$tmp"
    echo "recsys_rating_drift_flag{type=\"big_count_change\"} ${big_flag:-0}" >> "$tmp"

    echo "# HELP recsys_rating_drift_total_ratings Total ratings in last 1h window" >> "$tmp"
    echo "# TYPE recsys_rating_drift_total_ratings gauge" >> "$tmp"
    echo "recsys_rating_drift_total_ratings{window=\"1h\"} ${total_ratings:-0}" >> "$tmp"
  fi
fi

# ------------------------- Hit rate per model version -------------------------
# header:
# ts_utc,model_version,total,hits,hit_rate_pct,
# cold_total,cold_hits,cold_hit_rate_pct,
# warm_total,warm_hits,warm_hit_rate_pct

VER_FILE="/var/log/recsys/rollups/hit_rate_30m_versions.csv"

if [[ -f "$VER_FILE" ]]; then
  # Get latest timestamp
  last_ts="$(tail -n 1 "$VER_FILE" | cut -d',' -f1)"

  if [[ "$last_ts" != "ts_utc" && -n "$last_ts" ]]; then
    # Extract all rows for that timestamp (one per model_version)
    mapfile -t rows < <(grep "^$last_ts" "$VER_FILE")

    append "# HELP recsys_hitrate_30m_version Hit rate by model version (fraction 0..1)"
    append "# TYPE recsys_hitrate_30m_version gauge"

    append "# HELP recsys_hitrate_30m_version_counts Last window totals and hits per model version"
    append "# TYPE recsys_hitrate_30m_version_counts gauge"

    for r in "${rows[@]}"; do
      IFS=',' read -r ts mv total hits hit_pct \
                       cold_total cold_hits cold_pct \
                       warm_total warm_hits warm_pct <<< "$r"

      # Fractions
      total_frac="$(to_frac "${hit_pct:-0}")"
      cold_frac="$(to_frac "${cold_pct:-0}")"
      warm_frac="$(to_frac "${warm_pct:-0}")"

      # Ints
      total_i="$(to_int "${total:-0}")"
      hits_i="$(to_int  "${hits:-0}")"
      cold_total_i="$(to_int "${cold_total:-0}")"
      cold_hits_i="$(to_int  "${cold_hits:-0}")"
      warm_total_i="$(to_int "${warm_total:-0}")"
      warm_hits_i="$(to_int  "${warm_hits:-0}")"

      # Metrics
      append "recsys_hitrate_30m_version{version=\"${mv}\"} ${total_frac}"
      append "recsys_hitrate_30m_version_counts{version=\"${mv}\",route=\"total\",type=\"total\"} ${total_i}"
      append "recsys_hitrate_30m_version_counts{version=\"${mv}\",route=\"total\",type=\"hits\"} ${hits_i}"

      append "recsys_hitrate_30m_version_counts{version=\"${mv}\",route=\"cold\",type=\"total\"} ${cold_total_i}"
      append "recsys_hitrate_30m_version_counts{version=\"${mv}\",route=\"cold\",type=\"hits\"} ${cold_hits_i}"

      append "recsys_hitrate_30m_version_counts{version=\"${mv}\",route=\"warm\",type=\"total\"} ${warm_total_i}"
      append "recsys_hitrate_30m_version_counts{version=\"${mv}\",route=\"warm\",type=\"hits\"} ${warm_hits_i}"
    done
  fi
fi

# Write atomically with safe perms (no sudo; unit runs unprivileged)
install -m 0644 -o "$(id -un)" -g "$(id -gn)" "$tmp" "$OUT"
