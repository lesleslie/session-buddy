#!/usr/bin/env python3
"""Advanced Search Engine for Session Management.

Provides enhanced search capabilities with faceted filtering, full-text search,
and intelligent result ranking.
"""

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any

from .reflection_tools import ReflectionDatabase
from .search_enhanced import EnhancedSearchEngine
from .session_types import SQLCondition
from .utils.search import (
    SearchFacet,
    SearchFilter,
    SearchResult,
    ensure_timezone,
    extract_technical_terms,
    parse_timeframe,
    parse_timeframe_single,
    truncate_content,
)

__all__ = ["AdvancedSearchEngine", "SearchFilter"]


class AdvancedSearchEngine:
    """Advanced search engine with faceted filtering and full-text search."""

    def __init__(self, reflection_db: ReflectionDatabase) -> None:
        self.reflection_db = reflection_db
        self.enhanced_search = EnhancedSearchEngine(reflection_db)
        self.index_cache: dict[str, datetime] = {}

        # Search configuration
        self.facet_configs = {
            "project": {"type": "terms", "size": 20},
            "content_type": {"type": "terms", "size": 10},
            "date_range": {
                "type": "date",
                "ranges": ["1d", "7d", "30d", "90d", "365d"],
            },
            "author": {"type": "terms", "size": 15},
            "tags": {"type": "terms", "size": 25},
            "file_type": {"type": "terms", "size": 10},
            "language": {"type": "terms", "size": 10},
            "error_type": {"type": "terms", "size": 15},
        }

    async def search(
        self,
        query: str,
        filters: list[SearchFilter] | None = None,
        facets: list[str] | None = None,
        sort_by: str = "relevance",  # 'relevance', 'date', 'project'
        limit: int = 20,
        offset: int = 0,
        include_highlights: bool = True,
        content_type: str | None = None,
        timeframe: str | None = None,
    ) -> dict[str, Any]:
        """Perform advanced search with faceted filtering."""
        # Ensure search index is up to date
        await self._ensure_search_index()

        # Build and execute search
        search_query = self._build_search_query(query, filters)
        results = await self._execute_search(
            search_query,
            sort_by,
            limit,
            offset,
            filters,
            content_type,
            timeframe,
        )

        # Process results with optional features
        results = await self._process_search_results(results, query, include_highlights)
        facet_results = await self._process_facets(query, filters, facets)

        return self._format_search_response(results, facet_results, query, filters)

    async def _process_search_results(
        self,
        results: list[Any],
        query: str,
        include_highlights: bool,
    ) -> list[Any]:
        """Process search results with optional highlighting."""
        if include_highlights:
            return await self._add_highlights(results, query)
        return results

    async def _process_facets(
        self,
        query: str,
        filters: list[SearchFilter] | None,
        facets: list[str] | None,
    ) -> dict[str, Any]:
        """Process facets if requested."""
        if facets:
            return await self._calculate_facets(query, filters, facets)
        return {}

    def _format_search_response(
        self,
        results: list[Any],
        facet_results: dict[str, Any],
        query: str,
        filters: list[SearchFilter] | None,
    ) -> dict[str, Any]:
        """Format the final search response."""
        return {
            "results": results,
            "facets": facet_results,
            "total": len(results),
            "query": query,
            "filters": [f.__dict__ for f in filters] if filters else [],
            "took": time.time() - time.time(),  # Will be updated with actual timing
        }

    async def suggest_completions(
        self,
        query: str,
        field: str = "indexed_content",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get search completion suggestions."""
        # Use parameterized queries with predefined SQL patterns to prevent injection
        field_queries = {
            "content": """
                SELECT DISTINCT indexed_content, COUNT(*) as frequency
                FROM search_index
                WHERE indexed_content LIKE ?
                GROUP BY indexed_content
                ORDER BY frequency DESC, indexed_content
                LIMIT ?
            """,
            "project": """
                SELECT DISTINCT JSON_EXTRACT_STRING(search_metadata, '$.project'), COUNT(*) as frequency
                FROM search_index
                WHERE JSON_EXTRACT_STRING(search_metadata, '$.project') LIKE ?
                GROUP BY JSON_EXTRACT_STRING(search_metadata, '$.project')
                ORDER BY frequency DESC, JSON_EXTRACT_STRING(search_metadata, '$.project')
                LIMIT ?
            """,
            "tags": """
                SELECT DISTINCT JSON_EXTRACT_STRING(search_metadata, '$.tags'), COUNT(*) as frequency
                FROM search_index
                WHERE JSON_EXTRACT_STRING(search_metadata, '$.tags') LIKE ?
                GROUP BY JSON_EXTRACT_STRING(search_metadata, '$.tags')
                ORDER BY frequency DESC, JSON_EXTRACT_STRING(search_metadata, '$.tags')
                LIMIT ?
            """,
        }

        # Use predefined query or default to content search
        sql = field_queries.get(field, field_queries["content"])

        if not self.reflection_db.conn:
            return []

        try:
            results = self.reflection_db.conn.execute(
                sql,
                [f"%{query}%", limit],
            ).fetchall()

            return [{"text": row[0], "frequency": row[1]} for row in results]
        except Exception:
            # Table doesn't exist yet, will be created during index rebuild
            return []

    async def get_similar_content(
        self,
        content_id: str,
        content_type: str,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Find similar content using embeddings or text similarity."""
        # Get the source content
        sql = """
            SELECT indexed_content, search_metadata
            FROM search_index
            WHERE content_id = ? AND content_type = ?
        """

        if not self.reflection_db.conn:
            return []

        try:
            result = self.reflection_db.conn.execute(
                sql,
                [content_id, content_type],
            ).fetchone()

            if not result:
                return []
        except Exception:
            # Table doesn't exist yet, will be created during index rebuild
            return []

        source_content = result[0]

        # Use enhanced search for similarity
        similar_results = await self.reflection_db.search_conversations(
            query=source_content[:500],  # Use first 500 chars as query
            limit=limit + 1,  # +1 to exclude the source itself
        )

        # Convert to SearchResult format and exclude source
        search_results = [
            SearchResult(
                content_id=conv.get("conversation_id", ""),
                content_type="conversation",
                title=f"Conversation from {conv.get('project', 'Unknown')}",
                content=conv.get("content", ""),
                score=conv.get("score", 0.0),
                project=conv.get("project"),
                timestamp=conv.get("timestamp"),
                metadata=conv.get("metadata", {}),
            )
            for conv in similar_results
            if conv.get("conversation_id") != content_id
        ]

        return search_results[:limit]

    async def search_by_timeframe(
        self,
        timeframe: str,  # '1h', '1d', '1w', '1m', '1y' or ISO date range
        query: str | None = None,
        project: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search within a specific timeframe."""
        # Parse timeframe
        time_range = parse_timeframe(timeframe)
        start_time, end_time = time_range.start, time_range.end

        # Build time filter
        time_filter = SearchFilter(
            field="timestamp",
            operator="range",
            value=(start_time, end_time),
        )

        filters = [time_filter]
        if project:
            filters.append(SearchFilter(field="project", operator="eq", value=project))

        # Perform search
        search_results = await self.search(
            query=query or "*",
            filters=filters,
            limit=limit,
            sort_by="date",
        )

        # Convert SearchResult objects to dictionaries for compatibility
        result_dicts = []
        for result in search_results["results"]:
            result_dict = {
                "content_id": result.content_id,
                "content_type": result.content_type,
                "title": result.title,
                "content": result.content,
                "score": result.score,
                "project": result.project,
                "timestamp": result.timestamp,
                "metadata": result.metadata,
                "highlights": result.highlights,
                "facets": result.facets,
            }
            result_dicts.append(result_dict)

        return result_dicts

    async def aggregate_metrics(
        self,
        metric_type: str,  # 'activity', 'projects', 'content_types', 'errors'
        timeframe: str = "30d",
        filters: list[SearchFilter] | None = None,
    ) -> dict[str, Any]:
        """Calculate aggregate metrics from search data."""
        time_range = parse_timeframe(timeframe)
        start_time, end_time = time_range.start, time_range.end

        # Use predefined parameterized queries to prevent SQL injection
        metric_queries = {
            "activity": """
                SELECT DATE_TRUNC('day', last_indexed) as day,
                       COUNT(*) as count,
                       COUNT(DISTINCT content_id) as unique_content
                FROM search_index
                WHERE last_indexed BETWEEN ? AND ?
                GROUP BY day
                ORDER BY day
            """,
            "projects": """
                SELECT JSON_EXTRACT_STRING(search_metadata, '$.project') as project,
                       COUNT(*) as count
                FROM search_index
                WHERE last_indexed BETWEEN ? AND ?
                  AND JSON_EXTRACT_STRING(search_metadata, '$.project') IS NOT NULL
                GROUP BY project
                ORDER BY count DESC
            """,
            "content_types": """
                SELECT content_type, COUNT(*) as count
                FROM search_index
                WHERE last_indexed BETWEEN ? AND ?
                GROUP BY content_type
                ORDER BY count DESC
            """,
            "errors": """
                SELECT JSON_EXTRACT_STRING(search_metadata, '$.error_type') as error_type,
                       COUNT(*) as count
                FROM search_index
                WHERE last_indexed BETWEEN ? AND ?
                  AND JSON_EXTRACT_STRING(search_metadata, '$.error_type') IS NOT NULL
                GROUP BY error_type
                ORDER BY count DESC
            """,
        }

        if metric_type not in metric_queries:
            return {"error": f"Unknown metric type: {metric_type}"}

        sql = metric_queries[metric_type]

        if not self.reflection_db.conn:
            return {
                "error": f"Database connection not available for metric type: {metric_type}",
            }

        try:
            # Use simplified parameters for the base time range
            base_params = [start_time, end_time]
            results = self.reflection_db.conn.execute(sql, base_params).fetchall()

            return {
                "metric_type": metric_type,
                "timeframe": timeframe,
                "data": [{"key": row[0], "value": row[1]} for row in results]
                if results
                else [],
            }
        except Exception:
            # Table doesn't exist yet, will be created during index rebuild
            return {
                "metric_type": metric_type,
                "timeframe": timeframe,
                "data": [],
            }

    async def _ensure_search_index(self) -> None:
        """Ensure search index is up to date."""
        # Check when index was last updated
        last_update = await self._get_last_index_update()

        # Update if older than 1 hour or if never updated
        if not last_update or (datetime.now(UTC) - last_update).total_seconds() > 3600:
            await self._rebuild_search_index()

    async def _get_last_index_update(self) -> datetime | None:
        """Get timestamp of last index update."""
        sql = "SELECT MAX(last_indexed) FROM search_index"

        if not self.reflection_db.conn:
            return None

        try:
            result = self.reflection_db.conn.execute(sql).fetchone()

            if result and result[0]:
                dt = result[0]
                # Ensure datetime is timezone-aware
                if isinstance(dt, datetime) and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt if isinstance(dt, datetime) else None
            return None
        except Exception:
            # Table doesn't exist yet, will be created during index rebuild
            return None

    async def _rebuild_search_index(self) -> None:
        """Rebuild the search index from conversations and reflections."""
        # Ensure database tables exist before indexing
        if self.reflection_db.conn:
            await self.reflection_db._ensure_tables()

        # Index conversations
        await self._index_conversations()

        # Index reflections
        await self._index_reflections()

        # Update facets
        await self._update_search_facets()

    async def _index_conversations(self) -> None:
        """Index all conversations for search."""
        if not self.reflection_db.conn:
            return

        conversations = self._fetch_conversations_for_indexing()
        for row in conversations:
            await self._process_conversation_for_index(row)

        self._commit_conversation_index()

    def _fetch_conversations_for_indexing(self) -> list[tuple[Any, ...]]:
        """Fetch conversations from database for indexing."""
        if not self.reflection_db.conn:
            return []

        sql = "SELECT id, content, project, timestamp, metadata FROM conversations"
        return self.reflection_db.conn.execute(sql).fetchall()

    async def _process_conversation_for_index(self, row: tuple[Any, ...]) -> None:
        """Process a single conversation row for search indexing."""
        conv_id, content, project, timestamp, metadata_json = row

        self._parse_conversation_metadata(metadata_json)
        indexed_content = self._build_indexed_content(content, project)
        search_metadata = self._build_conversation_search_metadata(
            project,
            timestamp,
            content,
            indexed_content,
        )

        self._insert_conversation_into_search_index(
            conv_id,
            indexed_content,
            search_metadata,
        )

    def _parse_conversation_metadata(self, metadata_json: str | None) -> dict[str, Any]:
        """Parse conversation metadata JSON safely."""
        return json.loads(metadata_json) if metadata_json else {}

    def _build_indexed_content(self, content: str, project: str | None) -> str:
        """Build indexed content with project and technical terms."""
        indexed_content = content

        if project:
            indexed_content += f" project:{project}"

        tech_terms = extract_technical_terms(content)
        if tech_terms:
            indexed_content += " " + " ".join(tech_terms)

        return indexed_content

    def _build_conversation_search_metadata(
        self,
        project: str | None,
        timestamp: datetime | None,
        content: str,
        indexed_content: str,
    ) -> dict[str, Any]:
        """Build search metadata for conversation."""
        tech_terms = extract_technical_terms(content)
        return {
            "project": project,
            "timestamp": timestamp.isoformat() if timestamp else None,
            "content_length": len(content),
            "technical_terms": tech_terms,
        }

    def _insert_conversation_into_search_index(
        self,
        conv_id: str,
        indexed_content: str,
        search_metadata: dict[str, Any],
    ) -> None:
        """Insert conversation into search index."""
        if not self.reflection_db.conn:
            return

        self.reflection_db.conn.execute(
            """
            INSERT INTO search_index
            (id, content_type, content_id, indexed_content, search_metadata, last_indexed)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
            content_type = EXCLUDED.content_type,
            content_id = EXCLUDED.content_id,
            indexed_content = EXCLUDED.indexed_content,
            search_metadata = EXCLUDED.search_metadata,
            last_indexed = EXCLUDED.last_indexed
            """,
            [
                f"conv_{conv_id}",
                "conversation",
                conv_id,
                indexed_content,
                json.dumps(search_metadata),
                datetime.now(UTC),
            ],
        )

    def _commit_conversation_index(self) -> None:
        """Commit the conversation indexing transaction."""
        if self.reflection_db.conn:
            self.reflection_db.conn.commit()

    async def _index_reflections(self) -> None:
        """Index all reflections for search."""
        if not self.reflection_db.conn:
            return

        sql = "SELECT id, content, tags, timestamp, metadata FROM reflections"
        results = self.reflection_db.conn.execute(sql).fetchall()

        for row in results:
            refl_id, content, tags, timestamp, metadata_json = row

            # Extract metadata
            metadata: dict[str, Any] = (
                json.loads(metadata_json) if metadata_json else {}
            )

            # Create indexed content
            indexed_content = content
            if tags:
                indexed_content += " " + " ".join(f"tag:{tag}" for tag in tags)

            # Create search metadata
            base_metadata: dict[str, Any] = {
                "tags": tags or [],
                "timestamp": timestamp.isoformat() if timestamp else None,
                "content_length": len(content),
            }
            search_metadata: dict[str, Any] = base_metadata | metadata

            # Insert or update search index
            if self.reflection_db.conn:
                self.reflection_db.conn.execute(
                    """
                    INSERT INTO search_index
                    (id, content_type, content_id, indexed_content, search_metadata, last_indexed)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                    content_type = EXCLUDED.content_type,
                    content_id = EXCLUDED.content_id,
                    indexed_content = EXCLUDED.indexed_content,
                    search_metadata = EXCLUDED.search_metadata,
                    last_indexed = EXCLUDED.last_indexed
                    """,
                    [
                        f"refl_{refl_id}",
                        "reflection",
                        refl_id,
                        indexed_content,
                        json.dumps(search_metadata),
                        datetime.now(UTC),
                    ],
                )

        if self.reflection_db.conn:
            self.reflection_db.conn.commit()

    def _get_facet_queries(self) -> dict[str, str]:
        """Get facet query definitions."""
        return {
            "project": """
                SELECT JSON_EXTRACT_STRING(search_metadata, '$.project') as facet_value, COUNT(*) as count
                FROM search_index
                WHERE JSON_EXTRACT_STRING(search_metadata, '$.project') IS NOT NULL
                GROUP BY facet_value
                ORDER BY count DESC
            """,
            "content_type": """
                SELECT content_type as facet_value, COUNT(*) as count
                FROM search_index
                WHERE content_type IS NOT NULL
                GROUP BY facet_value
                ORDER BY count DESC
            """,
            "tags": """
                SELECT JSON_EXTRACT_STRING(search_metadata, '$.tags') as facet_value, COUNT(*) as count
                FROM search_index
                WHERE JSON_EXTRACT_STRING(search_metadata, '$.tags') IS NOT NULL
                GROUP BY facet_value
                ORDER BY count DESC
            """,
            "technical_terms": """
                SELECT JSON_EXTRACT_STRING(search_metadata, '$.technical_terms') as facet_value, COUNT(*) as count
                FROM search_index
                WHERE JSON_EXTRACT_STRING(search_metadata, '$.technical_terms') IS NOT NULL
                GROUP BY facet_value
                ORDER BY count DESC
            """,
        }

    def _should_process_facet_value(self, facet_value: Any) -> bool:
        """Check if facet value should be processed."""
        return isinstance(facet_value, str) and bool(facet_value)

    def _insert_facet_value(self, facet_name: str, facet_value: str) -> None:
        """Insert a single facet value into the database."""
        if not self.reflection_db.conn:
            return

        facet_id = hashlib.md5(
            f"{facet_name}_{facet_value}".encode(),
            usedforsecurity=False,
        ).hexdigest()

        self.reflection_db.conn.execute(
            """
            INSERT INTO search_facets
            (id, content_type, content_id, facet_name, facet_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
            content_type = EXCLUDED.content_type,
            content_id = EXCLUDED.content_id,
            facet_name = EXCLUDED.facet_name,
            facet_value = EXCLUDED.facet_value,
            created_at = EXCLUDED.created_at
            """,
            [
                facet_id,
                "search_facet",
                f"{facet_name}_{facet_value}",
                facet_name,
                facet_value,
                datetime.now(UTC).isoformat(),
            ],
        )

    def _process_facet_query(self, facet_name: str, sql: str) -> None:
        """Process a single facet query."""
        if not self.reflection_db.conn:
            return

        try:
            results = self.reflection_db.conn.execute(sql).fetchall()

            for facet_value, _count in results:
                if self._should_process_facet_value(facet_value):
                    self._insert_facet_value(facet_name, facet_value)
        except Exception:
            # Table doesn't exist yet, will be created during index rebuild
            return

    async def _update_search_facets(self) -> None:
        """Update search facets based on indexed content."""
        if not self.reflection_db.conn:
            return

        # Clear existing facets
        self.reflection_db.conn.execute("DELETE FROM search_facets")

        # Process each facet query
        facet_queries = self._get_facet_queries()
        for facet_name, sql in facet_queries.items():
            self._process_facet_query(facet_name, sql)

        # Commit all changes
        if self.reflection_db.conn:
            self.reflection_db.conn.commit()

    def _build_search_query(
        self,
        query: str,
        filters: list[SearchFilter] | None,
    ) -> str:
        """Build search query with filters."""
        # For now, return simple query - could be enhanced with query parsing
        return query

    def _build_filter_conditions(
        self,
        filters: list[SearchFilter],
    ) -> SQLCondition:
        """Build SQL conditions from filters."""
        conditions = []
        params: list[str | datetime] = []

        for filt in filters:
            condition_result = self._build_single_filter_condition(filt)
            if condition_result:
                conditions.append(condition_result.condition)
                params.extend(condition_result.params)

        return SQLCondition(condition=" AND ".join(conditions), params=params)

    def _build_single_filter_condition(self, filt: SearchFilter) -> SQLCondition | None:
        """Build a single filter condition."""
        if filt.field == "timestamp" and filt.operator == "range":
            return self._build_timestamp_range_condition(filt)
        if filt.operator == "eq":
            return self._build_equality_condition(filt)
        if filt.operator == "contains":
            return self._build_contains_condition(filt)
        return None

    def _build_timestamp_range_condition(
        self,
        filt: SearchFilter,
    ) -> SQLCondition | None:
        """Build timestamp range condition."""
        if not isinstance(filt.value, tuple | list) or len(filt.value) != 2:
            return None  # Skip invalid range values

        start_time, end_time = filt.value[0], filt.value[1]
        condition = "last_indexed BETWEEN ? AND ?"
        negated_condition = f"{'NOT ' if filt.negate else ''}{condition}"

        # Ensure params are strings or datetime objects
        params: list[str | datetime] = []
        if isinstance(start_time, str | datetime):
            params.append(start_time)
        if isinstance(end_time, str | datetime):
            params.append(end_time)

        return SQLCondition(condition=negated_condition, params=params)

    def _build_equality_condition(self, filt: SearchFilter) -> SQLCondition:
        """Build equality condition."""
        condition = f"JSON_EXTRACT_STRING(search_metadata, '$.{filt.field}') = ?"
        negated_condition = f"{'NOT ' if filt.negate else ''}{condition}"

        # Ensure value is a string or datetime
        params: list[str | datetime] = []
        if isinstance(filt.value, str | datetime):
            params.append(filt.value)
        elif (
            isinstance(filt.value, list)
            and filt.value
            and isinstance(filt.value[0], str | datetime)
        ):
            params.append(filt.value[0])

        return SQLCondition(condition=negated_condition, params=params)

    def _build_contains_condition(self, filt: SearchFilter) -> SQLCondition:
        """Build contains condition."""
        condition = "indexed_content LIKE ?"
        negated_condition = f"{'NOT ' if filt.negate else ''}{condition}"

        # Ensure value is a string
        value_str = str(filt.value) if not isinstance(filt.value, str) else filt.value
        params: list[str | datetime] = [f"%{value_str}%"]

        return SQLCondition(condition=negated_condition, params=params)

    async def _execute_search(
        self,
        query: str,
        sort_by: str,
        limit: int,
        offset: int,
        filters: list[SearchFilter] | None = None,
        content_type: str | None = None,
        timeframe: str | None = None,
    ) -> list[SearchResult]:
        """Execute the actual search."""
        sql_result = self._build_search_sql(
            query,
            content_type,
            timeframe,
            filters,
            sort_by,
            limit,
            offset,
        )

        if not self.reflection_db.conn:
            return []

        try:
            results = self.reflection_db.conn.execute(
                sql_result.condition,
                self._prepare_sql_params(sql_result.params),
            ).fetchall()
            return self._convert_sql_results_to_search_results(results)
        except Exception:
            # Table doesn't exist yet, will be created during index rebuild
            return []

    def _build_search_sql(
        self,
        query: str,
        content_type: str | None,
        timeframe: str | None,
        filters: list[SearchFilter] | None,
        sort_by: str,
        limit: int,
        offset: int,
    ) -> SQLCondition:
        """Build complete SQL query for search."""
        sql = """
            SELECT content_id, content_type, indexed_content, search_metadata, last_indexed
            FROM search_index
            WHERE indexed_content LIKE ?
        """
        params: list[str | datetime] = [f"%{query}%"]

        result = self._add_content_type_filter(sql, params, content_type)
        sql, params = result.condition, result.params

        result = self._add_timeframe_filter(sql, params, timeframe, content_type)
        sql, params = result.condition, result.params

        result = self._add_filter_conditions_to_sql(sql, params, filters)
        sql, params = result.condition, result.params

        sql = self._add_sorting_to_sql(sql, sort_by)
        sql += " LIMIT ? OFFSET ?"
        params.extend([str(limit), str(offset)])

        return SQLCondition(condition=sql, params=params)

    def _get_sql_field(self, field: str) -> str:
        """Map filter field to SQL column expression."""
        field_mappings = {
            "content_type": "content_type",
            "last_indexed": "last_indexed",
            "project": "JSON_EXTRACT_STRING(search_metadata, '$.project')",
            "timestamp": "JSON_EXTRACT_STRING(search_metadata, '$.timestamp')",
            "author": "JSON_EXTRACT_STRING(search_metadata, '$.author')",
            "tags": "JSON_EXTRACT_STRING(search_metadata, '$.tags')",
        }
        return field_mappings.get(
            field,
            f"JSON_EXTRACT_STRING(search_metadata, '$.{field}')",
        )

    def _apply_eq_filter(
        self,
        sql_field: str,
        negation: str,
        value: Any,
        params: list[str | datetime],
    ) -> tuple[str, list[str | datetime]]:
        """Apply equality filter."""
        sql_part = f" AND {negation}{sql_field} = ?"
        params.append(str(value))
        return sql_part, params

    def _apply_ne_filter(
        self,
        sql_field: str,
        negation: str,
        value: Any,
        params: list[str | datetime],
    ) -> tuple[str, list[str | datetime]]:
        """Apply not-equal filter."""
        sql_part = f" AND {negation}{sql_field} != ?"
        params.append(str(value))
        return sql_part, params

    def _apply_in_filter(
        self,
        sql_field: str,
        negation: str,
        value: Any,
        params: list[str | datetime],
    ) -> tuple[str, list[str | datetime]]:
        """Apply IN filter."""
        if isinstance(value, list):
            placeholders = ", ".join("?" * len(value))
            sql_part = f" AND {negation}{sql_field} IN ({placeholders})"
            params.extend([str(v) for v in value])
            return sql_part, params
        return "", params

    def _apply_not_in_filter(
        self,
        sql_field: str,
        negation: str,
        value: Any,
        params: list[str | datetime],
    ) -> tuple[str, list[str | datetime]]:
        """Apply NOT IN filter."""
        if isinstance(value, list):
            placeholders = ", ".join("?" * len(value))
            sql_part = f" AND {negation}{sql_field} NOT IN ({placeholders})"
            params.extend([str(v) for v in value])
            return sql_part, params
        return "", params

    def _apply_contains_filter(
        self,
        sql_field: str,
        negation: str,
        value: Any,
        params: list[str | datetime],
    ) -> tuple[str, list[str | datetime]]:
        """Apply CONTAINS filter."""
        sql_part = f" AND {negation}{sql_field} LIKE ?"
        params.append(f"%{value}%")
        return sql_part, params

    def _apply_starts_with_filter(
        self,
        sql_field: str,
        negation: str,
        value: Any,
        params: list[str | datetime],
    ) -> tuple[str, list[str | datetime]]:
        """Apply STARTS_WITH filter."""
        sql_part = f" AND {negation}{sql_field} LIKE ?"
        params.append(f"{value}%")
        return sql_part, params

    def _apply_ends_with_filter(
        self,
        sql_field: str,
        negation: str,
        value: Any,
        params: list[str | datetime],
    ) -> tuple[str, list[str | datetime]]:
        """Apply ENDS_WITH filter."""
        sql_part = f" AND {negation}{sql_field} LIKE ?"
        params.append(f"%{value}")
        return sql_part, params

    def _apply_range_filter(
        self,
        sql_field: str,
        filter_obj: SearchFilter,
        params: list[str | datetime],
    ) -> tuple[str, list[str | datetime]]:
        """Apply RANGE filter."""
        if isinstance(filter_obj.value, tuple) and len(filter_obj.value) == 2:
            if filter_obj.negate:
                sql_part = f" AND ({sql_field} < ? OR {sql_field} > ?)"
            else:
                sql_part = f" AND {sql_field} BETWEEN ? AND ?"
            params.extend([str(filter_obj.value[0]), str(filter_obj.value[1])])
            return sql_part, params
        return "", params

    def _add_filter_conditions_to_sql(
        self,
        sql: str,
        params: list[str | datetime],
        filters: list[SearchFilter] | None,
    ) -> SQLCondition:
        """Add custom filter conditions to SQL query."""
        if not filters:
            return SQLCondition(condition=sql, params=params)

        for filter_obj in filters:
            sql_field = self._get_sql_field(filter_obj.field)
            negation = "NOT " if filter_obj.negate else ""

            # Dispatch to appropriate filter handler
            operator_handlers = {
                "eq": lambda: self._apply_eq_filter(
                    sql_field,
                    negation,
                    filter_obj.value,
                    params,
                ),
                "ne": lambda: self._apply_ne_filter(
                    sql_field,
                    negation,
                    filter_obj.value,
                    params,
                ),
                "in": lambda: self._apply_in_filter(
                    sql_field,
                    negation,
                    filter_obj.value,
                    params,
                ),
                "not_in": lambda: self._apply_not_in_filter(
                    sql_field,
                    negation,
                    filter_obj.value,
                    params,
                ),
                "contains": lambda: self._apply_contains_filter(
                    sql_field,
                    negation,
                    filter_obj.value,
                    params,
                ),
                "starts_with": lambda: self._apply_starts_with_filter(
                    sql_field,
                    negation,
                    filter_obj.value,
                    params,
                ),
                "ends_with": lambda: self._apply_ends_with_filter(
                    sql_field,
                    negation,
                    filter_obj.value,
                    params,
                ),
                "range": lambda: self._apply_range_filter(
                    sql_field,
                    filter_obj,
                    params,
                ),
            }

            handler = operator_handlers.get(filter_obj.operator)
            if handler:
                sql_part, params = handler()
                sql += sql_part

        return SQLCondition(condition=sql, params=params)

    def _add_content_type_filter(
        self,
        sql: str,
        params: list[str | datetime],
        content_type: str | None,
    ) -> SQLCondition:
        """Add content type filter to SQL query."""
        if content_type:
            sql += " AND content_type = ?"
            params.append(content_type)
        return SQLCondition(condition=sql, params=params)

    def _add_timeframe_filter(
        self,
        sql: str,
        params: list[str | datetime],
        timeframe: str | None,
        content_type: str | None,
    ) -> SQLCondition:
        """Add timeframe filter to SQL query."""
        if (
            timeframe and content_type
        ):  # Only add timeframe if content_type is also specified
            cutoff_date = parse_timeframe_single(timeframe)
            if cutoff_date:
                sql += " AND last_indexed >= ?"
                params.append(cutoff_date.isoformat())
        return SQLCondition(condition=sql, params=params)

    def _add_sorting_to_sql(self, sql: str, sort_by: str) -> str:
        """Add sorting clause to SQL query."""
        if sort_by == "date":
            sql += " ORDER BY last_indexed DESC"
        elif sort_by == "project":
            sql += " ORDER BY JSON_EXTRACT_STRING(search_metadata, '$.project')"
        else:  # relevance - simple for now
            sql += " ORDER BY LENGTH(indexed_content) DESC"  # Longer content = more relevant
        return sql

    def _prepare_sql_params(self, params: list[str | datetime]) -> list[str]:
        """Prepare parameters for SQL execution."""
        return [
            param.isoformat() if isinstance(param, datetime) else str(param)
            for param in params
        ]

    def _convert_sql_results_to_search_results(
        self,
        results: list[tuple[Any, ...]],
    ) -> list[SearchResult]:
        """Convert SQL results to SearchResult objects."""
        search_results = []
        for row in results:
            (
                content_id,
                content_type,
                indexed_content,
                search_metadata_json,
                last_indexed,
            ) = row
            metadata: dict[str, Any] = (
                json.loads(search_metadata_json) if search_metadata_json else {}
            )

            search_results.append(
                SearchResult(
                    content_id=content_id,
                    content_type=content_type or "unknown",
                    title=f"{(content_type or 'unknown').title()} from {metadata.get('project', 'Unknown')}",
                    content=truncate_content(indexed_content),
                    score=0.8,  # Simple scoring for now
                    project=metadata.get("project"),
                    timestamp=ensure_timezone(last_indexed),
                    metadata=metadata,
                ),
            )
        return search_results

    async def _add_highlights(
        self,
        results: list[SearchResult],
        query: str,
    ) -> list[SearchResult]:
        """Add search highlights to results."""
        query_terms = query.lower().split()

        for result in results:
            highlights = []
            content_lower = result.content.lower()

            for term in query_terms:
                if term in content_lower:
                    # Find context around the term
                    start_pos = content_lower.find(term)
                    context_start = max(0, start_pos - 50)
                    context_end = min(len(result.content), start_pos + len(term) + 50)

                    highlight = result.content[context_start:context_end]
                    highlight = highlight.replace(term, f"<mark>{term}</mark>")
                    highlights.append(highlight)

            result.highlights = highlights[:3]  # Limit to 3 highlights

        return results

    async def _calculate_facets(
        self,
        query: str,
        filters: list[SearchFilter] | None,
        requested_facets: list[str],
    ) -> dict[str, SearchFacet]:
        """Calculate facet counts for search results."""
        facets = {}

        for facet_name in requested_facets:
            if facet_name in self.facet_configs:
                facet_config = self.facet_configs[facet_name]

                sql = """
                    SELECT facet_value, COUNT(*) as count
                    FROM search_facets sf
                    JOIN search_index si ON sf.content_id = si.id
                    WHERE sf.facet_name = ? AND si.indexed_content LIKE ?
                    GROUP BY facet_value
                    ORDER BY count DESC
                    LIMIT ?
                """

                if not self.reflection_db.conn:
                    continue

                try:
                    results = self.reflection_db.conn.execute(
                        sql,
                        [facet_name, f"%{query}%", facet_config["size"]],
                    ).fetchall()

                    facets[facet_name] = SearchFacet(
                        name=facet_name,
                        values=[
                            (str(row[0]) if row[0] is not None else "", row[1])
                            for row in results
                        ],
                        facet_type=str(facet_config["type"]),
                    )
                except Exception:
                    # Table doesn't exist yet, will be created during index rebuild
                    continue

        return facets
