# Dataset and pipeline flow

## Acquisition invariants

`src.ingestion.cli.main` accepts one manifest key or `all`. `--input` requires one dataset and an explicit SHA-256. `--index` requires `--load`. The manifest is trusted operator configuration; it is not accepted from HTTP.

`src.ingestion.acquire.download` validates the original URL and every redirect. It uses identity transfer encoding, a 30-second HTTP timeout, a 120-second total budget, six-request redirect bound, declared byte limit, and expected checksum. It writes a `.partial` file and removes it on failure.

`acquire` rejects unsafe dataset names and filenames. It locks each raw directory, verifies existing bytes, writes `provenance.json`, and writes the checked-in Loghub notice next to Loghub data.

## Processing invariants

`src.pipelines.runner.process` supports exactly seven dataset keys. Its run ID hashes pipeline version, dataset, input checksum, limit, timezone, and parser. A completed run is reusable only when every recorded output exists and matches its checksum.

Bronze paths contain the dataset key and checksum. Existing Bronze bytes must match. New bytes pass through a temporary file before atomic promotion.

Parsers emit Pydantic records or quarantine dictionaries. Silver uses explicit PyArrow schemas and Zstandard compression. Attributes become sorted JSON strings in Parquet. Buffers flush at 1000 records.

Non-log records are deduplicated within a run by kind and source ID. Log IDs derive from file checksum and line number.

Gold contains incident status counts, incident history, ordered timelines, log severity counts, and repeated messages. Repetition is an aggregate, not an anomaly or root-cause claim.

## Persistence and replay

`src.pipelines.load.load_silver` reads Silver in batches. SQL inserts use dialect-specific conflict handling on `(source, source_id)`.

OpenSearch indexing is optional. `ensure_index` creates a strict mapping. Bulk writes use deterministic IDs and a maximum batch of 1000. Retryable item failures retry; permanent schema failures stop.

The database commits before search indexing. There is no distributed transaction. Re-running the same Silver output is the recovery mechanism.

## Dataset boundaries

BPI 2013, BPI 2014, and each Loghub source are independent. The code does not correlate them. BPI 2013 opening time is the first observed event. BPI 2014 naive timestamps stay unset unless the operator supplies a timezone.

Status: **Complete** for checked-in manifest sources. Scheduled extraction, document parsing, and live connectors are **Planned**.
