-- PostgreSQL analytics, intentionally partitioned by source and incident.
-- No joins based on coincidental identifiers across independent datasets.
WITH ordered_events AS (
    SELECT source, incident_id, source_id, activity, occurred_at,
           lag(activity) OVER (
               PARTITION BY source, incident_id ORDER BY occurred_at, source_id
           ) AS previous_activity,
           lag(occurred_at) OVER (
               PARTITION BY source, incident_id ORDER BY occurred_at, source_id
           ) AS previous_time
    FROM incident_events
), transitions AS (
    SELECT source, incident_id, source_id, activity, previous_activity,
           occurred_at - previous_time AS elapsed_since_previous
    FROM ordered_events
    WHERE previous_time IS NOT NULL
)
SELECT source, previous_activity, activity,
       count(*) AS transition_count,
       avg(elapsed_since_previous) AS mean_elapsed
FROM transitions
GROUP BY source, previous_activity, activity
ORDER BY source, transition_count DESC;

-- Observed incident volume and change from the previous observed day.
-- Missing calendar days are not imputed as zero.
WITH daily AS (
    SELECT source, date_trunc('day', opened_at AT TIME ZONE 'UTC') AS observed_day,
           count(*) AS incident_count
    FROM incidents
    WHERE opened_at IS NOT NULL
    GROUP BY source, observed_day
)
SELECT source, observed_day, incident_count,
       incident_count - lag(incident_count) OVER (
           PARTITION BY source ORDER BY observed_day
       ) AS delta_from_previous_observed_day
FROM daily
ORDER BY source, observed_day;
