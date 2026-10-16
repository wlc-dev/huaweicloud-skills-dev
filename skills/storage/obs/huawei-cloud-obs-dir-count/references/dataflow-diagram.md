# Data Flow Diagram

## Architecture Overview

```mermaid
graph LR
    subgraph Agent
        A[AI Agent]
    end
    subgraph Execution
        A -->|"1. hcloud OBS ls -d (primary)"| B[KooCLI OBS / obsutil]
        A -->|"2. count_obs_directories.py"| P[Python script]
        A -->|"3. huaweicloudsdkobs (fallback)"| C[Python SDK]
    end
    B --> D["Huawei Cloud OBS API<br/>GET /?prefix=&delimiter= (ListObjects)"]
    C --> D
    P --> B
    P --> C
    D --> E[(OBS Bucket)]
    E --> B
    E --> C
    B -->|"Folder number"| A
    C -->|"common prefixes count"| A
```

## Sequence Diagram

```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent
    participant P as count_obs_directories.py
    participant C as hcloud CLI (obsutil)
    participant S as Python SDK
    participant O as OBS Service

    U->>A: How many directories are in bucket X?
    A->>P: --bucket X
    P->>C: hcloud OBS ls obs://X/ -d
    C->>O: GET /?prefix=&delimiter=/
    O-->>C: common prefixes (directories)
    C-->>P: Folder number: N
    P-->>A: N
    A-->>U: N

    alt CLI unavailable
        A->>P: --bucket X --executor sdk
        P->>S: ListObjectsRequest(prefix, delimiter=/)
        S->>O: GET /?prefix=&delimiter=/
        O-->>S: common prefixes
        S-->>P: count
        P-->>A: N
        A-->>U: N
    end
