# Data Flow

```mermaid
flowchart TD
    A[CLI args: --seed --date --format --data --output] --> B[load_data(): scripts/checkin_data.json or --data]
    B --> C[build_record(seed, date, data)]
    C --> D[random.Random(seed).choice: pick one type]
    D --> E[draw time from the type's window]
    E --> F[pick location / device / note from their pools]
    F --> G[derive status from type + time]
    G --> H[assemble record: record_id / date / weekday / type / time / location / device / status / note]
    H --> I{format}
    I -- markdown --> J[render_markdown: table]
    I -- text --> K[render_text]
    I -- json --> L[render_json]
    J --> M[--output file or stdout]
    K --> M
    L --> M
```

All randomness is driven by a single `random.Random(seed)`, so a fixed `--seed` makes the
whole pipeline deterministic. No network, CLI, SDK, or cloud resource is involved at any
step.