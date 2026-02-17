# AI Maestro Feature Analysis for Session Buddy

**Date:** 2025-01-24
**Analysis of:** [AI Maestro v0.19.0](https://github.com/23blocks-OS/ai-maestro)
**Purpose:** Identify features that would enhance Session Buddy

---

## Executive Summary

AI Maestro and Session Buddy serve complementary but different purposes:

| Aspect | AI Maestro | Session Buddy |
|--------|-----------|---------------|
| **Architecture** | Multi-agent orchestrator (tmux sessions + web dashboard) | MCP server for single Claude Code instance |
| **Focus** | Managing multiple AI agents across machines | Session context, memory, and search |
| **Storage** | CozoDB (graph-relational) per agent | DuckDB (vector + relational) centralized |
| **Communication** | Agent-to-agent messaging | Multi-project coordination |

**Key Insight:** These systems can work together - Session Buddy provides the memory backend, AI Maestro provides the orchestration frontend.

---

## 🎯 Top Recommended Features

### 1. Agent Communication System ⭐⭐⭐⭐⭐
**Priority: HIGH** | **Effort: MEDIUM**

AI Maestro's file-based messaging system would dramatically enhance Session Buddy's multi-project coordination.

#### What AI Maestro Has

- **Persistent message queue** with inbox/outbox per agent
- **Priority levels:** urgent, high, normal, low
- **Message types:** request, response, notification, update
- **Cross-host messaging** via mesh network
- **Message forwarding** with context preservation
- **CLI scripts** for shell integration

#### Data Model (from AI Maestro)

```typescript
interface Message {
  id: string
  from: string              // Agent ID
  fromAlias?: string        // Display name
  fromSession?: string      // Actual tmux session
  fromHost?: string         // Host machine
  to: string                // Recipient agent ID
  toAlias?: string
  toSession?: string
  toHost?: string
  timestamp: string
  subject: string
  priority: 'low' | 'normal' | 'high' | 'urgent'
  status: 'unread' | 'read' | 'archived'
  content: {
    type: 'request' | 'response' | 'notification' | 'update'
    message: string
    context?: Record<string, any>
    attachments?: Array<{name, path, type}>
  }
  inReplyTo?: string
  forwardedFrom?: {
    originalMessageId: string
    originalFrom: string
    originalTo: string
    originalTimestamp: string
    forwardedBy: string
    forwardedAt: string
    forwardNote?: string
  }
}
```

#### Proposed Session Buddy Implementation

```python
# session_buddy/tools/messaging_tools.py

from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)

class Priority(str, Literal["low", "normal", "high", "urgent"]):
    """Message priority levels"""
    pass

class MessageType(str, Literal["request", "response", "notification", "update"]):
    """Message types"""
    pass

class MessageContent(BaseModel):
    """Message content structure"""
    type: MessageType
    message: str
    context: dict[str, object] | None = None
    attachments: list[dict[str, str]] | None = None

class Message(BaseModel):
    """Inter-project message"""
    id: str
    from_project: str
    from_alias: str | None = None
    to_project: str
    to_alias: str | None = None
    timestamp: str
    subject: str
    priority: Priority
    status: Literal["unread", "read", "archived"]
    content: MessageContent
    in_reply_to: str | None = None

@mcp.tool()
async def send_project_message(
    from_project: str,
    to_project: str,
    subject: str,
    message: str,
    priority: Priority = Priority.NORMAL,
    message_type: MessageType = MessageType.NOTIFICATION,
    context: dict[str, object] | None = None
) -> dict[str, object]:
    """
    Send a structured message between projects.

    Enables backend projects to notify frontend projects when APIs are ready,
    or for QA projects to alert development projects of test failures.

    Args:
        from_project: Source project identifier
        to_project: Target project identifier
        subject: Message subject line
        message: Message body
        priority: Message priority (low, normal, high, urgent)
        message_type: Type of message (request, response, notification, update)
        context: Additional metadata/context

    Returns:
        Sent message with ID and metadata
    """
    try:
        msg_id = f"msg-{int(datetime.now().timestamp())}-{uuid.uuid4().hex[:8]}"

        message_obj = Message(
            id=msg_id,
            from_project=from_project,
            to_project=to_project,
            timestamp=datetime.now().isoformat(),
            subject=subject,
            priority=priority,
            status="unread",
            content=MessageContent(
                type=message_type,
                message=message,
                context=context
            )
        )

        # Store in DuckDB messages table
        async with ReflectionDatabase() as db:
            await db._store_message(message_obj)

        logger.info(
            "Message sent",
            from_project=from_project,
            to_project=to_project,
            message_id=msg_id,
            priority=priority
        )

        return {
            "success": True,
            "message_id": msg_id,
            "timestamp": message_obj.timestamp,
            "priority": priority
        }

    except Exception as e:
        logger.error("Failed to send message", error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def list_project_messages(
    project: str,
    status: Literal["unread", "read", "archived"] | None = None,
    priority: Priority | None = None
) -> dict[str, object]:
    """
    List messages for a project.

    Args:
        project: Project identifier
        status: Filter by status (optional)
        priority: Filter by priority (optional)

    Returns:
        List of messages with metadata
    """
    try:
        async with ReflectionDatabase() as db:
            messages = await db._list_messages(project, status, priority)

        return {
            "success": True,
            "messages": messages,
            "count": len(messages)
        }

    except Exception as e:
        logger.error("Failed to list messages", error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def forward_project_message(
    original_message_id: str,
    from_project: str,
    to_project: str,
    forward_note: str | None = None
) -> dict[str, object]:
    """
    Forward a message to another project with additional context.

    Args:
        original_message_id: ID of message to forward
        from_project: Project doing the forwarding
        to_project: Target project
        forward_note: Optional note to add to forwarded message

    Returns:
        Forwarded message with ID
    """
    try:
        async with ReflectionDatabase() as db:
            original = await db._get_message(from_project, original_message_id)
            if not original:
                return {"success": False, "error": "Message not found"}

            # Build forwarded content
            forwarded_content = f"""--- Forwarded Message ---
From: {original.from_project}
To: {original.to_project}
Sent: {original.timestamp}
Subject: {original.subject}

{original.content.message}
--- End of Forwarded Message ---"""

            if forward_note:
                forwarded_content = f"{forward_note}\n\n{forwarded_content}"

            # Send as new message
            result = await send_project_message(
                from_project=from_project,
                to_project=to_project,
                subject=f"Fwd: {original.subject}",
                message=forwarded_content,
                priority=original.priority,
                message_type=MessageType.NOTIFICATION
            )

            return result

    except Exception as e:
        logger.error("Failed to forward message", error=str(e))
        return {"success": False, "error": str(e)}
```

#### Database Schema Additions

```sql
-- Add to reflection_tools.py _ensure_tables()

CREATE TABLE IF NOT EXISTS project_messages (
    id TEXT PRIMARY KEY,
    from_project TEXT NOT NULL,
    from_alias TEXT,
    to_project TEXT NOT NULL,
    to_alias TEXT,
    timestamp TEXT NOT NULL,
    subject TEXT NOT NULL,
    priority TEXT NOT NULL,  -- 'low' | 'normal' | 'high' | 'urgent'
    status TEXT NOT NULL,     -- 'unread' | 'read' | 'archived'
    content_type TEXT NOT NULL,
    content_message TEXT NOT NULL,
    content_context JSON,
    in_reply_to TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_to_project
    ON project_messages(to_project, status, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_messages_from_project
    ON project_messages(from_project, timestamp DESC);
```

#### Real-World Use Cases

```python
# Backend API notifies frontend that endpoint is ready
await send_project_message(
    from_project="myapp-backend-api",
    to_project="myapp-frontend-dashboard",
    subject="User stats API ready",
    message="GET /api/stats implemented. Returns {activeUsers, signups, revenue}. "
            "Cached for 5min. Rate limited to 100/hour.",
    priority=Priority.HIGH,
    message_type=MessageType.NOTIFICATION
)

# Frontend responds after integration
await send_project_message(
    from_project="myapp-frontend-dashboard",
    to_project="myapp-backend-api",
    subject="Re: User stats API ready",
    message="Dashboard updated. Works perfectly. Thanks!",
    message_type=MessageType.RESPONSE,
    in_reply_to="msg-1234567890-abc123"
)

# QA alerts developers of test failure
await send_project_message(
    from_project="myapp-qa-tests",
    to_project="myapp-backend-api",
    subject="Test failure: POST /api/users",
    message="Integration test failing with 500 error. "
            "See test_report_20250124.html for details.",
    priority=Priority.URGENT,
    message_type=MessageType.NOTIFICATION,
    context={"test_file": "tests/api/test_users.py", "line": 142}
)
```

#### Integration with Existing Features

- **Multi-Project Coordinator:** Message delivery uses existing project relationships
- **Reflection Database:** Store messages in same DuckDB for unified search
- **Natural Scheduler:** Send reminders via project messages
- **Tmux Integration:** Optional terminal notifications for urgent messages

---

### 2. Code Graph Visualization & Indexing ⭐⭐⭐⭐⭐
**Priority: HIGH** | **Effort: HIGH**

AI Maestro's Code Graph provides deep codebase understanding that would dramatically improve Session Buddy's context awareness.

#### What AI Maestro Has

- **Multi-language AST parsing:** TypeScript, JavaScript, Ruby, Python
- **CozoDB storage:** Graph relationships (classes, functions, calls, imports)
- **Delta indexing:** ~100ms for changed files vs 1000ms+ full re-index
- **Interactive graph visualization:** Web-based explorer
- **Filter by type:** Files, Functions, Components
- **Focus mode:** Explore specific code paths

#### Data Model (from AI Maestro)

```typescript
// CozoDB schema (simplified)
interface CodeGraph {
  // Nodes
  files: {file_id, path, module, project_path}
  functions: {fn_id, name, file_id, is_export, lang}
  components: {component_id, name, file_id}  // React components
  classes: {class_id, name, file_id, class_type}

  // Edges
  declares: {file_id, fn_id}           // File declares function
  calls: {caller_fn, callee_fn}        // Function calls function
  component_calls: {component_id, fn_id}
  extends: {child_class, parent_class}
  imports: {from_file, to_file, module}
}
```

#### Proposed Session Buddy Implementation

```python
# session_buddy/code_graph.py

import ast
import asyncio
from pathlib import Path
from typing import Literal
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)

@dataclass
class CodeNode:
    """Base class for code nodes"""
    id: str
    name: str
    file_id: str
    node_type: Literal["file", "function", "class", "component"]

@dataclass
class FunctionNode(CodeNode):
    """Function or method"""
    is_export: bool
    start_line: int
    end_line: int
    calls: list[str]  # List of function names called
    lang: str = "python"

@dataclass
class ClassNode(CodeNode):
    """Class definition"""
    class_type: Literal["class", "interface", "type"]
    start_line: int
    end_line: int
    extends: str | None = None
    methods: list[str]  # Function IDs

@dataclass
class FileNode(CodeNode):
    """Source file"""
    path: str
    module: str
    language: str
    functions: list[FunctionNode]
    classes: list[ClassNode]

class CodeGraphAnalyzer:
    """Analyze and index codebase structure"""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.nodes: dict[str, CodeNode] = {}
        self.edges: dict[str, set[str]] = {}

    async def analyze_codebase(self) -> dict[str, object]:
        """
        Analyze entire codebase and build code graph.

        Returns:
            Statistics about indexed code
        """
        logger.info("Starting codebase analysis", path=str(self.project_path))

        python_files = list(self.project_path.rglob("*.py"))
        logger.info("Found Python files", count=len(python_files))

        stats = {
            "files_indexed": 0,
            "functions_indexed": 0,
            "classes_indexed": 0,
            "calls_indexed": 0
        }

        for file_path in python_files:
            try:
                result = await self._analyze_file(file_path)
                if result:
                    stats["files_indexed"] += 1
                    stats["functions_indexed"] += result["functions"]
                    stats["classes_indexed"] += result["classes"]
                    stats["calls_indexed"] += result["calls"]
            except Exception as e:
                logger.warning("Failed to analyze file", file=str(file_path), error=str(e))

        logger.info("Codebase analysis complete", **stats)
        return stats

    async def _analyze_file(self, file_path: Path) -> dict[str, int] | None:
        """Analyze a single Python file"""
        try:
            source = file_path.read_text()
            tree = ast.parse(source, filename=str(file_path))

            file_id = self._generate_file_id(file_path)
            module = self._get_module_name(file_path)

            functions = []
            classes = []
            call_count = 0

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func = self._parse_function(node, file_id)
                    functions.append(func)
                    call_count += len(func.calls)

                elif isinstance(node, ast.ClassDef):
                    cls = self._parse_class(node, file_id)
                    classes.append(cls)

            file_node = FileNode(
                id=file_id,
                name=file_path.name,
                file_id=file_id,
                node_type="file",
                path=str(file_path.relative_to(self.project_path)),
                module=module,
                language="python",
                functions=functions,
                classes=classes
            )

            # Store nodes
            self.nodes[file_id] = file_node
            for func in functions:
                self.nodes[func.id] = func
            for cls in classes:
                self.nodes[cls.id] = cls

            return {
                "functions": len(functions),
                "classes": len(classes),
                "calls": call_count
            }

        except SyntaxError as e:
            logger.warning("Syntax error in file", file=str(file_path), error=str(e))
            return None

    def _parse_function(self, node: ast.FunctionDef, file_id: str) -> FunctionNode:
        """Parse a function definition"""
        func_id = f"fn-{file_id}-{node.lineno}-{node.name}"

        # Find function calls
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)

        return FunctionNode(
            id=func_id,
            name=node.name,
            file_id=file_id,
            node_type="function",
            is_export=not node.name.startswith("_"),
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            calls=calls
        )

    def _parse_class(self, node: ast.ClassDef, file_id: str) -> ClassNode:
        """Parse a class definition"""
        class_id = f"cls-{file_id}-{node.lineno}-{node.name}"

        # Get base classes
        extends = None
        if node.bases:
            if isinstance(node.bases[0], ast.Name):
                extends = node.bases[0].id

        methods = [
            f"fn-{file_id}-{m.lineno}-{m.name}"
            for m in node.body
            if isinstance(m, ast.FunctionDef)
        ]

        return ClassNode(
            id=class_id,
            name=node.name,
            file_id=file_id,
            node_type="class",
            class_type="class",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            extends=extends,
            methods=methods
        )

    async def find_related_files(self, file_path: str) -> list[str]:
        """
        Find files that import or are imported by target file.

        Returns:
            List of related file paths
        """
        file_id = self._generate_file_id(Path(file_path))
        related = set()

        # Find files this file imports
        for edge_id, targets in self.edges.items():
            if file_id in targets:
                related.add(edge_id)

        # Find files that import this file
        related.update(self.edges.get(file_id, set()))

        return [
            self.nodes[fid].name
            for fid in related
            if fid in self.nodes and self.nodes[fid].node_type == "file"
        ]

    async def get_function_callers(
        self,
        function_name: str
    ) -> list[dict[str, object]]:
        """
        Find all functions that call this function.

        Returns:
            List of caller function info
        """
        callers = []

        for node in self.nodes.values():
            if isinstance(node, FunctionNode):
                if function_name in node.calls:
                    callers.append({
                        "function": node.name,
                        "file": self.nodes[node.file_id].name if node.file_id in self.nodes else node.file_id,
                        "line": node.start_line
                    })

        return callers

    def _generate_file_id(self, file_path: Path) -> str:
        """Generate unique file ID"""
        rel_path = file_path.relative_to(self.project_path)
        return str(rel_path).replace("/", "_").replace(".", "_")

    def _get_module_name(self, file_path: Path) -> str:
        """Extract module name from file path"""
        parts = file_path.relative_to(self.project_path).parts
        if parts[-1] == "__init__.py":
            return ".".join(parts[:-1])
        return ".".join(parts[:-1] + (parts[-1].replace(".py", ""),))

# MCP Tools
@mcp.tool()
async def index_code_graph(
    project_path: str
) -> dict[str, object]:
    """
    Analyze and index codebase structure.

    Builds a graph of files, functions, classes, and their relationships.
    Enables intelligent context compaction and better search results.

    Args:
        project_path: Path to project directory

    Returns:
        Indexing statistics
    """
    try:
        analyzer = CodeGraphAnalyzer(Path(project_path))
        stats = await analyzer.analyze_codebase()

        return {
            "success": True,
            "stats": stats,
            "message": f"Indexed {stats['files_indexed']} files with "
                      f"{stats['functions_indexed']} functions and "
                      f"{stats['classes_indexed']} classes"
        }

    except Exception as e:
        logger.error("Code graph indexing failed", error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def find_related_code(
    file_path: str,
    relationship_type: Literal["imports", "imported_by", "calls", "called_by"] = "imports"
) -> dict[str, object]:
    """
    Find code related to a specific file.

    Args:
        file_path: Path to source file
        relationship_type: Type of relationship to find

    Returns:
        List of related code elements
    """
    try:
        # Implementation depends on stored graph
        async with ReflectionDatabase() as db:
            related = await db._find_related_code(file_path, relationship_type)

        return {
            "success": True,
            "related": related,
            "count": len(related)
        }

    except Exception as e:
        logger.error("Failed to find related code", error=str(e))
        return {"success": False, "error": str(e)}
```

#### Database Schema Additions

```sql
-- Code graph tables
CREATE TABLE IF NOT EXISTS code_files (
    file_id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    module TEXT,
    project_path TEXT NOT NULL,
    language TEXT NOT NULL,
    indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS code_functions (
    fn_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    file_id TEXT NOT NULL,
    is_export BOOLEAN NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    language TEXT NOT NULL,
    FOREIGN KEY (file_id) REFERENCES code_files(file_id)
);

CREATE TABLE IF NOT EXISTS code_classes (
    class_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    file_id TEXT NOT NULL,
    class_type TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    extends TEXT,
    FOREIGN KEY (file_id) REFERENCES code_files(file_id)
);

CREATE TABLE IF NOT EXISTS code_calls (
    caller_fn TEXT NOT NULL,
    callee_fn TEXT NOT NULL,
    PRIMARY KEY (caller_fn, callee_fn),
    FOREIGN KEY (caller_fn) REFERENCES code_functions(fn_id),
    FOREIGN KEY (callee_fn) REFERENCES code_functions(fn_id)
);

CREATE TABLE IF NOT EXISTS code_imports (
    from_file TEXT NOT NULL,
    to_file TEXT NOT NULL,
    module TEXT,
    PRIMARY KEY (from_file, to_file),
    FOREIGN KEY (from_file) REFERENCES code_files(file_id),
    FOREIGN KEY (to_file) REFERENCES code_files(file_id)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_functions_file
    ON code_functions(file_id);

CREATE INDEX IF NOT EXISTS idx_functions_name
    ON code_functions(name);

CREATE INDEX IF NOT EXISTS idx_calls_caller
    ON code_calls(caller_fn);

CREATE INDEX IF NOT EXISTS idx_calls_callee
    ON code_calls(callee_fn);
```

#### Benefits for Session Buddy

1. **Smarter Context Compaction**
   - Know which files are related before compaction
   - Keep related files together in compacted context
   - Prioritize recently modified or frequently called functions

2. **Better Search Results**
   - Understand code relationships for semantic search
   - Find calling/called functions alongside search results
   - Provide context about why code is relevant

3. **Improved Quality Scoring**
   - Analyze code complexity (cyclomatic complexity from AST)
   - Measure coupling (number of imports/calls)
   - Detect code smells (long functions, deep inheritance)

4. **Automatic Documentation Generation**
   - Extract docstrings from indexed functions
   - Generate API documentation from code
   - Search through documented functions/classes

---

### 3. Portable Agent Configuration ⭐⭐⭐⭐
**Priority: MEDIUM-HIGH** | **Effort: LOW-MEDIUM**

AI Maestro's ability to export/import agent configurations would be valuable for Session Buddy users.

#### What AI Maestro Has

- **Export agents to .zip** with full configuration
- **Import with conflict detection**
- **Preview before importing**
- **Cross-host transfer**
- **Clone & backup agents**

#### Proposed Session Buddy Implementation

```python
# session_buddy/tools/portable_config.py

import zipfile
import json
from pathlib import Path
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

@mcp.tool()
async def export_session_config(
    session_id: str,
    include_reflections: bool = True,
    include_quality_history: bool = True,
    include_multi_project_config: bool = True
) -> dict[str, object]:
    """
    Export session configuration to a portable zip file.

    Creates a backup of session state, reflections, and configuration
    that can be imported into another Session Buddy instance.

    Args:
        session_id: Session identifier
        include_reflections: Include stored reflections
        include_quality_history: Include quality score history
        include_multi_project_config: Include project group configuration

    Returns:
        Zip file path and metadata
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"session_buddy_export_{session_id}_{timestamp}.zip"
        export_path = Path.home() / ".claude" / "exports" / zip_name
        export_path.parent.mkdir(parents=True, exist_ok=True)

        config_data = {
            "exported_at": datetime.now().isoformat(),
            "session_id": session_id,
            "version": "0.12.0",
            "includes": {
                "reflections": include_reflections,
                "quality_history": include_quality_history,
                "multi_project": include_multi_project_config
            }
        }

        with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Export configuration
            zipf.writestr("config.json", json.dumps(config_data, indent=2))

            # Export reflections if requested
            if include_reflections:
                async with ReflectionDatabase() as db:
                    reflections = await db._get_all_reflections(session_id)
                    zipf.writestr(
                        "reflections.json",
                        json.dumps(reflections, indent=2)
                    )

            # Export quality history if requested
            if include_quality_history:
                quality_file = Path.home() / ".claude" / "data" / "quality_history.json"
                if quality_file.exists():
                    zipf.write(quality_file, "quality_history.json")

            # Export multi-project config if requested
            if include_multi_project_config:
                project_config = Path.home() / ".claude" / "data" / "project_groups.json"
                if project_config.exists():
                    zipf.write(project_config, "project_groups.json")

        logger.info(
            "Session configuration exported",
            session_id=session_id,
            path=str(export_path),
            size_bytes=export_path.stat().st_size
        )

        return {
            "success": True,
            "export_path": str(export_path),
            "size_bytes": export_path.stat().st_size,
            "config": config_data
        }

    except Exception as e:
        logger.error("Failed to export session config", error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def import_session_config(
    zip_path: str,
    merge_strategy: Literal["preview", "merge", "replace"] = "preview"
) -> dict[str, object]:
    """
    Import session configuration from zip file.

    Args:
        zip_path: Path to exported zip file
        merge_strategy:
            - preview: Show what would be imported without making changes
            - merge: Merge with existing configuration
            - replace: Replace existing configuration

    Returns:
        Import plan with conflicts and changes
    """
    try:
        zip_file = Path(zip_path)
        if not zip_file.exists():
            return {"success": False, "error": "Zip file not found"}

        import_plan = {
            "config": None,
            "reflections": [],
            "quality_history": None,
            "project_groups": None,
            "conflicts": [],
            "changes": []
        }

        with zipfile.ZipFile(zip_file, 'r') as zipf:
            # Read configuration
            if 'config.json' in zipf.namelist():
                config_data = json.loads(zipf.read('config.json'))
                import_plan["config"] = config_data

            # Preview reflections
            if 'reflections.json' in zipf.namelist():
                reflections = json.loads(zipf.read('reflections.json'))
                import_plan["reflections"] = reflections
                import_plan["changes"].append(
                    f"Would import {len(reflections)} reflections"
                )

            # Check for conflicts
            async with ReflectionDatabase() as db:
                existing_reflections = await db._get_all_reflections(
                    import_plan["config"]["session_id"]
                )
                if existing_reflections:
                    import_plan["conflicts"].append(
                        f"Session has {len(existing_reflections)} existing reflections"
                    )

        # Preview mode - just return the plan
        if merge_strategy == "preview":
            return {
                "success": True,
                "merge_strategy": "preview",
                "import_plan": import_plan,
                "message": "Preview mode - no changes made"
            }

        # Actually perform import
        if merge_strategy in ["merge", "replace"]:
            # Implementation for actual import
            logger.info(
                "Importing session configuration",
                zip_path=zip_path,
                strategy=merge_strategy
            )
            # ... import logic here ...

        return {
            "success": True,
            "merge_strategy": merge_strategy,
            "import_plan": import_plan,
            "message": f"Configuration imported with {merge_strategy} strategy"
        }

    except Exception as e:
        logger.error("Failed to import session config", error=str(e))
        return {"success": False, "error": str(e)}
```

#### Use Cases

1. **Session Backup**
   ```bash
   # Before major refactoring
   await export_session_config(
       session_id="session-buddy-main",
       include_reflections=True,
       include_quality_history=True
   )
   ```

2. **Cross-Machine Migration**
   ```bash
   # Export from laptop
   await export_session_config("my-project")

   # Transfer zip to desktop, then import
   await import_session_config(
       "/path/to/export.zip",
       merge_strategy="merge"
   )
   ```

3. **Team Template Sharing**
   ```bash
   # Create optimized session configuration
   await export_session_config("template-optimized")

   # Share with team
   # Team members import with merge strategy
   ```

---

### 4. Conversation Memory Browser ⭐⭐⭐⭐
**Priority: MEDIUM** | **Effort: LOW-MEDIUM**

AI Maestro's conversation history with semantic search complements Session Buddy's reflection system.

#### What AI Maestro Has

- **Full conversation history browser**
- **Semantic search** across conversations
- **Track model usage** and statistics
- **Browse thinking messages** and tool usage

#### Proposed Session Buddy Enhancement

Session Buddy already has `search_reflections` - extend it to full conversation browsing:

```python
# Enhanced version of existing search_reflections

@mcp.tool()
async def search_conversations(
    query: str,
    filters: dict[str, object] | None = None,
    limit: int = 20
) -> dict[str, object]:
    """
    Search across full conversation history with filters.

    Extends search_reflections to include:
    - Conversation metadata (model, timestamp, duration)
    - Tool usage patterns
    - Thinking/reasoning chains
    - Quality metrics

    Args:
        query: Search query (semantic or text)
        filters: Optional filters (date range, model, quality score)
        limit: Maximum results

    Returns:
        Matching conversations with context
    """
    try:
        search_filters = filters or {}

        async with ReflectionDatabase() as db:
            results = await db._search_conversations(
                query=query,
                filters=search_filters,
                limit=limit
            )

        return {
            "success": True,
            "results": results,
            "count": len(results),
            "query": query
        }

    except Exception as e:
        logger.error("Conversation search failed", error=str(e))
        return {"success": False, "error": str(e)}

@mcp.tool()
async def get_conversation_stats(
    session_id: str,
    time_range: str | None = None  # e.g., "7d", "30d", "90d"
) -> dict[str, object]:
    """
    Get usage statistics for a session.

    Provides:
    - Total conversations
    - Model usage distribution
    - Average conversation length
    - Quality score trends
    - Tool usage frequency

    Args:
        session_id: Session identifier
        time_range: Optional time range filter

    Returns:
        Conversation statistics
    """
    try:
        async with ReflectionDatabase() as db:
            stats = await db._get_conversation_stats(
                session_id=session_id,
                time_range=time_range
            )

        return {
            "success": True,
            "stats": stats
        }

    except Exception as e:
        logger.error("Failed to get conversation stats", error=str(e))
        return {"success": False, "error": str(e)}
```

#### Database Schema Enhancement

```sql
-- Add to existing conversations table
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS model TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS duration_ms INTEGER;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS tool_usage JSON;  -- {tool_name: count}
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS quality_score REAL;

-- New stats table
CREATE TABLE IF NOT EXISTS conversation_stats (
    stat_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    date TEXT NOT NULL,  -- YYYY-MM-DD
    model TEXT NOT NULL,
    conversation_count INTEGER NOT NULL,
    total_duration_ms INTEGER NOT NULL,
    avg_quality_score REAL,
    tool_usage_summary JSON,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

### 5. Auto-Generated Documentation ⭐⭐⭐
**Priority: MEDIUM** | **Effort: MEDIUM** (depends on Code Graph)

AI Maestro automatically extracts and indexes code documentation.

#### What AI Maestro Has

- **Auto-extract docstrings** from code
- **Search through documented** functions/classes
- **Living documentation** from codebase

#### Proposed Session Buddy Implementation

```python
# session_buddy/tools/documentation_tools.py

import ast
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)

@mcp.tool()
async def index_documentation(
    project_path: str,
    file_patterns: list[str] | None = None
) -> dict[str, object]:
    """
    Extract and index all code documentation (docstrings).

    Args:
        project_path: Path to project directory
        file_patterns: Optional glob patterns (default: ["**/*.py"])

    Returns:
        Indexing statistics
    """
    try:
        patterns = file_patterns or ["**/*.py"]
        project = Path(project_path)

        doc_stats = {
            "files_processed": 0,
            "functions_documented": 0,
            "classes_documented": 0,
            "modules_documented": 0
        }

        async with ReflectionDatabase() as db:
            for pattern in patterns:
                for file_path in project.glob(pattern):
                    stats = await _index_file_documentation(file_path, db)
                    doc_stats["files_processed"] += 1
                    doc_stats["functions_documented"] += stats["functions"]
                    doc_stats["classes_documented"] += stats["classes"]
                    doc_stats["modules_documented"] += stats["modules"]

        return {
            "success": True,
            "stats": doc_stats
        }

    except Exception as e:
        logger.error("Documentation indexing failed", error=str(e))
        return {"success": False, "error": str(e)}

async def _index_file_documentation(
    file_path: Path,
    db: ReflectionDatabase
) -> dict[str, int]:
    """Index documentation from a single file"""
    try:
        source = file_path.read_text()
        tree = ast.parse(source, filename=str(file_path))

        stats = {"functions": 0, "classes": 0, "modules": 0}

        # Module docstring
        if tree.body and isinstance(tree.body[0], ast.Expr):
            if isinstance(tree.body[0].value, ast.Constant):
                module_doc = tree.body[0].value.value
                if module_doc:
                    await db._store_documentation(
                        name=file_path.stem,
                        doc_type="module",
                        docstring=module_doc,
                        file_path=str(file_path),
                        line=1
                    )
                    stats["modules"] += 1

        # Functions and classes
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and ast.get_docstring(node):
                await db._store_documentation(
                    name=node.name,
                    doc_type="function",
                    docstring=ast.get_docstring(node),
                    file_path=str(file_path),
                    line=node.lineno
                )
                stats["functions"] += 1

            elif isinstance(node, ast.ClassDef) and ast.get_docstring(node):
                await db._store_documentation(
                    name=node.name,
                    doc_type="class",
                    docstring=ast.get_docstring(node),
                    file_path=str(file_path),
                    line=node.lineno
                )
                stats["classes"] += 1

        return stats

    except Exception as e:
        logger.warning("Failed to index file documentation", file=str(file_path), error=str(e))
        return {"functions": 0, "classes": 0, "modules": 0}

@mcp.tool()
async def search_documentation(
    query: str,
    doc_types: list[str] | None = None
) -> dict[str, object]:
    """
    Search through indexed code documentation.

    Args:
        query: Search query
        doc_types: Filter by type (module, function, class)

    Returns:
        Matching documentation entries
    """
    try:
        async with ReflectionDatabase() as db:
            results = await db._search_documentation(
                query=query,
                doc_types=doc_types or ["module", "function", "class"]
            )

        return {
            "success": True,
            "results": results,
            "count": len(results)
        }

    except Exception as e:
        logger.error("Documentation search failed", error=str(e))
        return {"success": False, "error": str(e)}
```

#### Database Schema

```sql
CREATE TABLE IF NOT EXISTS code_documentation (
    doc_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    doc_type TEXT NOT NULL,  -- 'module', 'function', 'class'
    docstring TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line INTEGER NOT NULL,
    embedding FLOAT[384],  -- For semantic search
    indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documentation_name
    ON code_documentation(name);

CREATE INDEX IF NOT EXISTS idx_documentation_type
    ON code_documentation(doc_type);
```

---

## ❌ Features That DON'T Fit Session Buddy

### Peer Mesh Network
**Why not:** Session Buddy is an MCP server (single instance), not a multi-agent orchestrator. The mesh network is specific to AI Maestro's architecture of managing tmux sessions across machines.

### tmux Session Management
**Why not:** Session Buddy doesn't manage terminal sessions - it manages Claude Code sessions via MCP protocol.

### Web Dashboard
**Why not:** Session Buddy is designed to work through Claude Code's UI, not provide its own dashboard.

### Agent Notes (localStorage)
**Why not:** Session Buddy already has persistent reflections with DuckDB storage - browser-based notes would be less powerful and redundant.

---

## 📊 Implementation Priority

```
Phase 1 (High Impact, Low-Medium Effort):
  ✅ Agent Communication System
     - Leverage existing multi_project_coordinator.py
     - Extend DuckDB schema with messages table
     - Implement send/list/forward MCP tools
     - Estimated effort: 2-3 days

  ✅ Conversation Memory Browser
     - Extend existing search_reflections
     - Add conversation stats tracking
     - Implement filters and aggregations
     - Estimated effort: 1-2 days

Phase 2 (High Impact, High Effort):
  ⭐ Code Graph Visualization
     - Add AST parsing for Python
     - Create graph schema in DuckDB
     - Build code graph analyzer
     - Implement related code search
     - Estimated effort: 5-7 days

  ⭐ Auto-Generated Documentation
     - Depends on Code Graph infrastructure
     - Extract docstrings during indexing
     - Implement semantic search
     - Estimated effort: 2-3 days

Phase 3 (Medium Impact, Low Effort):
  🔧 Portable Agent Configuration
     - Export/import session configs
     - Conflict detection and resolution
     - Zip file packaging
     - Estimated effort: 1-2 days

Phase 4 (Future Enhancement):
  📋 Performance Metrics Dashboard
     - Track development patterns
     - Visualize quality trends
     - Tool usage analytics
     - Estimated effort: 3-4 days
```

---

## 🎁 Bonus: Integration Opportunities

### AI Maestro + Session Buddy Synergy

These two systems can work together beautifully:

**Session Buddy as Memory Backend for AI Maestro:**

```python
# Proposed integration

@mcp.tool()
async def get_agent_context(
    agent_id: str,
    query: str,
    context_type: Literal["conversations", "code_graph", "quality"] = "conversations"
) -> dict[str, object]:
    """
    Provide enhanced context to AI Maestro agents.

    AI Maestro can call this to give agents memory and intelligence.

    Args:
        agent_id: AI Maestro agent identifier
        query: Context query
        context_type: Type of context to retrieve

    Returns:
        Relevant context for the agent
    """
    try:
        context = {}

        if context_type in ["conversations", "all"]:
            async with ReflectionDatabase() as db:
                context["conversations"] = await db.search_conversations(query)

        if context_type in ["code_graph", "all"]:
            # Get code graph context
            context["code_graph"] = await get_code_context(query)

        if context_type in ["quality", "all"]:
            # Get quality metrics
            context["quality"] = await get_quality_history(agent_id)

        return {
            "success": True,
            "agent_id": agent_id,
            "context": context
        }

    except Exception as e:
        logger.error("Failed to get agent context", error=str(e))
        return {"success": False, "error": str(e)}
```

**Benefits of Integration:**
- AI Maestro gains persistent memory and semantic search
- Session Buddy gains multi-agent orchestration
- Both systems become more powerful together
- Users get best of both worlds

**Example Workflow:**
```bash
# 1. Start AI Maestro orchestrator
cd ~/ai-maestro && yarn dev

# 2. Create agents with Session Buddy integration
# - backend-api agent with memory
# - frontend-dashboard agent with memory
# - qa-tests agent with memory

# 3. Backend agent finishes API endpoint
# - Sends message to frontend agent via AI Maestro
# - Session Buddy provides context about similar APIs built in past
# - Frontend agent integrates using knowledge from past conversations

# 4. QA agent finds bug
# - Notifies backend agent via AI Maestro
# - Session Buddy provides context about similar bugs and fixes
# - Backend agent resolves issue faster with historical knowledge
```

---

## 🚀 Recommended Next Steps

### Option 1: Agent Communication System
I can design and implement the complete messaging system with:
- Full database schema
- MCP tool implementations
- Integration with multi-project coordinator
- Test suite
- Documentation

### Option 2: Code Graph Proof-of-Concept
I can create a working prototype with:
- Python AST parser
- DuckDB graph storage
- Basic visualization tools
- Search functionality
- Performance benchmarks

### Option 3: Integration Layer
I can build the integration between Session Buddy and AI Maestro:
- MCP API for AI Maestro to call
- Context retrieval tools
- Shared memory architecture
- Example workflows

### Option 4: Detailed Design Docs
I can create comprehensive design documents for any feature:
- Architecture diagrams
- Database schemas
- API specifications
- Implementation roadmap

Let me know which direction you'd like to pursue!

---

## 📚 References

- **AI Maestro GitHub:** https://github.com/23blocks-OS/ai-maestro
- **AI Maestro Documentation:** https://ai-maestro.23blocks.com/
- **Session Buddy Repository:** https://github.com/lesleslie/session-buddy
- **CozoDB (Graph Database):** https://www.cozodb.org/
- **DuckDB Documentation:** https://duckdb.org/docs/

---

**Document Version:** 1.0
**Last Updated:** 2025-01-24
**Author:** Claude Code with analysis of AI Maestro v0.19.0
