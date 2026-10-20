# EDA evidence and change record

Recorded 2026-10-15. These are measured public-data findings, not live enterprise
results. PNG files are exported analytical figures, not screenshots of a running
agent or Azure service. No upload or deployment is recorded by this work.

Verification: the notebook executed and passed notebook-format validation using
Python 3.11.9. All 14 targeted acquisition, pipeline and EDA tests passed. Ruff
lint/format checks and the repository's limited tracked-file exposure check passed.
All three PNGs were visually inspected. This is local evidence, not fresh CI.

## Goal and why agents belong

Build an evidence-grounded incident investigation assistant. It should select
authorized tools, inspect results, decide what to investigate next, retrieve
relevant operational guidance, and return a cited report with uncertainties and
proposed next steps. Consequential actions require a separately implemented human
approval and execution boundary. A conversational interface is only an entry point.

Use deterministic code for counts, joins, access control and statistics. Start with
one tool-using investigator; add specialist agents only when evaluation demonstrates
a benefit. Compare the investigator against search-and-summary on identical cases.
Measure evidence correctness, task completion, unsupported claims, latency, cost
and recovery. These agent results are not measured yet.

This direction has industry precedent: [Azure SRE Agent incident response](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
describes investigations and action review; [Microsoft Research](https://www.microsoft.com/en-us/research/publication/exploring-llm-based-agents-for-root-cause-analysis/?lang=fr-ca)
evaluates agents with retrieval tools on production incidents. Neither establishes
the performance of this repository.

## Changes and improvements

| Before | Added | Why it matters | Evidence |
| --- | --- | --- | --- |
| Counts and missing values only | Missing percentages and timestamp coverage chart | Makes unsupported time analysis visible | 01-timestamp-readiness.png |
| Duration pair count only | Median, p90, p95, maximum and distribution | Shows skew and tail cases without assuming averages are representative | 02-observed-durations.png |
| No path profile | Source-order event counts, transitions and repeated activities | Identifies questions requiring source lifecycle interpretation | 03-activity-transitions.png |
| Exact message repetition only | Character-length distributions and component coverage | Helps scope bounded log retrieval; character counts are not model tokens | analysis.json |
| No presentation evidence | Reproducible notebook, figures and this record | Supports a reviewable project history | notebooks/eda_public_data.ipynb |

Source-order activity transitions are not a reconstructed timestamp timeline or a
verified incident-state machine. The frequent Accepted-to-Accepted transition does
not establish a reopening, reassignment, failure or wasted work.

## Measured findings

- BPI 2013: median 6 events per incident, p95 23, maximum 123.
- There are 535 distinct source-order activity paths; 7,539 of 7,554 cases repeat
  at least one activity label. Activity alone is insufficient to describe state.
- Among 5,573 complete normalized opening/closing pairs, observed duration median
  is 199.33 hours, p90 671.89 hours and p95 1,138.77 hours. Opening is the first
  observed event. Excluding 1,981 incomplete cases can bias these summaries.
- No BPI 2014 duration estimate is produced under the unknown-timezone policy.
- HDFS sample maximum message length is 2,480 characters; this is not a token
  limit recommendation or a population-wide maximum.

## Research that informed the analysis

- [Kaggle incident management notebook](https://www.kaggle.com/code/zhefeijin/incident-management-2):
  publicly visible contents identify distributions and feature understanding before
  prediction. Full notebook cells were not accessible through the research browser.
- [GitHub incident analysis](https://github.com/ARGULASAISURAJ/Incident_Management_Analysis):
  documents separate event-level and one-row-per-incident datasets.
- [GitHub ITSM dashboard](https://github.com/AnkurTechStack/ITSM_Incident_Management):
  documents resolution, closure and reassignment analysis. Its business-impact
  numbers are not adopted as project results.
- [Loglizer](https://github.com/logpai/loglizer): parses logs and forms session/time
  windows before feature extraction. Session and template analysis remains future
  work here; exact repeated text is not a parsed template.
- [Loghub](https://github.com/logpai/loghub): documents source-specific scope and
  label availability. Our 2,000-row inputs are samples, not full archives.

## Reproduce

From the repository root, using Python 3.11:

```sh
uv sync --frozen --python 3.11 --group eda
uv run --group eda python -m src.ingestion.cli all --full
uv run --group eda python -m scripts.eda_evidence
uv run --group eda pytest tests/test_pipeline.py tests/test_acquire.py tests/test_data_profile.py tests/test_eda_evidence.py -q
```

The notebook calls the same analysis implementation. Every run validates recorded
pipeline output checksums. `analysis.json` includes run IDs, checksums, parser and
pipeline versions. Raw records and incident identifiers are not exported here.

## Evidence to publish and evidence still needed

| Item | Status | Caption |
| --- | --- | --- |
| Three PNG figures and notebook | Generated locally | Public-dataset EDA and limitations |
| Aggregate JSON and change record | Generated locally | Reproducible analysis provenance |
| Current test result | 14 targeted tests passed | Local targeted verification, not CI |
| GitHub Actions screenshot | Requires a new CI run | Include the tested commit |
| Agent tool-call trace and cited report | Agent execution not implemented | Show tool inputs/outputs with sensitive values removed |
| Agent versus baseline comparison | Evaluation cases needed | Use the same cases, sources and scoring criteria |
| Azure deployment screenshot | Not deployed | Include the resource and deployment date |
| Latency, throughput, GPU memory, recovery graphs | Model benchmarks not run | Include hardware, model, workload and failure scenario |

Upload the figures with their captions, the notebook and this record when publishing
the project. Preserve source notices and attribution. Do not upload raw datasets,
credentials, internal enterprise records or screenshots with account secrets.

## Next data requirements

Public BPI and Loghub sources are independent. They support separate analysis and
tool tests, not a joined root-cause investigation. To evaluate the agent, obtain
authorized incident, log, change and runbook records with real shared identifiers,
or use explicitly labeled synthetic connected scenarios for functional tests.
Human-reviewed answers are needed to score investigation quality.
