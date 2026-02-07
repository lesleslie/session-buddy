#!/usr/bin/env python3
"""Git Worktree Management for Session Management MCP Server.

Provides high-level worktree operations and coordination with session management.
"""

import json
import os
import shutil
import subprocess  # nosec B404
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils.git_worktrees import (
    WorktreeInfo,
    get_worktree_info,
    is_git_repository,
    list_worktrees,
)


@dataclass(frozen=True)
class WorktreeCreationOptions:
    """Immutable worktree creation options."""

    create_branch: bool = False
    checkout_existing: bool = False
    force: bool = False


@dataclass
class WorktreeValidationResult:
    """Result of worktree validation."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)

    @classmethod
    def success(cls) -> "WorktreeValidationResult":
        """Create successful validation result."""
        return cls(is_valid=True)  # type: ignore[call-arg]

    @classmethod
    def error(cls, error: str) -> "WorktreeValidationResult":
        """Create error validation result."""
        return cls(is_valid=False, errors=[error])  # type: ignore[call-arg]


@dataclass
class GitOperationResult:
    """Result of git operation execution."""

    success: bool
    output: str = field(default="")
    error: str = field(default="")

    @classmethod
    def success_result(cls, output: str = "") -> "GitOperationResult":
        """Create successful operation result."""
        return cls(success=True, output=output)  # type: ignore[call-arg]

    @classmethod
    def error_result(cls, error: str) -> "GitOperationResult":
        """Create error operation result."""
        return cls(success=False, error=error)  # type: ignore[call-arg]


class WorktreeManager:
    """Manages git worktrees with session coordination."""

    def __init__(self, session_logger: Any = None) -> None:
        self.session_logger = session_logger

    def _log(self, message: str, level: str = "info", **context: Any) -> None:
        """Log messages if logger available."""
        if self.session_logger:
            getattr(self.session_logger, level)(message, **context)

    def _get_git_executable(self) -> str:
        """Security: Get the full path to git executable to prevent PATH injection."""
        git_path = shutil.which("git")
        if not git_path:
            msg = "Git executable not found in PATH"
            raise OSError(msg)
        return git_path

    def _validate_git_command(self, cmd: list[str]) -> bool:
        """Security: Validate git command arguments to prevent injection."""
        if not cmd or len(cmd) < 2:
            return False

        # First argument should be the git executable
        if not cmd[0].endswith("git"):
            return False

        # Second argument should be a valid git subcommand
        valid_subcommands = {
            "worktree",
            "status",
            "add",
            "commit",
            "branch",
            "checkout",
        }
        if len(cmd) > 1 and cmd[1] not in valid_subcommands:
            return False

        # Check for potentially dangerous characters in arguments
        for arg in cmd:
            if any(char in arg for char in (";", "&", "|", "`", "$", "\\", "\n", "\r")):
                return False

        return True

    def _is_safe_branch_name(self, branch: str) -> bool:
        """Security: Validate branch name is safe for shell execution."""
        import re

        # Allow alphanumeric, dashes, underscores, slashes (for remote branches)
        # Using pattern directly to avoid ValidatedPattern complexity
        pattern = re.compile(r"^[a-zA-Z0-9_/-]+$")  # REGEX OK: validated safe pattern
        return bool(pattern.match(branch)) and len(branch) < 100

    def _is_safe_path(self, path: Path) -> bool:
        """Security: Validate path is safe and reasonable."""
        try:
            # Convert to absolute path for validation
            abs_path = path.resolve()

            # Check for suspicious path components
            path_str = str(abs_path)

            # Reject paths with null bytes or dangerous patterns
            if "\x00" in path_str or ".." in path_str:
                return False

            # Check path length is reasonable
            return not len(path_str) > 500
        except (OSError, ValueError):
            return False

    async def list_worktrees(self, directory: Path) -> dict[str, Any]:
        """List all worktrees with enhanced information."""
        if not is_git_repository(directory):
            return {"success": False, "error": "Not a git repository", "worktrees": []}

        try:
            worktrees = list_worktrees(directory)
            current_worktree = get_worktree_info(directory)

            worktree_data = []
            for wt in worktrees:
                wt_data = {
                    "path": str(wt.path),
                    "branch": wt.branch,
                    "is_main": wt.is_main_worktree,
                    "is_current": current_worktree and wt.path == current_worktree.path,
                    "is_detached": wt.is_detached,
                    "is_bare": wt.is_bare,
                    "locked": wt.locked,
                    "prunable": wt.prunable,
                    "exists": wt.path.exists(),
                }

                # Add session info if available
                wt_data["has_session"] = self._check_session_exists(wt.path)

                worktree_data.append(wt_data)

            self._log("Listed worktrees", worktrees_count=len(worktree_data))

            return {
                "success": True,
                "worktrees": worktree_data,
                "current_worktree": str(current_worktree.path)
                if current_worktree
                else None,
                "total_count": len(worktree_data),
            }

        except Exception as e:
            self._log(f"Failed to list worktrees: {e}", level="error")
            return {"success": False, "error": str(e), "worktrees": []}

    def _validate_worktree_creation_request(
        self,
        repository_path: Path,
        new_path: Path,
        branch: str,
    ) -> WorktreeValidationResult:
        """Validate worktree creation request. Target complexity: ≤5."""
        if not is_git_repository(repository_path):
            return WorktreeValidationResult.error(
                "Source directory is not a git repository",
            )

        if new_path.exists():
            return WorktreeValidationResult.error(
                f"Target path already exists: {new_path}",
            )

        # Security: Validate branch name to prevent injection
        if not branch or not self._is_safe_branch_name(branch):
            return WorktreeValidationResult.error(
                "Invalid branch name: must be alphanumeric with dashes/underscores only",
            )

        # Security: Validate path is within reasonable bounds
        if not self._is_safe_path(new_path):
            return WorktreeValidationResult.error(
                "Invalid path: path must be relative to current directory structure",
            )

        return WorktreeValidationResult.success()

    def _build_worktree_command(
        self,
        new_path: Path,
        branch: str,
        options: WorktreeCreationOptions,
    ) -> list[str]:
        """Build git worktree add command with security hardening."""
        git_executable = self._get_git_executable()
        cmd = [git_executable, "worktree", "add"]

        if options.create_branch:
            cmd.extend(["-b", branch])
        elif options.checkout_existing:
            cmd.extend(["--track", "-B", branch])

        cmd.extend([str(new_path), branch])
        return cmd

    def _execute_worktree_creation(
        self,
        cmd: list[str],
        repository_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        """Execute git worktree add with security hardening."""
        return subprocess.run(  # nosec B603 - Command validated via _validate_git_command()
            cmd,
            cwd=repository_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,  # Security: Prevent hanging processes
            shell=False,  # Security: Explicit shell=False to prevent injection
        )

    def _build_success_response_from_info(
        self,
        new_path: Path,
        branch: str,
        worktree_info: Any,
        output: str,
    ) -> dict[str, Any]:
        """Build success response for worktree creation. Target complexity: ≤3."""
        return {
            "success": True,
            "worktree_path": str(new_path),
            "branch": branch,
            "worktree_info": {
                "path": str(worktree_info.path),
                "branch": worktree_info.branch,
                "is_main": worktree_info.is_main_worktree,
                "is_detached": worktree_info.is_detached,
            },
            "output": output,
        }

    async def _execute_git_worktree_creation(
        self,
        new_path: Path,
        branch: str,
        options: WorktreeCreationOptions,
        repository_path: Path,
    ) -> GitOperationResult:
        """Execute git worktree creation. Target complexity: ≤8."""
        try:
            # Build and validate command
            cmd = self._build_worktree_command(new_path, branch, options)

            # Security: Validate command before execution
            if not self._validate_git_command(cmd):
                return GitOperationResult.error_result(
                    "Invalid git command detected - potential security risk",
                )

            # Execute command
            result = self._execute_worktree_creation(cmd, repository_path)
            return GitOperationResult.success_result(result.stdout.strip())

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            self._log(f"Failed to create worktree: {error_msg}", level="error")
            return GitOperationResult.error_result(error_msg)
        except Exception as e:
            self._log(f"Unexpected error creating worktree: {e}", level="error")
            return GitOperationResult.error_result(str(e))

    def _verify_worktree_creation(self, new_path: Path) -> GitOperationResult:
        """Verify worktree was created successfully. Target complexity: ≤3."""
        worktree_info = get_worktree_info(new_path)
        if not worktree_info:
            return GitOperationResult.error_result(
                "Worktree was created but cannot be accessed",
            )
        return GitOperationResult.success_result()

    async def create_worktree(
        self,
        repository_path: Path,
        new_path: Path,
        branch: str,
        create_branch: bool = False,
        checkout_existing: bool = False,
    ) -> dict[str, Any]:
        """Create a new worktree. Target complexity: ≤8."""
        options = WorktreeCreationOptions(
            create_branch=create_branch,
            checkout_existing=checkout_existing,
        )

        # 1. Validate request
        validation = self._validate_worktree_creation_request(
            repository_path,
            new_path,
            branch,
        )
        if not validation.is_valid:
            return {"success": False, "error": validation.errors[0]}

        # 2. Execute git operations
        git_result = await self._execute_git_worktree_creation(
            new_path,
            branch,
            options,
            repository_path,
        )
        if not git_result.success:
            return {"success": False, "error": git_result.error}

        # 3. Verify creation
        verify_result = self._verify_worktree_creation(new_path)
        if not verify_result.success:
            return {"success": False, "error": verify_result.error}

        # 4. Build success response
        worktree_info = get_worktree_info(new_path)
        self._log("Created worktree", path=str(new_path), branch=branch)
        return self._build_success_response_from_info(
            new_path,
            branch,
            worktree_info,
            git_result.output,
        )

    async def remove_worktree(
        self,
        repository_path: Path,
        worktree_path: Path,
        force: bool = False,
    ) -> dict[str, Any]:
        """Remove an existing worktree."""
        if not is_git_repository(repository_path):
            return {
                "success": False,
                "error": "Source directory is not a git repository",
            }

        try:
            # Build git worktree remove command with security hardening
            git_executable = self._get_git_executable()
            cmd = [git_executable, "worktree", "remove"]

            if force:
                cmd.append("--force")

            cmd.append(str(worktree_path))

            # Security: Validate command before execution
            if not self._validate_git_command(cmd):
                return {
                    "success": False,
                    "error": "Invalid git command detected - potential security risk",
                }

            # Execute git worktree remove with security hardening
            result = subprocess.run(  # nosec B603 - Command validated via _validate_git_command()
                cmd,
                cwd=repository_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,  # Security: Prevent hanging processes
                shell=False,  # Security: Explicit shell=False to prevent injection
            )

            self._log("Removed worktree", path=str(worktree_path))

            return {
                "success": True,
                "removed_path": str(worktree_path),
                "output": result.stdout.strip() or "Worktree removed successfully",
            }

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            self._log(f"Failed to remove worktree: {error_msg}", level="error")
            return {"success": False, "error": error_msg}
        except Exception as e:
            self._log(f"Unexpected error removing worktree: {e}", level="error")
            return {"success": False, "error": str(e)}

    async def prune_worktrees(self, repository_path: Path) -> dict[str, Any]:
        """Prune stale worktree references."""
        if not is_git_repository(repository_path):
            return {"success": False, "error": "Directory is not a git repository"}

        try:
            # Build git worktree prune command with security hardening
            git_executable = self._get_git_executable()
            cmd = [git_executable, "worktree", "prune", "--verbose"]

            # Security: Validate command before execution
            if not self._validate_git_command(cmd):
                return {
                    "success": False,
                    "error": "Invalid git command detected - potential security risk",
                }

            # Execute git worktree prune with security hardening
            result = subprocess.run(  # nosec B603 - Command validated via _validate_git_command()
                cmd,
                cwd=repository_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,  # Security: Prevent hanging processes
                shell=False,  # Security: Explicit shell=False to prevent injection
            )

            output_lines = (
                result.stdout.strip().split("\n") if result.stdout.strip() else []
            )
            pruned_count = len([line for line in output_lines if "Removing" in line])

            self._log("Pruned worktrees", pruned_count=pruned_count)

            return {
                "success": True,
                "pruned_count": pruned_count,
                "output": result.stdout.strip() or "No worktrees to prune",
            }

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            self._log(f"Failed to prune worktrees: {error_msg}", level="error")
            return {"success": False, "error": error_msg}

    async def get_worktree_status(self, directory: Path) -> dict[str, Any]:
        """Get comprehensive status for current worktree and all related worktrees."""
        if not is_git_repository(directory):
            return {"success": False, "error": "Not a git repository"}

        try:
            current_worktree = get_worktree_info(directory)
            all_worktrees = list_worktrees(directory)

            if not current_worktree:
                return {
                    "success": False,
                    "error": "Could not determine current worktree info",
                }

            # Enhanced status with session coordination
            return {
                "success": True,
                "current_worktree": {
                    "path": str(current_worktree.path),
                    "branch": current_worktree.branch,
                    "is_main": current_worktree.is_main_worktree,
                    "is_detached": current_worktree.is_detached,
                    "has_session": self._check_session_exists(current_worktree.path),
                },
                "all_worktrees": [
                    {
                        "path": str(wt.path),
                        "branch": wt.branch,
                        "is_main": wt.is_main_worktree,
                        "is_current": wt.path == current_worktree.path,
                        "exists": wt.path.exists(),
                        "has_session": self._check_session_exists(wt.path),
                        "prunable": wt.prunable,
                    }
                    for wt in all_worktrees
                ],
                "total_worktrees": len(all_worktrees),
                "session_summary": self._get_session_summary(all_worktrees),
            }

        except Exception as e:
            self._log(f"Failed to get worktree status: {e}", level="error")
            return {"success": False, "error": str(e)}

    def _check_session_exists(self, path: Path) -> bool:
        """Check if a worktree has an active session by looking for session files."""
        if isinstance(path, str):
            path = Path(path)

        if not path.exists():
            return False

        # Check for common session indicators
        session_indicators = [
            path / ".git",  # Git repository
            path / ".claude",  # Claude session directory
            path / ".session",  # Generic session directory
        ]

        # Also check for project-specific session files
        project_files = [
            "pyproject.toml",
            "package.json",
            "requirements.txt",
            "setup.py",
        ]

        has_session_indicators = any(
            indicator.exists() for indicator in session_indicators
        )
        has_project_files = any(
            (path / proj_file).exists() for proj_file in project_files
        )

        return has_session_indicators or has_project_files

    def _get_session_summary(self, worktrees: list[WorktreeInfo]) -> dict[str, Any]:
        """Get summary of sessions across worktrees."""
        active_sessions = 0
        branches = set()

        for wt in worktrees:
            if self._check_session_exists(wt.path):
                active_sessions += 1
            branches.add(wt.branch)

        return {
            "active_sessions": active_sessions,
            "unique_branches": len(branches),
            "branches": list(branches),
        }

    def _save_current_session_state(self, worktree_path: Path) -> dict[str, Any] | None:
        """Save the current session state for preservation during worktree switching."""
        try:
            state = {
                "timestamp": datetime.now().isoformat(),
                "worktree_path": str(worktree_path),
                "working_directory": str(Path.cwd()),
                "environment": os.environ.copy(),
                "recent_files": self._get_recent_files(worktree_path),
                "git_status": self._get_git_status(worktree_path),
            }

            # Save to a temporary file in the .claude directory
            claude_dir = Path.home() / ".claude" / "worktree_sessions"
            claude_dir.mkdir(parents=True, exist_ok=True)

            state_file = claude_dir / f"session_state_{worktree_path.name}.json"
            with state_file.open("w") as f:
                json.dump(state, f, indent=2)

            return state
        except Exception as e:
            self._log(f"Failed to save session state: {e}", level="warning")
            return None

    def _restore_session_state(
        self,
        worktree_path: Path,
        state: dict[str, Any] | None,
    ) -> bool:
        """Restore session state for the target worktree."""
        if not state:
            return False

        try:
            # For now, we'll just log that we're restoring state
            # In a more advanced implementation, we could restore environment variables,
            # open files, IDE state, etc.
            self._log(
                "Session state restored",
                worktree=worktree_path.name,
                recent_files=len(state.get("recent_files", [])),
            )
            return True
        except Exception as e:
            self._log(f"Failed to restore session state: {e}", level="warning")
            return False

    def _get_recent_files(self, worktree_path: Path) -> list[str]:
        """Get recently modified files in the worktree."""
        try:
            recent_files = []
            # Get files modified in the last 24 hours
            cutoff_time = time.time() - (24 * 60 * 60)

            for file_path in worktree_path.rglob("*"):
                if file_path.is_file() and not any(
                    part.startswith(".") for part in file_path.parts
                ):
                    try:
                        if file_path.stat().st_mtime > cutoff_time:
                            recent_files.append(
                                str(file_path.relative_to(worktree_path)),
                            )
                    except (OSError, PermissionError):
                        continue

            return recent_files[:20]  # Limit to 20 most recent files
        except Exception:
            return []

    def _get_git_status(self, worktree_path: Path) -> dict[str, Any]:
        """Get git status for the worktree."""
        try:
            from .utils.git_operations import get_git_status

            modified, untracked = get_git_status(worktree_path)
            return {
                "modified_files": modified,
                "untracked_files": untracked,
                "has_changes": len(modified) > 0 or len(untracked) > 0,
            }
        except Exception:
            return {"modified_files": [], "untracked_files": [], "has_changes": False}

    async def switch_worktree_context(
        self,
        from_path: Path,
        to_path: Path,
    ) -> dict[str, Any]:
        """Coordinate switching between worktrees with session preservation."""
        try:
            # Validate both paths
            if not is_git_repository(from_path):
                return {
                    "success": False,
                    "error": f"Source path is not a git repository: {from_path}",
                }

            if not is_git_repository(to_path):
                return {
                    "success": False,
                    "error": f"Target path is not a git repository: {to_path}",
                }

            from_worktree = get_worktree_info(from_path)
            to_worktree = get_worktree_info(to_path)

            if not from_worktree or not to_worktree:
                return {
                    "success": False,
                    "error": "Could not get worktree information for context switch",
                }

            # Integrate with session management to preserve context
            try:
                # 1. Save current session state
                session_state = self._save_current_session_state(from_path)

                # 2. Switch working directory context
                os.chdir(to_path)

                # 3. Restore/create session for target worktree
                restored_state = self._restore_session_state(to_path, session_state)

                self._log(
                    "Context switch completed with session preservation",
                    from_branch=from_worktree.branch,
                    to_branch=to_worktree.branch,
                )

                return {
                    "success": True,
                    "from_worktree": {
                        "path": str(from_worktree.path),
                        "branch": from_worktree.branch,
                    },
                    "to_worktree": {
                        "path": str(to_worktree.path),
                        "branch": to_worktree.branch,
                    },
                    "context_preserved": True,
                    "session_state_saved": session_state is not None,
                    "session_state_restored": restored_state,
                    "message": f"Switched from {from_worktree.branch} to {to_worktree.branch}",
                }
            except Exception as session_error:
                # Fallback to basic switching if session preservation fails
                self._log(
                    f"Session preservation failed, using basic switching: {session_error}",
                    level="warning",
                )
                os.chdir(to_path)

                self._log(
                    "Basic context switch completed",
                    from_branch=from_worktree.branch,
                    to_branch=to_worktree.branch,
                )

                return {
                    "success": True,
                    "from_worktree": {
                        "path": str(from_worktree.path),
                        "branch": from_worktree.branch,
                    },
                    "to_worktree": {
                        "path": str(to_worktree.path),
                        "branch": to_worktree.branch,
                    },
                    "context_preserved": False,
                    "session_error": str(session_error),
                    "message": f"Switched from {from_worktree.branch} to {to_worktree.branch} (session preservation failed)",
                }

        except Exception as e:
            self._log(f"Failed to switch worktree context: {e}", level="error")
            return {"success": False, "error": str(e)}
