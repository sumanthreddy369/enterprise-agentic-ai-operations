# Dataset catalog and reproducibility

This guide reflects the repository manifest verified on 2026-09-25; this documentation update did not redownload data. The [manifest](../data/dataset_manifest.json) is authoritative for exact URLs, SHA-256 checksums, byte counts and source schemas. The [verification report](verification.md) records measured parsing outcomes.

## Inventory

| Dataset | Acquired records | Bytes | Purpose |
| --- | ---: | ---: | --- |
| [Loghub Apache](https://github.com/logpai/loghub) | 2,000 rows/lines | 171,239 | Independent log parsing, severity distributions and repeated-message features |
| [Loghub OpenStack](https://github.com/logpai/loghub) | 2,000 rows/lines | 595,119 | Independent log parsing, severity distributions and repeated-message features |
| [Loghub BGL](https://github.com/logpai/loghub) | 2,000 rows/lines | 317,150 | Independent log parsing, severity distributions and repeated-message features |
| [Loghub HDFS](https://github.com/logpai/loghub) | 2,000 rows/lines | 287,848 | Independent log parsing, severity distributions and repeated-message features |
| [Loghub Zookeeper](https://github.com/logpai/loghub) | 2,000 rows/lines | 279,891 | Independent log parsing, severity distributions and repeated-message features |
| [BPI Challenge 2013, incidents](https://figshare.com/articles/dataset/_/12693914) | 7,554 traces / 65,533 events | 1,322,247 | Historical incident status analysis and observed event timelines |
| [BPI Challenge 2014: Incident details](https://figshare.com/articles/dataset/_/12692378) | 46,809 rows/lines | 14,306,331 | Historical incident status analysis and closure duration where timestamps are usable |

BPI 2013 and BPI 2014 are independent releases. None of the Loghub logs joins to either release. Do not present cross-dataset correlations as real incident evidence. These sources do not provide a labeled root-cause or remediation evaluation set. Synthetic test fixtures are separate from acquired data.

## Source details

### Loghub Apache (`loghub-apache`)

- File: `Apache_2k.log`; format: UTF-8 text, source-specific log format.
- [Acquisition URL](https://raw.githubusercontent.com/logpai/loghub/dd61d0952749ee7963bde24220d1be5ede023033/Apache/Apache_2k.log); [source terms recorded in manifest](https://github.com/logpai/loghub/blob/dd61d0952749ee7963bde24220d1be5ede023033/LICENSE).
- SHA-256: `c7efa3eb686e3a96bd2f8f4457b2a7887e9cf2f3649327f1b4e87af841363ce8`.
- Pinned source revision: `dd61d0952749ee7963bde24220d1be5ede023033`.
- Reference structured schema (the pipeline parses raw lines): LineId, Time, Level, Content, EventId, EventTemplate.
- Samples are not representative timelines.
- No shared BPI incident identifiers.
- Source local timezone is unspecified (BGL epoch is usable).
- Raw logs may contain identifiers; do not publish raw data.
- [Full archive](https://zenodo.org/records/8196385/files/Apache.tar.gz?download=1): publisher reports 56,481 records, 4.90 MiB. Archive was not downloaded or checksummed; these are not local validation results.

### Loghub OpenStack (`loghub-openstack`)

- File: `OpenStack_2k.log`; format: UTF-8 text, source-specific log format.
- [Acquisition URL](https://raw.githubusercontent.com/logpai/loghub/dd61d0952749ee7963bde24220d1be5ede023033/OpenStack/OpenStack_2k.log); [source terms recorded in manifest](https://github.com/logpai/loghub/blob/dd61d0952749ee7963bde24220d1be5ede023033/LICENSE).
- SHA-256: `025a1bc64ff5b2ef4a4bda6c4ad5c5c5f18478b71cd1ad2b0676e01625629f2f`.
- Pinned source revision: `dd61d0952749ee7963bde24220d1be5ede023033`.
- Reference structured schema (the pipeline parses raw lines): LineId, Logrecord, Date, Time, Pid, Level, Component, ADDR, Content, EventId, EventTemplate.
- Samples are not representative timelines.
- No shared BPI incident identifiers.
- Source local timezone is unspecified (BGL epoch is usable).
- Raw logs may contain identifiers; do not publish raw data.
- [Full archive](https://zenodo.org/records/8196385/files/OpenStack.tar.gz?download=1): publisher reports 207,820 records, 58.61 MiB. Archive was not downloaded or checksummed; these are not local validation results.

### Loghub BGL (`loghub-bgl`)

- File: `BGL_2k.log`; format: UTF-8 text, source-specific log format.
- [Acquisition URL](https://raw.githubusercontent.com/logpai/loghub/dd61d0952749ee7963bde24220d1be5ede023033/BGL/BGL_2k.log); [source terms recorded in manifest](https://github.com/logpai/loghub/blob/dd61d0952749ee7963bde24220d1be5ede023033/LICENSE).
- SHA-256: `2a819ea540909db682005c9cf948387a40729b5c2e9f19d430e29ce704825496`.
- Pinned source revision: `dd61d0952749ee7963bde24220d1be5ede023033`.
- Reference structured schema (the pipeline parses raw lines): LineId, Label, Timestamp, Date, Node, Time, NodeRepeat, Type, Component, Level, Content, EventId, EventTemplate.
- Samples are not representative timelines.
- No shared BPI incident identifiers.
- Source local timezone is unspecified (BGL epoch is usable).
- Raw logs may contain identifiers; do not publish raw data.
- [Full archive](https://zenodo.org/records/8196385/files/BGL.zip?download=1): publisher reports 4,747,963 records, 708.76 MiB. Archive was not downloaded or checksummed; these are not local validation results.

### Loghub HDFS (`loghub-hdfs`)

- File: `HDFS_2k.log`; format: UTF-8 text, source-specific log format.
- [Acquisition URL](https://raw.githubusercontent.com/logpai/loghub/dd61d0952749ee7963bde24220d1be5ede023033/HDFS/HDFS_2k.log); [source terms recorded in manifest](https://github.com/logpai/loghub/blob/dd61d0952749ee7963bde24220d1be5ede023033/LICENSE).
- SHA-256: `7c967000980c086ed55fa6544ba4f05fe66d44622795e890c68caf8bbb635035`.
- Pinned source revision: `dd61d0952749ee7963bde24220d1be5ede023033`.
- Reference structured schema (the pipeline parses raw lines): LineId, Date, Time, Pid, Level, Component, Content, EventId, EventTemplate.
- Samples are not representative timelines.
- No shared BPI incident identifiers.
- Source local timezone is unspecified (BGL epoch is usable).
- Raw logs may contain identifiers; do not publish raw data.
- [Full archive](https://zenodo.org/records/8196385/files/HDFS_v1.zip?download=1): publisher reports 11,175,629 records, 1.47 GiB. Archive was not downloaded or checksummed; these are not local validation results.

### Loghub Zookeeper (`loghub-zookeeper`)

- File: `Zookeeper_2k.log`; format: UTF-8 text, source-specific log format.
- [Acquisition URL](https://raw.githubusercontent.com/logpai/loghub/dd61d0952749ee7963bde24220d1be5ede023033/Zookeeper/Zookeeper_2k.log); [source terms recorded in manifest](https://github.com/logpai/loghub/blob/dd61d0952749ee7963bde24220d1be5ede023033/LICENSE).
- SHA-256: `e40e0af5ef9eb6e4097200f260b9d1f626b3676f861a432e87977242e75543d8`.
- Pinned source revision: `dd61d0952749ee7963bde24220d1be5ede023033`.
- Reference structured schema (the pipeline parses raw lines): LineId, Date, Time, Level, Node, Component, Id, Content, EventId, EventTemplate.
- Samples are not representative timelines.
- No shared BPI incident identifiers.
- Source local timezone is unspecified (BGL epoch is usable).
- Raw logs may contain identifiers; do not publish raw data.
- [Full archive](https://zenodo.org/records/8196385/files/Zookeeper.tar.gz?download=1): publisher reports 74,380 records, 9.95 MiB. Archive was not downloaded or checksummed; these are not local validation results.

### BPI Challenge 2013, incidents (`bpi-2013`)

- File: `BPI_Challenge_2013_incidents.xes.gz`; format: gzip XES XML.
- [Acquisition URL](https://ndownloader.figshare.com/files/24033593); [source terms recorded in manifest](https://doi.org/10.4121/resource:terms_of_use).
- SHA-256: `6ec2136c607648608655802486df97a866f351668751b7ecbca51e1f8715d522`.
- Observed source fields: trace: concept:name; event: org:group, resource country, organization country, org:resource, organization involved, org:role, concept:name, impact, product, lifecycle:transition, time:timestamp.
- No relationship to Loghub or the other BPI release.
- Title is not provided; generated display label is not a source description.
- No narrative corrective-action knowledge is inferred.
- 2013 first event is not guaranteed creation time.

### BPI Challenge 2014: Incident details (`bpi-2014`)

- File: `Detail_Incident.csv`; format: UTF-8 semicolon CSV.
- [Acquisition URL](https://ndownloader.figshare.com/files/24031637); [source terms recorded in manifest](https://doi.org/10.4121/resource:terms_of_use).
- SHA-256: `621ad800120ffa2f022c9b93d13aec3adc86da7cae4938150c0859d59ef29de3`.
- Observed source fields: CI Name (aff), CI Type (aff), CI Subtype (aff), Service Component WBS (aff), Incident ID, Status, Impact, Urgency, Priority, Category, KM number, Alert Status, # Reassignments, Open Time, Reopen Time, Resolved Time, Close Time, Handle Time (Hours), Closure Code, # Related Interactions, Related Interaction, # Related Incidents, # Related Changes, Related Change, CI Name (CBy), CI Type (CBy), CI Subtype (CBy), ServiceComp WBS (CBy).
- No relationship to Loghub or the other BPI release.
- Title is not provided; generated display label is not a source description.
- No narrative corrective-action knowledge is inferred.
- Date strings use day/month/year and have no timezone; trailing unnamed CSV columns retained.

## Acquisition and transformation

From the repository root after completing the README setup:

```sh
uv run ops-data all --limit 100 --load
uv run ops-data all --full
uv run ops-data bpi-2014 --full --timezone Europe/Amsterdam
```

Default runs process 100 records per source or 100 complete BPI 2013 traces. `--full` processes the acquired file; for Loghub that is still the 2,000-line sample. The timezone argument is an explicit assumption, not established source metadata. Offset-bearing timestamps normalize to UTC; naive times remain null unless a timezone is provided. Original strings remain available.

Bronze preserves original bytes; Silver stores validated source-scoped records in Parquet; Gold contains aggregate analytics. Quarantine retains rejected records, and manifests record checksums, parser versions, counts and replay identity. BPI 2014 has 203 rows without incident IDs: 46,606 of 46,809 rows were accepted, without inventing IDs. See the README for database loading and OpenSearch indexing.

Full archives require separate download, extraction, source-term review and checksum recording. Import the verified uncompressed file with `--input` and `--sha256`; archives are not automatically extracted. Changing a pinned checksum requires review rather than silent replacement.

## Publication and future datasets

Git tracks code, source metadata, schemas and documentation. Raw/acquired data, generated Parquet, quarantine records, runtime databases, credentials and model weights remain local through `.gitignore`. Ignore rules do not remove already tracked files or replace secret scanning. Preserve the [Loghub notice](LOGHUB-LICENSE.txt); this project's source-code license does not relicense third-party datasets. Dataset terms above are recorded provenance, not a new licensing determination.

Later phases will add authorized operational documents with ACLs and versioned citations, and independently curated golden evaluation cases with human relevance judgments. No such corpus, retrieval scores or live enterprise feed is claimed today. Do not create hourly jobs that describe unchanged historical benchmarks as current incidents.
