# data/

Flujos Prefect (bronze -> silver -> gold) que alimentan `gold` en Azure SQL y registran `ops.pipeline_runs` / `ops.quality_checks` / `ops.quarantine_records`.

**Fuera del alcance de este prompt**. En local, el simulador llena `gold` y `POST /api/v1/ops/pipelines/run` simula una corrida.
