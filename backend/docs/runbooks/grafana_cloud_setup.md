# Grafana Cloud Setup — Clonnect Dashboards

**Prepared:** 2026-04-19  
**Dashboards:** `ops/grafana/dashboards/` (5 JSON files)  
**Alerts:** `ops/grafana/alerts.yaml`

All dashboards are generated as importable JSON (Grafana 10.x format).  
No manual editing required — import, select your Prometheus datasource, done.

---

## Step 1 — Create Grafana Cloud account

1. Go to [grafana.com](https://grafana.com) → "Start for free"
2. The **free tier** includes:
   - 10k series Prometheus metrics
   - 14-day retention
   - 3 active users
   - Sufficient for Clonnect production monitoring
3. Create a stack (e.g. `clonnect`)
4. Note your Grafana instance URL: `https://<your-stack>.grafana.net`

---

## Step 2 — Connect Railway Prometheus to Grafana Cloud

Clonnect exposes Prometheus metrics at `/metrics` (added in ARC5 Phase 3).

### Option A: Prometheus scraping via Grafana Agent (recommended)

Install Grafana Agent on a Railway service or a small VPS that can reach your API:

```yaml
# grafana-agent.yaml
metrics:
  global:
    scrape_interval: 15s
  configs:
    - name: clonnect
      scrape_configs:
        - job_name: clonnect-api
          static_configs:
            - targets: ["www.clonnectapp.com"]
          metrics_path: /metrics
          scheme: https
      remote_write:
        - url: https://prometheus-prod-XX-prod-XX.grafana.net/api/prom/push
          basic_auth:
            username: <grafana-cloud-user-id>
            password: <grafana-cloud-api-key>
```

Get the `remote_write` URL and credentials from:  
Grafana Cloud → Connections → Add new connection → Prometheus → "Using Grafana Agent"

### Option B: Direct Prometheus datasource (pull from browser)

1. In Grafana: **Connections → Data sources → Add new → Prometheus**
2. URL: `https://www.clonnectapp.com/metrics`
3. This works for exploration but does NOT retain history

> **Recommended:** Option A (Grafana Agent) for persistent time-series history.

---

## Step 3 — Import dashboards

For each file in `ops/grafana/dashboards/`:

1. In Grafana: **Dashboards → New → Import**
2. Click **Upload JSON file**
3. Select the dashboard JSON
4. On import screen: select your Prometheus datasource from the dropdown
5. Click **Import**

Import order (suggested):
1. `clonnect_pipeline_overview.json` — start here, broadest visibility
2. `clonnect_arc1_budget.json`
3. `clonnect_arc2_memory.json`
4. `clonnect_arc3_compactor.json`
5. `clonnect_business.json`

---

## Step 4 — Configure alerts

### Option A: Grafana Managed Alerts (recommended for Grafana Cloud)

1. In Grafana: **Alerting → Alert rules → New alert rule**
2. Manually create rules from `ops/grafana/alerts.yaml`

Or import via Grafana API:
```bash
# Using Grafana API to create alert rules (adjust URL and credentials)
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  https://<your-stack>.grafana.net/api/ruler/grafana/api/v1/rules/clonnect \
  -d @ops/grafana/alerts_grafana_managed.json
```

### Option B: Prometheus Alertmanager (if self-hosting)

```bash
# If running your own Prometheus + Alertmanager:
cp ops/grafana/alerts.yaml /etc/prometheus/rules/clonnect.yaml
promtool check rules /etc/prometheus/rules/clonnect.yaml
systemctl reload prometheus
```

### Configure notification channels

In Grafana: **Alerting → Contact points → Add contact point**

Recommended channels:
- **Slack**: `#clonnect-alerts` (critical) / `#clonnect-warnings` (warning)
- **Email**: `manelbertran@gmail.com`
- **PagerDuty**: for critical-severity alerts only

Routing policy example:
```yaml
routes:
  - matchers: [severity="critical"]
    receiver: slack-critical
  - matchers: [severity="warning"]
    receiver: slack-warnings
```

---

## Step 5 — Verify dashboards show data

1. Open **Clonnect — Pipeline Overview**
2. Set time range: **Last 1 hour**
3. Verify panels show data (not "No data"):
   - If no data: check that `/metrics` endpoint returns Prometheus format
   - `curl https://www.clonnectapp.com/metrics | head -30`
4. Check the `creator_id` dropdown populates with real creator IDs

### Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| All panels show "No data" | Prometheus not scraping `/metrics` | Verify Grafana Agent config or datasource URL |
| `creator_id` dropdown empty | Metrics emitted but no requests yet | Send a test webhook to trigger emit_metric calls |
| Panels with histogram queries fail | Older Prometheus syntax | Ensure Grafana uses PromQL, not InfluxQL |
| Alerts not firing | Alert evaluation not running | Enable Grafana Managed Alerts in stack settings |

---

## Step 6 — Test an alert

To manually verify an alert fires:

```bash
# Trigger a test by hitting the health endpoint repeatedly to generate baseline traffic
for i in {1..100}; do curl -s https://www.clonnectapp.com/health > /dev/null; done

# Then check Grafana: Alerting → Alert rules — status should show "Normal" for all rules
```

For a real alert test, temporarily lower a threshold in a copy of the rule, confirm it fires, then restore.

---

## Active alerts summary

| Alert | Severity | Threshold | `for` |
|-------|----------|-----------|-------|
| HighPipelineErrorRate | critical | error rate > 5% | 5m |
| GenerationLatencyP95High | critical | P95 > 3000ms | 10m |
| MemoryDualWriteFailureHigh | critical | dual-write fail > 1% | 10m |
| LLMAPIErrorRateHigh | critical | LLM error rate > 5% | 5m |
| BudgetUtilizationSaturated | critical | budget P95 > 95% | 20m |
| CompactionAppliedRateHigh | warning | compaction > 30% of DMs | 30m |
| DistillCacheMissHigh | warning | distill miss rate > 30% | 30m |

## TODO alerts (uncomment in alerts.yaml when metrics exist)

- `CircuitBreakerTrips` — needs `circuit_breaker_tripped_total`
- `OpenRouterRateLimit` — needs `llm_429_total`

See `docs/sprint5_planning/ARC5_phase4_metrics_inventory.md` for full TODO list.
