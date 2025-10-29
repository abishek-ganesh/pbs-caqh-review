"""
Duplicate Detector Module

Implements 15-minute duplicate detection logic using user + filename matching.
Tracks submission history to prevent duplicate processing.

Business Rules (from GAMEPLAN.md):
- Duplicate = Same user + exact filename + within 15 minutes
- True duplicates usually 1-2 minutes apart (accidental double submissions)
- >15 minutes = treat as new submission (user may have made updates)
- Frequency: 1-2 duplicates per week per reviewer
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


class SubmissionRecord(BaseModel):
    """Record of a PDF submission"""
    user_name: str
    filename: str
    submission_time: datetime
    file_path: str
    file_size: int = 0
    file_hash: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class DuplicateDetectionResult(BaseModel):
    """Result of duplicate detection check"""
    is_duplicate: bool
    original_submission: Optional[SubmissionRecord] = None
    time_difference_minutes: Optional[float] = None
    message: str
    recommendation: str  # "reject_duplicate", "process_normally", "needs_review"


class DuplicateDetector:
    """
    Duplicate detector using 15-minute time window.

    Stores submission history in JSON file for persistence across sessions.
    """

    def __init__(self, history_file: str = "data/submission_history.json"):
        """
        Initialize duplicate detector.

        Args:
            history_file: Path to JSON file storing submission history
        """
        self.history_file = Path(history_file)
        self.history: List[SubmissionRecord] = []
        self._load_history()

    def _load_history(self) -> None:
        """Load submission history from JSON file"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    self.history = [
                        SubmissionRecord(
                            user_name=rec['user_name'],
                            filename=rec['filename'],
                            submission_time=datetime.fromisoformat(rec['submission_time']),
                            file_path=rec['file_path'],
                            file_size=rec.get('file_size', 0),
                            file_hash=rec.get('file_hash')
                        )
                        for rec in data
                    ]
            except Exception as e:
                print(f"Warning: Could not load submission history: {e}")
                self.history = []
        else:
            # Create parent directory if it doesn't exist
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            self.history = []

    def _save_history(self) -> None:
        """Save submission history to JSON file"""
        try:
            # Only keep last 30 days of history to prevent file from growing too large
            cutoff_date = datetime.now() - timedelta(days=30)
            self.history = [
                rec for rec in self.history
                if rec.submission_time > cutoff_date
            ]

            with open(self.history_file, 'w') as f:
                json.dump(
                    [rec.dict() for rec in self.history],
                    f,
                    indent=2,
                    default=str
                )
        except Exception as e:
            print(f"Warning: Could not save submission history: {e}")

    def check_for_duplicate(
        self,
        user_name: str,
        filename: str,
        file_path: str,
        time_window_minutes: int = 15
    ) -> DuplicateDetectionResult:
        """
        Check if submission is a duplicate within the time window.

        Args:
            user_name: Name of the user submitting the PDF
            filename: Exact filename of the PDF (case-sensitive)
            file_path: Full path to the PDF file
            time_window_minutes: Time window for duplicate detection (default 15)

        Returns:
            DuplicateDetectionResult with detection details and recommendation
        """
        current_time = datetime.now()

        # Look for matching submissions from same user with same filename
        for past_submission in reversed(self.history):  # Check most recent first
            # Must match user AND exact filename (case-sensitive)
            if (past_submission.user_name == user_name and
                past_submission.filename == filename):

                # Calculate time difference
                time_diff = current_time - past_submission.submission_time
                time_diff_minutes = time_diff.total_seconds() / 60

                # Check if within time window
                if time_diff_minutes <= time_window_minutes:
                    return DuplicateDetectionResult(
                        is_duplicate=True,
                        original_submission=past_submission,
                        time_difference_minutes=time_diff_minutes,
                        message=(
                            f"Duplicate submission detected: {filename} was submitted by {user_name} "
                            f"{time_diff_minutes:.1f} minutes ago (within {time_window_minutes}-minute window)"
                        ),
                        recommendation="reject_duplicate"
                    )
                else:
                    # Found matching submission but outside time window - treat as new
                    return DuplicateDetectionResult(
                        is_duplicate=False,
                        original_submission=past_submission,
                        time_difference_minutes=time_diff_minutes,
                        message=(
                            f"Previous submission found but {time_diff_minutes:.1f} minutes ago "
                            f"(outside {time_window_minutes}-minute window). Treating as new submission."
                        ),
                        recommendation="process_normally"
                    )

        # No matching submissions found
        return DuplicateDetectionResult(
            is_duplicate=False,
            original_submission=None,
            time_difference_minutes=None,
            message=f"No previous submission found for {filename} from {user_name}",
            recommendation="process_normally"
        )

    def record_submission(
        self,
        user_name: str,
        filename: str,
        file_path: str,
        file_size: Optional[int] = None,
        file_hash: Optional[str] = None
    ) -> None:
        """
        Record a new submission in the history.

        Args:
            user_name: Name of the user submitting the PDF
            filename: Exact filename of the PDF
            file_path: Full path to the PDF file
            file_size: File size in bytes (optional)
            file_hash: MD5/SHA hash of file content (optional)
        """
        # Get file size if not provided
        if file_size is None:
            try:
                file_size = os.path.getsize(file_path)
            except:
                file_size = 0

        record = SubmissionRecord(
            user_name=user_name,
            filename=filename,
            submission_time=datetime.now(),
            file_path=file_path,
            file_size=file_size,
            file_hash=file_hash
        )

        self.history.append(record)
        self._save_history()

    def get_user_history(
        self,
        user_name: str,
        days: int = 7
    ) -> List[SubmissionRecord]:
        """
        Get submission history for a specific user.

        Args:
            user_name: Name of the user
            days: Number of days to look back

        Returns:
            List of submission records for the user
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        return [
            rec for rec in self.history
            if rec.user_name == user_name and rec.submission_time > cutoff_date
        ]

    def get_recent_duplicates(self, days: int = 7) -> List[Dict]:
        """
        Get all duplicate submissions detected in the past N days.

        Args:
            days: Number of days to look back

        Returns:
            List of dictionaries with duplicate information
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        duplicates = []

        # Group submissions by user + filename
        grouped: Dict[str, List[SubmissionRecord]] = {}
        for rec in self.history:
            if rec.submission_time > cutoff_date:
                key = f"{rec.user_name}|{rec.filename}"
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(rec)

        # Find groups with multiple submissions
        for key, submissions in grouped.items():
            if len(submissions) > 1:
                # Sort by time
                submissions.sort(key=lambda x: x.submission_time)

                # Check for duplicates within time window
                for i in range(1, len(submissions)):
                    time_diff = submissions[i].submission_time - submissions[i-1].submission_time
                    time_diff_minutes = time_diff.total_seconds() / 60

                    if time_diff_minutes <= 15:
                        duplicates.append({
                            'user_name': submissions[i].user_name,
                            'filename': submissions[i].filename,
                            'first_submission': submissions[i-1].submission_time.isoformat(),
                            'duplicate_submission': submissions[i].submission_time.isoformat(),
                            'time_difference_minutes': time_diff_minutes
                        })

        return duplicates

    def clear_old_history(self, days: int = 30) -> int:
        """
        Clear submission history older than N days.

        Args:
            days: Number of days to keep

        Returns:
            Number of records removed
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        original_count = len(self.history)

        self.history = [
            rec for rec in self.history
            if rec.submission_time > cutoff_date
        ]

        removed_count = original_count - len(self.history)
        if removed_count > 0:
            self._save_history()

        return removed_count


# Singleton instance
_detector_instance: Optional[DuplicateDetector] = None


def get_duplicate_detector(history_file: str = "data/submission_history.json") -> DuplicateDetector:
    """
    Get singleton instance of DuplicateDetector.

    Args:
        history_file: Path to submission history file

    Returns:
        DuplicateDetector instance
    """
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = DuplicateDetector(history_file=history_file)
    return _detector_instance
