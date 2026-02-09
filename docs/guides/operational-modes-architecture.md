# Session-Buddy Operational Modes - Architecture Diagram

## Mode Selection Flow

```mermaid
flowchart TD
    Start([Session-Buddy Start]) --> CheckEnv{SESSION_BUDDY_MODE env var?}

    CheckEnv -->|Yes| UseEnv[Use Environment Mode]
    CheckEnv -->|No| CheckCLI{--mode parameter?}

    CheckCLI -->|Yes| UseCLI[Use CLI Mode]
    CheckCLI -->|No| UseDefault[Use Default: Standard]

    UseEnv --> ValidateMode{Validate Mode}
    UseCLI --> ValidateMode
    UseDefault --> ValidateMode

    ValidateMode -->|lite| InitLite[Initialize Lite Mode]
    ValidateMode -->|standard| InitStandard[Initialize Standard Mode]
    ValidateMode -->|invalid| Error[Invalid Mode Error]

    InitLite --> LoadLiteConfig[Load settings/lite.yaml]
    InitStandard --> LoadStdConfig[Load settings/standard.yaml]

    LoadLiteConfig --> CreateDB[Create Database Connection]
    LoadStdConfig --> CreateDB

    CreateDB --> DBType{Database Type?}

    DBType -->|:memory:| InMemoryDB[In-Memory Database]
    DBType -->|file path| FileDB[File-Based Database]

    InMemoryDB --> StartServer[Start MCP Server]
    FileDB --> StartServer

    StartServer --> Ready([Session-Buddy Ready])

    style InitLite fill:#c8e6c9
    style InitStandard fill:#b2dfdb
    style InMemoryDB fill:#fff9c4
    style FileDB fill:#b2dfdb
    style Ready fill:#ffccbc
```

## Mode Comparison Matrix

```mermaid
graph LR
    subgraph Lite Mode
        L1[⚡ Fast Startup]
        L2[💾 No Persistence]
        L3[📦 Minimal Features]
        L4[🧪 Testing/CI/CD]
    end

    subgraph Standard Mode
        S1[💾 Persistent Storage]
        S2[🧠 Full Features]
        S3[🌐 Multi-Project]
        S4[🚀 Production Ready]
    end

    Lite[Lite Mode] --> L1
    Lite --> L2
    Lite --> L3
    Lite --> L4

    Standard[Standard Mode] --> S1
    Standard --> S2
    Standard --> S3
    Standard --> S4

    style Lite fill:#fff9c4
    style Standard fill:#b2dfdb
```

## Architecture Components

```mermaid
classDiagram
    class OperationMode {
        <<abstract>>
        +name: str
        +get_config() ModeConfig
        +validate_environment() list[str]
        +get_startup_message() str
    }

    class LiteMode {
        +name: "lite"
        +get_config() ModeConfig
        +get_startup_message() str
    }

    class StandardMode {
        +name: "standard"
        +get_config() ModeConfig
        +validate_environment() list[str]
        +get_startup_message() str
    }

    class ModeConfig {
        +name: str
        +database_path: str
        +storage_backend: str
        +enable_embeddings: bool
        +enable_multi_project: bool
        +enable_token_optimization: bool
        +enable_auto_checkpoint: bool
        +to_dict() dict
    }

    class ReflectionDatabase {
        +db_path: str
        +is_temp_db: bool
        +initialize() async
        +store_conversation() async
        +search_conversations() async
    }

    OperationMode <|-- LiteMode
    OperationMode <|-- StandardMode
    LiteMode --> ModeConfig
    StandardMode --> ModeConfig
    ModeConfig --> ReflectionDatabase
```

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Mode
    participant Config
    participant Database
    participant Server

    User->>CLI: session-buddy --mode=lite start
    CLI->>Mode: get_mode("lite")
    Mode-->>CLI: LiteMode instance
    CLI->>Mode: get_config()
    Mode-->>Config: ModeConfig
    Config-->>CLI: {"database_path": ":memory:", ...}
    CLI->>Database: ReflectionDatabase(":memory:")
    Database->>Database: initialize()
    Database-->>Server: Connection ready
    Server-->>User: Session-Buddy ready (lite mode)
```

## Feature Flags

```mermaid
graph TD
    subgraph Lite Mode Features
        L1[Embeddings: Disabled]
        L2[Multi-Project: Disabled]
        L3[Token Optimization: Disabled]
        L4[Auto-Checkpoint: Disabled]
        L5[Faceted Search: Disabled]
        L6[Search Suggestions: Disabled]
        L7[Auto-Store: Disabled]
        L8[Crackerjack: Disabled]
        L9[Git Integration: Disabled]
    end

    subgraph Standard Mode Features
        S1[Embeddings: Enabled]
        S2[Multi-Project: Enabled]
        S3[Token Optimization: Enabled]
        S4[Auto-Checkpoint: Enabled]
        S5[Faceted Search: Enabled]
        S6[Search Suggestions: Enabled]
        S7[Auto-Store: Enabled]
        S8[Crackerjack: Enabled]
        S9[Git Integration: Enabled]
    end

    Mode[Mode Config] --> Lite{Lite Mode?}
    Mode --> Standard{Standard Mode?}

    Lite --> L1
    Lite --> L2
    Lite --> L3
    Lite --> L4
    Lite --> L5
    Lite --> L6
    Lite --> L7
    Lite --> L8
    Lite --> L9

    Standard --> S1
    Standard --> S2
    Standard --> S3
    Standard --> S4
    Standard --> S5
    Standard --> S6
    Standard --> S7
    Standard --> S8
    Standard --> S9

    style Lite fill:#fff9c4
    style Standard fill:#b2dfdb
```

## Startup Sequence Comparison

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Mode
    participant DB
    participant Storage
    participant Server

    Note over User,Server: Lite Mode Startup
    User->>CLI: --mode=lite
    CLI->>Mode: get_mode("lite")
    Mode->>DB: :memory:
    DB-->>CLI: Ready (< 2s)
    CLI->>Storage: memory backend
    Storage-->>CLI: Ready
    CLI->>Server: Start
    Server-->>User: Ready

    Note over User,Server: Standard Mode Startup
    User->>CLI: --mode=standard
    CLI->>Mode: get_mode("standard")
    Mode->>DB: ~/.claude/data/reflection.duckdb
    DB->>DB: Load embeddings (~2s)
    DB-->>CLI: Ready (~3-5s)
    CLI->>Storage: file backend
    Storage-->>CLI: Ready
    CLI->>Server: Start
    Server-->>User: Ready
```

## Configuration Layering

```mermaid
graph TD
    subgraph Configuration Layers
        Base[Base Config<br/>settings/session-buddy.yaml]
        Mode[Mode Config<br/>settings/lite.yaml or standard.yaml]
        Local[Local Config<br/>settings/local.yaml]
        Env[Environment Variables<br/>SESSION_BUDDY_MODE]
    end

    Final[Final Configuration]

    Base --> Mode
    Mode --> Local
    Local --> Env
    Env --> Final

    style Base fill:#e1f5fe
    style Mode fill:#fff9c4
    style Local fill:#f3e5f5
    style Env fill:#e8f5e9
    style Final fill:#ffccbc
```

## Deployment Scenarios

```mermaid
flowchart TD
    subgraph Development
        Dev1[Local Development<br/>Standard Mode]
        Dev2[Feature Testing<br/>Lite Mode]
        Dev3[Quick Experiment<br/>Lite Mode]
    end

    subgraph Testing
        Test1[Unit Tests<br/>Lite Mode]
        Test2[Integration Tests<br/>Lite Mode]
        Test3[E2E Tests<br/>Standard Mode]
    end

    subgraph Production
        Prod1[Development Server<br/>Standard Mode]
        Prod2[Production Server<br/>Standard Mode]
    end

    User[Developer] --> Dev1
    User --> Dev2
    User --> Dev3

    CI[CI/CD Pipeline] --> Test1
    CI --> Test2
    CI --> Test3

    Ops[Operations] --> Prod1
    Ops --> Prod2

    style Dev2 fill:#fff9c4
    style Dev3 fill:#fff9c4
    style Test1 fill:#fff9c4
    style Test2 fill:#fff9c4
    style Dev1 fill:#b2dfdb
    style Test3 fill:#b2dfdb
    style Prod1 fill:#b2dfdb
    style Prod2 fill:#b2dfdb
```

## Performance Metrics

```mermaid
graph LR
    subgraph Lite Mode
        LStart[Startup: 1-2s]
        LMem[Memory: 50MB]
        LDB[Database: 0MB]
    end

    subgraph Standard Mode
        SStart[Startup: 3-5s]
        SMem[Memory: 50-200MB]
        SDB[Database: 1-50MB]
    end

    Lite[Lite Mode] --> LStart
    Lite --> LMem
    Lite --> LDB

    Standard[Standard Mode] --> SStart
    Standard --> SMem
    Standard --> SDB

    style Lite fill:#fff9c4
    style Standard fill:#b2dfdb
```
