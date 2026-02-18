"""
Cost tracking for Azure AI services.

Tracks token usage and estimates costs for GPT-5-mini and Mistral OCR.

Usage:
    from src.utils.cost_tracker import CostTracker

    tracker = CostTracker()
    tracker.log_gpt_usage(prompt_tokens=5000, completion_tokens=500, model="gpt-5-mini")
    tracker.log_mistral_ocr(pages=10)
    tracker.print_summary()
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# Pricing per 1M tokens (as of Feb 2026)
PRICING = {
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-4.1-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "mistral-document-ai-2505": {"per_page": 0.002},  # Estimated
}


@dataclass
class UsageRecord:
    """Single usage record."""
    timestamp: str
    service: str  # "gpt" or "mistral_ocr"
    model: str
    pdf_name: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    pages: int = 0
    estimated_cost: float = 0.0


@dataclass
class CostTracker:
    """Tracks costs for Azure AI services."""

    records: list = field(default_factory=list)
    session_start: str = field(default_factory=lambda: datetime.now().isoformat())

    def log_gpt_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "gpt-5-mini",
        pdf_name: Optional[str] = None,
    ) -> float:
        """
        Log GPT usage and return estimated cost.

        Args:
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            model: Model name
            pdf_name: Optional PDF filename for tracking

        Returns:
            Estimated cost in USD
        """
        total_tokens = prompt_tokens + completion_tokens

        # Calculate cost
        pricing = PRICING.get(model, PRICING["gpt-5-mini"])
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost

        record = UsageRecord(
            timestamp=datetime.now().isoformat(),
            service="gpt",
            model=model,
            pdf_name=pdf_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=total_cost,
        )
        self.records.append(record)

        logger.info(
            f"GPT usage: {total_tokens:,} tokens "
            f"({prompt_tokens:,} in, {completion_tokens:,} out) "
            f"= ${total_cost:.6f}"
        )

        return total_cost

    def log_mistral_ocr(
        self,
        pages: int = 1,
        pdf_name: Optional[str] = None,
    ) -> float:
        """
        Log Mistral OCR usage and return estimated cost.

        Args:
            pages: Number of pages processed
            pdf_name: Optional PDF filename for tracking

        Returns:
            Estimated cost in USD
        """
        pricing = PRICING["mistral-document-ai-2505"]
        total_cost = pages * pricing["per_page"]

        record = UsageRecord(
            timestamp=datetime.now().isoformat(),
            service="mistral_ocr",
            model="mistral-document-ai-2505",
            pdf_name=pdf_name,
            pages=pages,
            estimated_cost=total_cost,
        )
        self.records.append(record)

        logger.info(f"Mistral OCR usage: {pages} pages = ${total_cost:.6f}")

        return total_cost

    def get_session_totals(self) -> dict:
        """Get totals for the current session."""
        gpt_records = [r for r in self.records if r.service == "gpt"]
        ocr_records = [r for r in self.records if r.service == "mistral_ocr"]

        return {
            "session_start": self.session_start,
            "gpt": {
                "requests": len(gpt_records),
                "total_tokens": sum(r.total_tokens for r in gpt_records),
                "prompt_tokens": sum(r.prompt_tokens for r in gpt_records),
                "completion_tokens": sum(r.completion_tokens for r in gpt_records),
                "cost": sum(r.estimated_cost for r in gpt_records),
            },
            "mistral_ocr": {
                "requests": len(ocr_records),
                "total_pages": sum(r.pages for r in ocr_records),
                "cost": sum(r.estimated_cost for r in ocr_records),
            },
            "total_cost": sum(r.estimated_cost for r in self.records),
            "pdfs_processed": len(set(r.pdf_name for r in self.records if r.pdf_name)),
        }

    def print_summary(self):
        """Print a summary of usage and costs."""
        totals = self.get_session_totals()

        print("\n" + "=" * 50)
        print("COST TRACKING SUMMARY")
        print("=" * 50)
        print(f"Session started: {totals['session_start']}")
        print(f"PDFs processed: {totals['pdfs_processed']}")

        print(f"\nGPT-5-mini:")
        print(f"  Requests: {totals['gpt']['requests']}")
        print(f"  Tokens: {totals['gpt']['total_tokens']:,}")
        print(f"  Cost: ${totals['gpt']['cost']:.4f}")

        print(f"\nMistral OCR:")
        print(f"  Requests: {totals['mistral_ocr']['requests']}")
        print(f"  Pages: {totals['mistral_ocr']['total_pages']}")
        print(f"  Cost: ${totals['mistral_ocr']['cost']:.4f}")

        print(f"\nTOTAL COST: ${totals['total_cost']:.4f}")
        print("=" * 50)

    def save_to_file(self, filepath: Optional[str] = None):
        """Save usage records to a JSON file."""
        if filepath is None:
            filepath = Path("data") / "cost_tracking" / f"usage_{datetime.now().strftime('%Y%m%d')}.json"

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "session_start": self.session_start,
            "records": [asdict(r) for r in self.records],
            "totals": self.get_session_totals(),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved cost tracking to {filepath}")


# Global tracker instance
_tracker: Optional[CostTracker] = None


def get_tracker() -> CostTracker:
    """Get the global cost tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


def reset_tracker():
    """Reset the global cost tracker."""
    global _tracker
    _tracker = CostTracker()


if __name__ == "__main__":
    # Demo
    tracker = CostTracker()

    # Simulate some usage
    tracker.log_mistral_ocr(pages=10, pdf_name="CScott.pdf")
    tracker.log_gpt_usage(
        prompt_tokens=10000,
        completion_tokens=500,
        model="gpt-5-mini",
        pdf_name="CScott.pdf"
    )

    tracker.log_mistral_ocr(pages=12, pdf_name="JCruz.pdf")
    tracker.log_gpt_usage(
        prompt_tokens=12000,
        completion_tokens=600,
        model="gpt-5-mini",
        pdf_name="JCruz.pdf"
    )

    tracker.print_summary()
