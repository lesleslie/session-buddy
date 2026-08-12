# Crackerjack CLI Fallback — Alert Rules and Dashboard Panel

**Created:** 2026-07-27
**Owner:** session-buddy maintainers
**Metrics:**

- `session_buddy_crackerjack_fallback_invocations_total{command, outcome, caller}` (counter)
- `session_buddy_crackerjack_fallback_duration_seconds{command, caller}` (histogram)

## Alert rules (PromQL)

### A1. Outcome ≠ success rate exceeds 10% over 5 minutes

- **Severity:** Slack (not PagerDuty; the fallback is a recovery, not an outage)
- **PromQL:**
  ```promql
  sum(rate(session_buddy_crackerjack_fallback_invocations_total{outcome!="success"}[5m]))
    /
  sum(rate(session_buddy_crackerjack_fallback_invocations_total[5m]))
    > 0.10
  ```
- **Runbook:** Check `outcome` distribution. If most failures are `timeout`, the lock may be contended or the helper is slow. If most are `nonzero_exit`, the crackerjack invocation has a config issue. If most are `disabled`, someone flipped the kill switch and forgot.

### A2. Disabled outcome rate > 0

- **Severity:** Slack (informational; the kill switch was tripped)
- **PromQL:**
  ```promql
  sum(rate(session_buddy_crackerjack_fallback_invocations_total{outcome="disabled"}[1h])) > 0
  ```
- **Runbook:** The operator deliberately disabled the fallback. Confirm with the on-call channel that this is intentional.

### A3. p99 duration > 25s (close to the 30s timeout)

- **Severity:** Slack
- **PromQL:**
  ```promql
  histogram_quantile(0.99, sum by (le, command) (rate(session_buddy_crackerjack_fallback_duration_seconds_bucket[5m])))
    > 25
  ```
- **Runbook:** Fallback invocations are taking almost the full timeout. Either the subprocess is slow (crackerjack regression) or the lock is contended. Consider raising the timeout or staggering consumer-chain reads.

## Dashboard panel

Suggested panel: "Crackerjack Fallback" with these queries:

- **Invocation rate by outcome (stacked area):**
  ```promql
  sum by (outcome) (rate(session_buddy_crackerjack_fallback_invocations_total[5m]))
  ```
- **p50 / p99 duration:**
  ```promql
  histogram_quantile(0.50, sum by (le) (rate(session_buddy_crackerjack_fallback_duration_seconds_bucket[5m])))
  histogram_quantile(0.99, sum by (le) (rate(session_buddy_crackerjack_fallback_duration_seconds_bucket[5m])))
  ```
- **Caller distribution (proportion of consumer_chain vs producer_retry):**
  ```promql
  sum by (caller) (rate(session_buddy_crackerjack_fallback_invocations_total[5m]))
  ```

## Counter-name double-counting warning

The plan does NOT register dedicated `crackerjack.fallback.timeout{command}` or `crackerjack.fallback.disabled{command}` counters. Operators aggregating dashboards should query the unified `session_buddy_crackerjack_fallback_invocations_total{outcome="timeout"}` (not a separate counter) to avoid double-counting.
