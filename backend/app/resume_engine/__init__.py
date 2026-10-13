"""
VidyamargAI Offline High-Fidelity Resume Extraction Engine.
"""
from .resume_extract.pipeline import extract, process_document
from .resume_extract.application_mapping import map_result

__all__ = ["extract", "process_document", "map_result"]
