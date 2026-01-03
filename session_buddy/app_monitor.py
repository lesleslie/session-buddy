#!/usr/bin/env python3
"""Application-Aware Context Monitoring for Session Management MCP Server.

Monitors IDE activity and browser documentation to enrich session context.
Excludes Slack/Discord as per Phase 4 requirements.
"""

import asyncio
import json
import operator
import sqlite3
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import psutil
    # FileSystemEventHandler and Observer imported at runtime below

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

    # Create stub for FileSystemEventHandler when watchdog is not available
    class FileSystemEventHandler:  # type: ignore[no-redef]
        """Stub base class when watchdog is not available."""

        def __init__(self) -> None:  # type: ignore[no-redef]
            super().__init__()  # type: ignore[misc]

    # Create stub for Observer when watchdog is not available
    class Observer:  # type: ignore[no-redef]
        def __init__(self) -> None:
            pass

        def schedule(
            self, event_handler: Any, path: str, recursive: bool = True
        ) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def join(self) -> None:
            pass


try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


@dataclass
class ActivityEvent:
    """Represents a monitored activity event."""

    timestamp: str
    event_type: str  # 'file_change', 'app_focus', 'browser_nav'
    application: str
    details: dict[str, Any]
    project_path: str | None = None
    relevance_score: float = 0.0


class ProjectActivityMonitor:
    """Monitors project activity including file changes and application focus."""

    def __init__(self, project_paths: list[str] | None = None) -> None:
        """Initialize activity monitor."""
        from session_buddy.settings import get_settings

        self._settings = get_settings()
        self.project_paths = project_paths or []
        self.db_path = str(Path.home() / ".claude" / "data" / "activity.db")
        self.observers: list[Any] = []
        self.activity_buffer: list[ActivityEvent] = []
        self.last_activity: dict[str, Any] = {}
        self.ide_extensions = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".rs",
            ".go",
            ".php",
            ".rb",
            ".swift",
            ".kt",
            ".scala",
            ".cs",
            ".html",
            ".css",
            ".scss",
            ".vue",
            ".svelte",
            ".json",
            ".yaml",
        }

    def _init_database(self) -> None:
        """Initialize database tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activity_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    application TEXT NOT NULL,
                    details TEXT NOT NULL,
                    project_path TEXT,
                    relevance_score REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def start_monitoring(self) -> bool:
        """Start file system monitoring."""
        if not WATCHDOG_AVAILABLE:
            return False

        if WATCHDOG_AVAILABLE:
            for path in self.project_paths:
                if Path(path).exists():
                    event_handler = IDEFileHandler(self)
                    observer = Observer()
                    observer.schedule(event_handler, path, recursive=True)
                    observer.start()
                    self.observers.append(observer)

        return len(self.observers) > 0

    def stop_monitoring(self) -> None:
        """Stop file system monitoring."""
        if WATCHDOG_AVAILABLE:
            for observer in self.observers:
                observer.stop()
                observer.join()
        self.observers.clear()

    def add_activity(self, event: ActivityEvent) -> None:
        """Add activity event to buffer."""
        self.activity_buffer.append(event)

        # Keep buffer size manageable
        if len(self.activity_buffer) > 1000:
            self.activity_buffer = self.activity_buffer[-500:]

    def get_recent_activity(self, minutes: int = 30) -> list[ActivityEvent]:
        """Get recent activity within specified minutes."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        cutoff_str = cutoff.isoformat()

        return [
            event for event in self.activity_buffer if event.timestamp >= cutoff_str
        ]

    def get_active_files(self, minutes: int = 60) -> list[dict[str, Any]]:
        """Get files actively being worked on."""
        recent_events = self.get_recent_activity(minutes)
        file_activity: dict[str, list[ActivityEvent]] = defaultdict(list)

        for event in recent_events:
            if event.event_type == "file_change" and "file_path" in event.details:
                file_path = event.details["file_path"]
                file_activity[file_path].append(event)

        # Score files by activity frequency and recency
        active_files = []
        for file_path, events in file_activity.items():
            score = len(events)
            latest_event = max(events, key=lambda e: e.timestamp)

            # Boost score for recent activity
            time_diff = datetime.now() - datetime.fromisoformat(latest_event.timestamp)
            if time_diff.total_seconds() < 300:  # 5 minutes
                score *= 2

            active_files.append(
                {
                    "file_path": file_path,
                    "activity_score": score,
                    "event_count": len(events),
                    "last_activity": latest_event.timestamp,
                    "project_path": latest_event.project_path,
                },
            )

        return sorted(
            active_files, key=operator.itemgetter("activity_score"), reverse=True
        )


class IDEFileHandler(FileSystemEventHandler):  # type: ignore[misc]
    """Handles file system events for IDE monitoring."""

    def __init__(self, monitor: ProjectActivityMonitor) -> None:
        self.monitor = monitor
        # Merge settings-driven ignore dirs
        self.ignore_patterns = set(self.monitor._settings.filesystem_ignore_dirs)
        self.ignore_patterns.add(".vscode/settings.json")

        # Critical file patterns for smart thresholding
        self.critical_patterns = {
            "auth": ["auth", "login", "session", "jwt", "oauth"],
            "database": ["db", "database", "migration", "schema"],
            "config": ["config", "settings", "env"],
            "api": ["api", "endpoint", "route", "controller"],
            "security": ["security", "encrypt", "hash", "crypto"],
        }
        self._recent_ttl_seconds = self.monitor._settings.filesystem_dedupe_ttl_seconds

    def should_ignore(self, file_path: str) -> bool:
        """Check if file should be ignored."""
        path = Path(file_path)

        # Check ignore patterns
        for part in path.parts:
            if part in self.ignore_patterns:
                return True

        # Check if it's a relevant file extension
        if path.suffix not in self.monitor.ide_extensions:
            return True

        # Ignore large or temporary files
        max_size = self.monitor._settings.filesystem_max_file_size_bytes
        with suppress(Exception):
            if path.exists() and path.is_file() and path.stat().st_size > max_size:
                return True

        return bool(path.name.startswith(".") or path.name.endswith("~"))

    def on_modified(self, event: Any) -> None:
        """Handle file modification events."""
        if event.is_directory or self.should_ignore(event.src_path):
            return

        src_path = Path(event.src_path)
        project_path = self._determine_project_path(src_path)

        activity_event = self._create_activity_event(src_path, project_path)
        self.monitor.add_activity(activity_event)

        self._try_entity_extraction(activity_event, src_path, project_path)

    def _determine_project_path(self, src_path: Path) -> str | None:
        """Determine which project this file belongs to."""
        for proj_path in self.monitor.project_paths:
            if src_path.is_relative_to(proj_path):
                return proj_path
        return None

    def _create_activity_event(
        self,
        src_path: Path,
        project_path: str | None,
    ) -> ActivityEvent:
        """Create an activity event for file modification."""
        return ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="file_change",
            application="ide",
            details={
                "file_path": str(src_path),
                "file_name": src_path.name,
                "file_extension": src_path.suffix,
                "change_type": "modified",
            },
            project_path=project_path,
            relevance_score=self._estimate_relevance(src_path),
        )

    def _try_entity_extraction(
        self,
        activity_event: ActivityEvent,
        src_path: Path,
        project_path: str | None,
    ) -> None:
        """Try to extract entities if feature flags are enabled."""
        from session_buddy.config.feature_flags import get_feature_flags

        flags = get_feature_flags()
        if not (
            flags.enable_filesystem_extraction and flags.enable_llm_entity_extraction
        ):
            return

        if not self._passes_threshold(activity_event):
            return

        if self._recently_processed_persisted(str(src_path)):
            return

        self._fire_and_forget_extraction(activity_event, src_path, project_path)

    def _fire_and_forget_extraction(
        self,
        activity_event: ActivityEvent,
        src_path: Path,
        project_path: str | None,
    ) -> None:
        """Fire-and-forget entity extraction task."""
        with suppress(Exception):
            import asyncio as _asyncio

            from session_buddy.memory.file_context import build_file_context
            from session_buddy.tools.entity_extraction_tools import (
                extract_and_store_memory as _extract,
            )

            ctx = build_file_context(str(src_path))
            snippet = ctx.get("snippet", "")

            _asyncio.create_task(
                _extract(
                    user_input=f"Updated file: {src_path.name}\nContext: {ctx['metadata']}",
                    ai_output=snippet,
                    project=project_path,
                    activity_score=activity_event.relevance_score,
                )
            )

    def _recently_processed_persisted(self, file_path: str) -> bool:
        """Check and update persistent recent-extractions cache.

        Returns True if the given file was processed within the TTL window.
        """
        try:
            # Use the same SQLite DB as activity log
            import sqlite3 as _sql
            from time import time as _now

            self._ensure_recent_table()
            with _sql.connect(self.monitor.db_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT last_extracted FROM recent_extractions WHERE file_path=?",
                    (file_path,),
                )
                row = cur.fetchone()
                now = int(_now())
                if row:
                    last = int(row[0])
                    if now - last < self._recent_ttl_seconds:
                        return True
                    # Update timestamp
                    cur.execute(
                        "UPDATE recent_extractions SET last_extracted=? WHERE file_path=?",
                        (now, file_path),
                    )
                else:
                    cur.execute(
                        "INSERT INTO recent_extractions (file_path, last_extracted) VALUES (?, ?)",
                        (file_path, now),
                    )
                conn.commit()
        except Exception:
            # On any error, fall back to allowing processing to avoid missing events
            return False
        return False

    def _ensure_recent_table(self) -> None:
        """Ensure the persistent recent_extractions table exists."""
        with suppress(Exception):
            import sqlite3 as _sql

            with _sql.connect(self.monitor.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recent_extractions (
                        file_path TEXT PRIMARY KEY,
                        last_extracted INTEGER
                    )
                    """
                )

    def _estimate_relevance(self, path: Path) -> float:
        name = path.name.lower()
        for keywords in self.critical_patterns.values():
            if any(k in name for k in keywords):
                return 0.95
        return 0.8

    def _passes_threshold(self, event: ActivityEvent) -> bool:
        # Base threshold
        if event.relevance_score < 0.7:
            return False
        # Stricter threshold for non-critical files
        name = event.details.get("file_name", "").lower()
        critical = any(
            any(k in name for k in kw) for kw in self.critical_patterns.values()
        )
        return not (not critical and event.relevance_score < 0.9)


class BrowserDocumentationMonitor:
    """Monitors browser activity for documentation sites."""

    def __init__(self) -> None:
        self.doc_domains = {
            "docs.python.org",
            "developer.mozilla.org",
            "docs.rs",
            "docs.oracle.com",
            "docs.microsoft.com",
            "docs.aws.amazon.com",
            "cloud.google.com",
            "docs.github.com",
            "docs.gitlab.com",
            "stackoverflow.com",
            "github.com",
            "fastapi.tiangolo.com",
            "pydantic-docs.helpmanual.io",
            "django-documentation",
            "flask.palletsprojects.com",
            "nodejs.org",
            "reactjs.org",
            "vuejs.org",
            "angular.io",
            "svelte.dev",
        }
        self.activity_buffer: list[ActivityEvent] = []
        self.browser_processes: set[str] = set()

    def get_browser_processes(self) -> list[dict[str, Any]]:
        """Get currently running browser processes."""
        if not PSUTIL_AVAILABLE:
            return []

        browsers = []
        browser_names = {"chrome", "firefox", "safari", "edge", "brave"}

        try:
            for proc in psutil.process_iter(["pid", "name", "create_time"]):
                proc_name = proc.info["name"].lower()
                if any(browser in proc_name for browser in browser_names):
                    browsers.append(
                        {
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "create_time": proc.info["create_time"],
                        },
                    )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        return browsers

    def extract_documentation_context(self, url: str) -> dict[str, Any]:
        """Extract context from documentation URLs."""
        context = {"domain": "", "technology": "", "topic": "", "relevance": 0.0}

        from contextlib import suppress

        with suppress(ValueError, AttributeError):
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc
            path = parsed.path

            context["domain"] = domain
            technology, relevance = self._determine_technology(domain, path)
            context["technology"] = technology
            context["relevance"] = relevance
            context["topic"] = self._extract_topic(path)

        return context

    def _determine_technology(self, domain: str, path: str) -> tuple[str, float]:
        """Return technology label and relevance score for a domain/path."""
        normalized_path = path.lower()
        normalized_domain = domain.lower()

        tech_rules = [
            (
                "python" in normalized_domain or "python" in normalized_path,
                "python",
                0.9,
            ),
            (
                "javascript" in normalized_path
                or "js" in normalized_path
                or normalized_domain in {"developer.mozilla.org", "nodejs.org"},
                "javascript",
                0.8,
            ),
            (
                "rust" in normalized_domain or "docs.rs" in normalized_domain,
                "rust",
                0.8,
            ),
            (
                any(
                    framework in normalized_domain
                    for framework in ("django", "flask", "fastapi")
                ),
                "python-web",
                0.9,
            ),
            (
                any(
                    framework in normalized_domain
                    for framework in ("react", "vue", "angular", "svelte")
                ),
                "frontend",
                0.8,
            ),
        ]

        for condition, label, relevance in tech_rules:
            if condition:
                return label, relevance

        return "", 0.0

    def _extract_topic(self, path: str) -> str:
        """Derive topic from a URL path."""
        path_parts = [p for p in path.split("/") if p]
        if not path_parts:
            return ""

        tail = path_parts[-1]
        if tail == "index.html" and len(path_parts) > 1:
            return path_parts[-2]
        return tail

    def add_browser_activity(self, url: str, title: str = "") -> None:
        """Add browser navigation activity."""
        context = self.extract_documentation_context(url)

        activity_event = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="browser_nav",
            application="browser",
            details={
                "url": url,
                "title": title,
                "domain": context["domain"],
                "technology": context["technology"],
                "topic": context["topic"],
            },
            relevance_score=context["relevance"],
        )

        self.activity_buffer.append(activity_event)

        # Keep buffer manageable
        if len(self.activity_buffer) > 500:
            self.activity_buffer = self.activity_buffer[-250:]


class ApplicationFocusMonitor:
    """Monitors application focus changes."""

    def __init__(self) -> None:
        self.focus_history: list[ActivityEvent] = []
        self.current_app: str | None = None
        self.app_categories = {
            "ide": {
                "code",
                "pycharm",
                "vscode",
                "sublime",
                "atom",
                "vim",
                "emacs",
                "intellij",
            },
            "browser": {"chrome", "firefox", "safari", "edge", "brave"},
            "terminal": {
                "terminal",
                "term",
                "console",
                "cmd",
                "powershell",
                "zsh",
                "bash",
            },
            "documentation": {"devdocs", "dash", "zeal"},
        }

    def get_focused_application(self) -> dict[str, Any] | None:
        """Get currently focused application."""
        if not PSUTIL_AVAILABLE:
            return None

        try:
            # This is a simplified version - would need platform-specific implementation
            # for full window focus detection
            for proc in psutil.process_iter(["pid", "name"]):
                proc_name = proc.info["name"].lower()
                category = self._categorize_app(proc_name)
                if category:
                    return {
                        "name": proc.info["name"],
                        "category": category,
                        "pid": proc.info["pid"],
                    }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        return None

    def _categorize_app(self, app_name: str) -> str | None:
        """Categorize application by name."""
        for category, keywords in self.app_categories.items():
            if any(keyword in app_name for keyword in keywords):
                return category
        return None

    def add_focus_event(self, app_info: dict[str, Any]) -> None:
        """Add application focus event."""
        activity_event = ActivityEvent(
            timestamp=datetime.now().isoformat(),
            event_type="app_focus",
            application=app_info["name"],
            details={"category": app_info["category"], "pid": app_info["pid"]},
            relevance_score=0.6 if app_info["category"] in {"ide", "terminal"} else 0.3,
        )

        self.focus_history.append(activity_event)

        # Keep history manageable
        if len(self.focus_history) > 200:
            self.focus_history = self.focus_history[-100:]


class ActivityDatabase:
    """SQLite database for storing activity events."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activity_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    application TEXT NOT NULL,
                    details TEXT NOT NULL,
                    project_path TEXT,
                    relevance_score REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON activity_events(timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_type ON activity_events(event_type)
            """)

    def store_event(self, event: ActivityEvent) -> None:
        """Store activity event in database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO activity_events
                (timestamp, event_type, application, details, project_path, relevance_score)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    event.timestamp,
                    event.event_type,
                    event.application,
                    json.dumps(event.details),
                    event.project_path,
                    event.relevance_score,
                ),
            )

    def get_events(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
        event_types: list[str] | None = None,
        limit: int = 100,
    ) -> list[ActivityEvent]:
        """Retrieve activity events from database."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT * FROM activity_events WHERE 1=1"
            params: list[Any] = []

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            if event_types:
                placeholders = ",".join("?" * len(event_types))
                query += f" AND event_type IN ({placeholders})"
                params.extend(event_types)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            return [
                ActivityEvent(
                    timestamp=row[1],
                    event_type=row[2],
                    application=row[3],
                    details=json.loads(row[4]),
                    project_path=row[5],
                    relevance_score=row[6] or 0.0,
                )
                for row in rows
            ]

    def cleanup_old_events(self, days_to_keep: int = 30) -> None:
        """Remove old activity events."""
        cutoff = datetime.now() - timedelta(days=days_to_keep)
        cutoff_str = cutoff.isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM activity_events WHERE timestamp < ?",
                (cutoff_str,),
            )


class ApplicationMonitor:
    """Main application monitoring coordinator."""

    def __init__(self, data_dir: str, project_paths: list[str] | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.project_paths = project_paths or []

        self._setup_directory()
        self._initialize_components()
        self._setup_monitoring_state()

    def _setup_directory(self) -> None:
        """Set up the data directory."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _initialize_components(self) -> None:
        """Initialize monitoring components."""
        self.db = ActivityDatabase(str(self.data_dir / "activity.db"))
        self.ide_monitor = ProjectActivityMonitor(self.project_paths)
        self.browser_monitor = BrowserDocumentationMonitor()
        self.focus_monitor = ApplicationFocusMonitor()

    def _setup_monitoring_state(self) -> None:
        """Set up monitoring state variables."""
        self.monitoring_active = False
        self._monitoring_task: asyncio.Task[Any] | None = None

    async def start_monitoring(self) -> dict[str, Any] | None:
        """Start all monitoring components."""
        if self.monitoring_active:
            return None

        self.monitoring_active = True

        # Start IDE monitoring
        ide_started = self.ide_monitor.start_monitoring()

        # Start background monitoring task
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())

        return {
            "ide_monitoring": ide_started,
            "watchdog_available": WATCHDOG_AVAILABLE,
            "psutil_available": PSUTIL_AVAILABLE,
            "project_paths": self.project_paths,
        }

    async def stop_monitoring(self) -> None:
        """Stop all monitoring."""
        self.monitoring_active = False

        if self._monitoring_task:
            self._monitoring_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitoring_task

        self.ide_monitor.stop_monitoring()

    async def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while self.monitoring_active:
            try:
                await self._process_monitoring_cycle()
                await asyncio.sleep(30)  # Check every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self._handle_monitoring_error(e)

    async def _process_monitoring_cycle(self) -> None:
        """Process a single monitoring cycle."""
        await self._check_application_focus()
        await self._persist_buffered_events()

    async def _check_application_focus(self) -> None:
        """Check and update application focus if changed."""
        focused_app = self.focus_monitor.get_focused_application()
        if self._is_focus_changed(focused_app) and focused_app is not None:
            self.focus_monitor.add_focus_event(focused_app)
            self.focus_monitor.current_app = focused_app.get("name")

    def _is_focus_changed(self, focused_app: dict[str, Any] | None) -> bool:
        """Check if application focus has changed."""
        return (
            focused_app is not None
            and focused_app.get("name") != self.focus_monitor.current_app
        )

    async def _persist_buffered_events(self) -> None:
        """Persist all buffered events to database."""
        # Use generator expressions for memory efficiency
        await self._persist_event_batch(
            event for event in self.ide_monitor.activity_buffer[-10:]
        )
        await self._persist_event_batch(
            event for event in self.browser_monitor.activity_buffer[-10:]
        )
        await self._persist_event_batch(
            event for event in self.focus_monitor.focus_history[-5:]
        )

    async def _persist_event_batch(
        self,
        events: Any,  # Generator of ActivityEvent
    ) -> None:
        """Persist a batch of events to the database."""
        for event in events:
            self.db.store_event(event)

    async def _handle_monitoring_error(self, error: Exception) -> None:
        """Handle monitoring errors with appropriate logging and delay."""
        # Log error but continue monitoring
        await asyncio.sleep(60)

    def get_activity_summary(self, hours: int = 2) -> dict[str, Any]:
        """Get activity summary for specified hours."""
        start_time = (datetime.now() - timedelta(hours=hours)).isoformat()
        events = self.db.get_events(start_time=start_time, limit=500)

        summary = self._create_activity_summary_template(hours, events)
        self._aggregate_event_data(events, summary)
        self._add_additional_context(hours, summary)
        return self._finalize_summary(summary)

    def _create_activity_summary_template(
        self,
        hours: int,
        events: list[Any],
    ) -> dict[str, Any]:
        """Create the base summary template."""
        return {
            "total_events": len(events),
            "time_range_hours": hours,
            "event_types": defaultdict(int),
            "applications": defaultdict(int),
            "active_files": [],
            "documentation_sites": [],
            "average_relevance": 0.0,
        }

    def _aggregate_event_data(self, events: list[Any], summary: dict[str, Any]) -> None:
        """Aggregate event data into the summary."""
        total_relevance: float = 0.0
        doc_sites = set()

        for event in events:
            summary["event_types"][event.event_type] += 1
            summary["applications"][event.application] += 1
            total_relevance += event.relevance_score

            if event.event_type == "browser_nav" and event.details.get("domain"):
                doc_sites.add(event.details["domain"])

        if events:
            summary["average_relevance"] = total_relevance / len(events)

        summary["documentation_sites"] = list(doc_sites)

    def _add_additional_context(self, hours: int, summary: dict[str, Any]) -> None:
        """Add additional context information to the summary."""
        summary["active_files"] = self.ide_monitor.get_active_files(hours * 60)

    def _finalize_summary(self, summary: dict[str, Any]) -> dict[str, Any]:
        """Finalize summary by converting collections for JSON serialization."""
        summary["event_types"] = dict(summary["event_types"])
        summary["applications"] = dict(summary["applications"])
        return summary

    def get_context_insights(self, hours: int = 1) -> dict[str, Any]:
        """Get contextual insights from recent activity."""
        start_time = (datetime.now() - timedelta(hours=hours)).isoformat()
        events = self.db.get_events(start_time=start_time, limit=200)

        insights = self._create_insights_template()
        if not events:
            return insights

        app_time = self._analyze_events(events, insights)
        self._determine_primary_focus(app_time, insights)
        self._calculate_productivity_score(events, insights)
        return self._finalize_insights(insights)

    def _create_insights_template(self) -> dict[str, Any]:
        """Create the insights template dictionary."""
        return {
            "primary_focus": None,
            "technologies_used": set(),
            "active_projects": set(),
            "documentation_topics": [],
            "productivity_score": 0.0,
            "context_switches": 0,
        }

    def _analyze_events(
        self,
        events: list[Any],
        insights: dict[str, Any],
    ) -> dict[str, int]:
        """Analyze events and extract insights data."""
        app_time: dict[str, int] = defaultdict(int)
        last_app = None

        for event in events:
            app_time[event.application] += 1

            if last_app and last_app != event.application:
                insights["context_switches"] += 1
            last_app = event.application

            self._extract_event_data(event, insights)

        return app_time

    def _extract_event_data(self, event: Any, insights: dict[str, Any]) -> None:
        """Extract relevant data from a single event."""
        self._extract_technologies(event, insights)
        self._extract_projects(event, insights)
        self._extract_documentation_topics(event, insights)

    def _extract_technologies(self, event: Any, insights: dict[str, Any]) -> None:
        """Extract technology information from file change events."""
        if event.event_type == "file_change":
            ext = event.details.get("file_extension", "")
            if ext == ".py":
                insights["technologies_used"].add("python")
            elif ext in {".js", ".ts"}:
                insights["technologies_used"].add("javascript")
            elif ext == ".rs":
                insights["technologies_used"].add("rust")

    def _extract_projects(self, event: Any, insights: dict[str, Any]) -> None:
        """Extract project information from events."""
        if event.project_path:
            insights["active_projects"].add(event.project_path)

    def _extract_documentation_topics(
        self,
        event: Any,
        insights: dict[str, Any],
    ) -> None:
        """Extract documentation topics from browser navigation events."""
        if event.event_type == "browser_nav":
            topic = event.details.get("topic")
            technology = event.details.get("technology")
            if topic and technology:
                insights["documentation_topics"].append(f"{technology}: {topic}")

    def _determine_primary_focus(
        self,
        app_time: dict[str, int],
        insights: dict[str, Any],
    ) -> None:
        """Determine the primary application focus."""
        if app_time:
            insights["primary_focus"] = max(
                app_time.items(), key=operator.itemgetter(1)
            )[0]

    def _calculate_productivity_score(
        self,
        events: list[Any],
        insights: dict[str, Any],
    ) -> None:
        """Calculate productivity score based on relevant activity."""
        relevant_events = [e for e in events if e.relevance_score > 0.5]
        if events:
            insights["productivity_score"] = len(relevant_events) / len(events)

    def _finalize_insights(self, insights: dict[str, Any]) -> dict[str, Any]:
        """Convert sets to lists for JSON serialization."""
        insights["technologies_used"] = list(insights["technologies_used"])
        insights["active_projects"] = list(insights["active_projects"])
        return insights
