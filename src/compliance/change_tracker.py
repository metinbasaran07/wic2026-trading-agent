"""Change tracker for competition compliance."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from loguru import logger

from src.config.settings import get_settings

if TYPE_CHECKING:
    from src.compliance.logger import OperationLogger


@dataclass
class ChangeRecord:
    """Record of a change to strategy, parameters, or code."""

    timestamp: datetime
    change_id: str
    change_type: str  # parameter, strategy, code, risk, config
    description: str
    author: str  # "agent", "human", "llm"
    auto_approved: bool = False

    # Change details
    target: str = ""  # What was changed (e.g., "strategy.params.rsi_period")
    old_value: Any = None
    new_value: Any = None

    # Context
    reason: str = ""
    llm_recommendation: bool = False
    review_id: str | None = None

    # Compliance
    pre_approved: bool = False
    """Whether change was in pre-report"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "change_id": self.change_id,
            "change_type": self.change_type,
            "description": self.description,
            "author": self.author,
            "auto_approved": self.auto_approved,
            "target": self.target,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "llm_recommendation": self.llm_recommendation,
            "review_id": self.review_id,
            "pre_approved": self.pre_approved,
        }


class ChangeTracker:
    """Tracks all changes for competition compliance."""

    def __init__(self, operation_logger: OperationLogger | None = None) -> None:
        self.settings = get_settings()
        self.log_dir = self.settings.LOG_DIR
        self.changes_file = self.log_dir / "changes.jsonl"
        self.code_hashes_file = self.log_dir / "code_hashes.json"

        self.operation_logger = operation_logger or get_operation_logger()
        self.changes: list[ChangeRecord] = []
        self.code_hashes: dict[str, str] = {}
        self.pre_approved_changes: set[str] = set()

        self._load_changes()
        self._load_code_hashes()

    def _load_changes(self) -> None:
        """Load change history from file."""
        if self.changes_file.exists():
            with open(self.changes_file) as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
                        self.changes.append(ChangeRecord(**data))
                    except Exception:
                        pass

    def _load_code_hashes(self) -> None:
        """Load code file hashes for detecting code changes."""
        if self.code_hashes_file.exists():
            with open(self.code_hashes_file) as f:
                self.code_hashes = json.load(f)

    def _save_code_hashes(self) -> None:
        """Save code hashes."""
        with open(self.code_hashes_file, "w") as f:
            json.dump(self.code_hashes, f, indent=2)

    def _generate_change_id(self) -> str:
        """Generate unique change ID."""
        return hashlib.md5(f"{datetime.now().isoformat()}".encode()).hexdigest()[:12]

    def record_change(
        self,
        change_type: str,
        target: str,
        old_value: Any,
        new_value: Any,
        description: str,
        reason: str = "",
        author: str = "agent",
        auto_approved: bool = False,
        llm_recommendation: bool = False,
        review_id: str | None = None,
    ) -> ChangeRecord:
        """Record a change."""
        change = ChangeRecord(
            timestamp=datetime.now(),
            change_id=self._generate_change_id(),
            change_type=change_type,
            target=target,
            old_value=old_value,
            new_value=new_value,
            description=description,
            reason=reason,
            author=author,
            auto_approved=auto_approved,
            llm_recommendation=llm_recommendation,
            review_id=review_id,
            pre_approved=self._is_pre_approved(target, old_value, new_value),
        )

        self.changes.append(change)

        # Write to JSONL
        with open(self.changes_file, "a") as f:
            f.write(json.dumps(change.to_dict(), default=str) + "\n")

        # Also log to operation logger
        self.operation_logger.log_change(
            change_type=change_type,
            description=description,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            auto=auto_approved,
        )

        logger.info(f"Change recorded: {change.change_id} - {description}")
        return change

    def _is_pre_approved(self, target: str, old_value: Any, new_value: Any) -> bool:
        """Check if change was pre-approved in pre-report."""
        change_key = f"{target}:{old_value}->{new_value}"
        return change_key in self.pre_approved_changes

    def add_pre_approved_change(self, target: str, old_value: Any, new_value: Any) -> None:
        """Add a change to pre-approved list (from pre-report)."""
        change_key = f"{target}:{old_value}->{new_value}"
        self.pre_approved_changes.add(change_key)

    def scan_code_changes(self, source_dirs: list[str] | None = None) -> list[ChangeRecord]:
        """Scan for code changes since last check."""
        source_dirs = source_dirs or ["src", "tests"]
        new_changes = []

        for src_dir in source_dirs:
            path = Path(src_dir)
            if not path.exists():
                continue

            for py_file in path.rglob("*.py"):
                try:
                    content = py_file.read_text(encoding="utf-8")
                    current_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                    relative_path = str(py_file)

                    if relative_path in self.code_hashes:
                        if self.code_hashes[relative_path] != current_hash:
                            # Code changed
                            change = self.record_change(
                                change_type="code",
                                target=relative_path,
                                old_value=self.code_hashes[relative_path],
                                new_value=current_hash,
                                description=f"Code modified: {relative_path}",
                                reason="Code change detected",
                                author="human",
                            )
                            new_changes.append(change)
                            self.code_hashes[relative_path] = current_hash
                    else:
                        # New file
                        self.code_hashes[relative_path] = current_hash

                except Exception as e:
                    logger.warning(f"Failed to hash {py_file}: {e}")

        if new_changes:
            self._save_code_hashes()

        return new_changes

    def get_changes_since(self, since: datetime) -> list[ChangeRecord]:
        """Get changes since a timestamp."""
        return [c for c in self.changes if c.timestamp >= since]

    def get_changes_by_type(self, change_type: str) -> list[ChangeRecord]:
        """Get changes by type."""
        return [c for c in self.changes if c.change_type == change_type]

    def get_unapproved_changes(self) -> list[ChangeRecord]:
        """Get changes that weren't pre-approved."""
        return [c for c in self.changes if not c.pre_approved and not c.auto_approved]

    def get_change_summary(self, start: datetime, end: datetime) -> dict[str, Any]:
        """Get change summary for a period."""
        period_changes = [c for c in self.changes if start <= c.timestamp <= end]

        by_type = {}
        by_author = {}
        for c in period_changes:
            by_type[c.change_type] = by_type.get(c.change_type, 0) + 1
            by_author[c.author] = by_author.get(c.author, 0) + 1

        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "total_changes": len(period_changes),
            "by_type": by_type,
            "by_author": by_author,
            "unapproved": len([c for c in period_changes if not c.pre_approved]),
            "llm_recommended": len([c for c in period_changes if c.llm_recommendation]),
        }

    def export_for_report(self, start: datetime, end: datetime) -> list[dict]:
        """Export changes for competition report."""
        changes = self.get_changes_since(start)
        return [c.to_dict() for c in changes if c.timestamp <= end]