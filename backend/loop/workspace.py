"""Workspace resolution and security guards for Antigravity (AGY) builds.

Handles:
- Dynamic Desktop resolution accounting for OneDrive redirection.
- Jailed per-run workspace subfolders (<root>/<project-slug>/).
- Strict workspace path validation (preventing traversal, symlink escapes, out-of-boundary writes).
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Union

from backend.config import settings
from backend.logging import logger


def resolve_desktop_path() -> Path:
    """
    Resolve the user's real Desktop path, accounting for OneDrive redirection.
    Checks:
    1. %OneDrive%\\Desktop
    2. %USERPROFILE%\\OneDrive\\Desktop
    3. %USERPROFILE%\\Desktop
    4. Fallback to ~/Desktop
    """
    candidates = []

    onedrive = os.environ.get("OneDrive")
    if onedrive:
        candidates.append(Path(onedrive) / "Desktop")

    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        candidates.append(Path(userprofile) / "OneDrive" / "Desktop")
        candidates.append(Path(userprofile) / "Desktop")

    # Path.home() fallback
    try:
        candidates.append(Path.home() / "Desktop")
    except Exception:
        pass

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()

    # If none exist yet, prefer %USERPROFILE%\Desktop or Path.home()\Desktop
    if userprofile:
        fallback = Path(userprofile) / "Desktop"
    else:
        fallback = Path.home() / "Desktop"

    fallback.mkdir(parents=True, exist_ok=True)
    return fallback.resolve()


def get_default_workspace_root() -> Path:
    """Return the base root directory for AGY workspaces (Desktop\\test by default)."""
    if settings.AGY_WORKSPACE_ROOT:
        root = Path(settings.AGY_WORKSPACE_ROOT)
    else:
        root = resolve_desktop_path() / "test"

    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def sanitize_slug(slug: str) -> str:
    """Sanitize loop run id or project name into a safe directory name."""
    clean = "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in slug)
    return clean.strip("._") or "nomad_build"


def get_loop_workspace(loop_run_id_or_slug: str, base_root: Optional[Path] = None) -> Path:
    """Get the dedicated subfolder for a loop run, ensuring it exists."""
    root = (base_root or get_default_workspace_root()).resolve()
    safe_slug = sanitize_slug(loop_run_id_or_slug)
    workspace = (root / safe_slug).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def is_path_inside_workspace(path_to_check: Union[str, Path], workspace_dir: Path) -> bool:
    """
    Verify whether a path resolves strictly inside the allowed workspace directory.
    Resolves symlinks, relative traversals (..), and checks common path boundaries.
    """
    try:
        target = Path(path_to_check)
        if not target.is_absolute():
            target = workspace_dir / target

        resolved_target = target.resolve()
        resolved_workspace = workspace_dir.resolve()

        # Target must equal workspace or be a child of workspace
        return (
            resolved_target == resolved_workspace
            or resolved_workspace in resolved_target.parents
        )
    except Exception as e:
        logger.warning(f"[WorkspaceGuard] Path resolution failed for '{path_to_check}': {e}")
        return False


def validate_workspace_files(files: list, workspace_dir: Path) -> tuple[bool, list[str]]:
    """
    Validate a list of reported files.
    Returns (all_valid, list_of_violations).
    """
    violations = []
    for f in files:
        if not is_path_inside_workspace(f, workspace_dir):
            violations.append(str(f))

    if violations:
        logger.error(
            f"[WorkspaceGuard] VIOLATION: Files detected outside workspace '{workspace_dir}': {violations}"
        )
        return False, violations
    return True, []


def clean_loop_workspace(loop_run_id_or_slug: str, base_root: Optional[Path] = None) -> bool:
    """
    Safely delete only a loop run's own subfolder.
    NEVER deletes the root workspace folder.
    """
    root = (base_root or get_default_workspace_root()).resolve()
    safe_slug = sanitize_slug(loop_run_id_or_slug)
    target_dir = (root / safe_slug).resolve()

    if target_dir == root:
        logger.critical("[WorkspaceGuard] Refusing to delete workspace root!")
        return False

    if target_dir.exists() and target_dir.is_dir():
        shutil.rmtree(target_dir)
        logger.info(f"[WorkspaceGuard] Cleaned workspace subfolder: {target_dir}")
        return True
    return False
