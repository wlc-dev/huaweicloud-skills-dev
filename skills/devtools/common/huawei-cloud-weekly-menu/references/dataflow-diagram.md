# Data Flow Diagram

```mermaid
flowchart TD
    A[User request: generate a weekly menu] --> B[scripts/generate_weekly_menu.py]
    B --> C[load_dishes(): scripts/dishes.json]
    C --> D[pick_week(seed, days, meals, dedup)]
    D --> E{dedup enabled?}
    E -- yes --> F[Exclude dishes already used in the same meal slot this week]
    E -- no --> G[Draw from the full pool]
    F --> H[random.Random(seed).choice]
    G --> H
    H --> I[Assemble week: day -> meal -> dish]
    I --> J{format}
    J -- markdown --> K[render_markdown()]
    J -- text --> L[render_text()]
    J -- json --> M[render json]
    K --> N[stdout or --output file]
    L --> N
    M --> N
```

No network, CLI, SDK, or cloud resource is involved at any step.