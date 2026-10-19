"""Example questions shown at the start of a chat, in the terminal and in the UI.

They exercise every record system with identifiers that exist in the export.
"""

EXAMPLE_QUESTIONS: list[str] = [
    "Who is customer CIF-1004823 and which accounts do they hold?",
    "List the screening hits for CIF-6244597, including any without a disposition.",
    "What prior cases does CIF-1004823 have in Castellan, and is any RFI still open?",
    "What documents are on file for review VGB-PR-2026-0041?",
    "Read 1004823_employment_letter_1.txt and tell me who issued it and when.",
    "List the credits on account 5583716687 in 2025 above 5,000.",
    "Compare the beneficial owners on record for CIF-3098094 with the ACRA extract on file.",
]
