"""
CAQH Data Summary Review Automation

AI-powered automation tool for reviewing CAQH PDF Data Summaries against
the CAQH Cheat Sheet validation rules.

Project Status: POC Development - Week 1
Last Updated: October 6, 2025
"""

__version__ = "0.1.0"
__author__ = "PBS Credentialing Team"

# Make submodules easily importable
# Note: Only import modules that are fully implemented
# from . import extraction  # TODO: Implement extraction module
# from . import validation  # Available
# from . import edge_cases  # TODO: Implement edge case handlers
from . import utils
from . import config
# from . import sharepoint  # TODO: Implement SharePoint integration
from . import models

__all__ = [
    # "extraction",
    # "validation",
    # "edge_cases",
    "utils",
    "config",
    # "sharepoint",
    "models",
]
