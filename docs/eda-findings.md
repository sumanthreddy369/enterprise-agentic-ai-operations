# Exploratory data analysis and engineering gates

Follow-up: [deeper EDA, change record and publication evidence](evidence/eda/README.md)
adds an executed notebook, three verified figures, duration percentiles and
source-order activity analysis. These do not establish agent or Azure performance.

Subsequent [data engineering verification](evidence/data-engineering/README.md)
completed real PostgreSQL/OpenSearch checks and full-file replay on 2026-10-15.
The first-pass observations below retain their original verification scope.

Observed 2026-10-15 from a fresh acquisition and full processing of all seven pinned
manifest files on this checkout. Full means the acquired file; Loghub inputs are
2,000-line samples, not the publishers' full archives. No live enterprise feed is
connected. No raw records or message text are reproduced in this report.

## Reproduction and provenance

```sh
uv run python -m src.ingestion.cli all --full
uv run python -m scripts.profile_data
uv run pytest tests/test_pipeline.py tests/test_acquire.py tests/test_data_profile.py -q
```

Acquisition validates pinned source checksums. The profiler verifies all manifest
output checksums before reading full, default-timezone Silver tables. Its local JSON
report includes source checksum, pipeline version, parser, run ID, row counts,
null counts, normalized categories and timestamp coverage. Raw files, Parquet and
the detailed aggregate JSON remain ignored. Generated labels are not original
incident narratives. SQL loading and OpenSearch indexing were not part of this EDA.

## Measured inventory

| Source | Incidents | Events | Logs | Quarantined |
| --- | ---: | ---: | ---: | ---: |
| BPI 2013 | 7,554 | 65,533 | 0 | 0 |
| BPI 2014 | 46,606 | 0 | 0 | 203 |
| Loghub Apache | 0 | 0 | 2,000 | 0 |
| Loghub OpenStack | 0 | 0 | 2,000 | 0 |
| Loghub BGL | 0 | 0 | 2,000 | 0 |
| Loghub HDFS | 0 | 0 | 2,000 | 0 |
| Loghub Zookeeper | 0 | 0 | 2,000 | 0 |

Accepted tables contain no duplicate `(source, source_id)` keys or synthetic rows.
No accepted BPI 2013 events lack a matching incident within their source. These
checks establish internal key integrity, not relationships between datasets.

## Timestamp and completeness findings

- BPI 2013: all 7,554 incidents have normalized opening times and all 65,533 events
  have normalized occurrence times. Opening time is the first observed event, not
  guaranteed original incident creation. There are 1,981 missing closing times.
  Of 5,573 usable opening/closing pairs, none has a negative duration.
- BPI 2014: all 46,606 accepted incidents have null normalized opening and closing
  times under the default policy. Source date strings have no established timezone;
  this is deliberate uncertainty preservation, not evidence that source dates are absent.
  Do not calculate elapsed-time or SLA metrics without a justified timezone policy.
- Loghub BGL: all 2,000 rows have normalized timestamps from the epoch field.
- Apache, OpenStack, HDFS and Zookeeper: each has 2,000 null normalized occurrence
  times, while all raw timestamp fields are present. Do not silently assume UTC.
- Apache has no populated component field in the normalized output. Other sample
  component fields are populated. This affects component-level filtering.

## Distributions and interpretation

BPI 2013 contains 5,573 closed, 90 resolved, 2 in-progress and 1,889 unknown normalized
statuses. BPI 2014 contains 46,597 closed and 9 unknown statuses. Review source-status
mapping before changing it; unknown must remain explicit where semantics are unclear.
The strong closed-status prevalence limits evaluation of current incident triage.

| Log source | Info | Warning | Error | Critical | Unknown | Repeated message excess rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Apache | 1,405 | 0 | 595 | 0 | 0 | 1,114 |
| OpenStack | 1,969 | 31 | 0 | 0 | 0 | 452 |
| BGL | 1,597 | 8 | 41 | 347 | 7 | 633 |
| HDFS | 1,920 | 80 | 0 | 0 | 0 | 0 |
| Zookeeper | 669 | 1,318 | 13 | 0 | 0 | 1,307 |

Repeated message excess rows equals row count minus the number of distinct exact
messages within a source. It is not duplicate source identity, an anomaly score or
a root-cause label. These samples are not representative production distributions.

## Data engineering before agents

| Gate | Required work | Current evidence |
| --- | --- | --- |
| Source integrity | Preserve pinned checksums, source terms, Bronze immutability and provenance | Fresh acquisition and pipeline output checksum verification passed |
| Quality contracts | Enforce source keys, schema, timestamp policy and quarantine accounting | First-pass aggregate checks completed; recurring quality gates still needed |
| Source semantics | Review unknown statuses, missing IDs, timestamps and display labels | Gaps identified above; no unsupported remapping applied |
| Replay and persistence | Validate bounded loads, replay after interruption and backend failure | Existing targeted pipeline tests passed; fresh real-backend verification remains |
| Evidence contracts | Expose bounded, authorized source records with stable citations | Log tool boundary exists; incident/history/document tools still need completion |
| Investigation execution | Finish durable jobs, leases, recovery and cancellation | Local Phase C implementation remains unfinished |
| Evaluation data | Curate authorized documents and human-judged investigation cases | Current datasets do not establish root-cause or remediation ground truth |
| Agent readiness | Verify retrieval, tool authorization, citations and uncertainty before orchestration | Working agents remain planned |

The next work is data engineering verification and evidence access, not training a
model on these records. RAG and tool use can provide authorized evidence without
fine-tuning. Real enterprise sources require their own access, retention and quality
contracts. Never join BPI 2013, BPI 2014 and Loghub by coincidental IDs or timestamps.

## Verification boundary

The targeted acquisition, pipeline and profiler suite passed 12 tests in the first
run. This is fresh local verification, not a new GitHub Actions or backend result.
The full profiler output is `.local/eda/profile.json`. No latency, model quality,
GPU inference, live enterprise integration or Azure deployment claim is made here.
