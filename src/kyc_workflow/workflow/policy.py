"""POL-042 v4.2 as code can use it.

The clause text is read from the data pack (`data/risk-rating-policy-v4.2.md`),
never paraphrased into code. What this module adds is the parts a check needs
as numbers and tables: the thresholds the policy states, Appendix B industry
baselines, Appendix C jurisdiction groups, and the two rules Compliance has
not settled, kept configurable with their defaults visible in the pack.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from kyc_workflow.config import PROJECT_ROOT

POLICY_PATH = PROJECT_ROOT / "data" / "risk-rating-policy-v4.2.md"


@dataclass(frozen=True)
class Rules:
    # Stated in the policy.
    turnover_tolerance: float = 2.0           # §4.7(b): actual > 200% of declared is an exception
    monthly_swing: float = 0.40               # §7.2(a): ±40% of the trailing monthly average
    swing_months: int = 3                     # §7.2(a): sustained over three or more months
    pass_through_business_days: int = 5       # §7.4(c)
    pass_through_match: float = 0.8           # share of a credit that must leave within the window
    strong_band: float = 0.85                 # §8.2
    possible_band: float = 0.60               # §8.2
    rfi_response_days: int = 30               # §4.8.2
    in_scope_tiers: tuple[int, ...] = (1, 2, 3)  # low and medium: CRR 1-2 (36 months) and CRR 3 (24 months)
    # Unsettled with Compliance; defaults flagged in the pack.
    document_validity_days: int = 90          # §5.4 states it for CRR 4 only; Nora applies it to every file
    document_rule_all_tiers: bool = True
    payslip_is_independent: bool = False      # QA accepts payslips; Nora and the PR-88214 overturn do not
    material_credit: float = 1_000.0          # smallest credit worth matching to a document
    pass_through_min_share: float = 0.5       # §7.4(c) is tested on credits of at least this share of the average monthly credits


@dataclass
class Baseline:
    ssic: str
    industry: str
    seasonality: str
    cash_band: tuple[float, float]
    geography: list[str]


# ISO 3166 alpha-2 codes used in the export, to the names Appendix C uses.
COUNTRY_NAMES: dict[str, str] = {
    "SG": "Singapore", "JP": "Japan", "KR": "Korea, Republic of", "AU": "Australia", "NZ": "New Zealand",
    "GB": "United Kingdom", "UK": "United Kingdom", "DE": "Germany", "FR": "France", "NL": "Netherlands",
    "CH": "Switzerland", "US": "United States", "CA": "Canada", "HK": "Hong Kong SAR", "TW": "Taiwan",
    "MY": "Malaysia", "TH": "Thailand", "ID": "Indonesia", "VN": "Vietnam", "PH": "Philippines", "CN": "China",
    "IN": "India", "AE": "United Arab Emirates", "SA": "Saudi Arabia", "TR": "Turkiye", "BR": "Brazil",
    "MX": "Mexico", "ZA": "South Africa", "MM": "Myanmar", "KH": "Cambodia", "LA": "Lao PDR",
    "KP": "Korea, Democratic People's Republic of", "IR": "Iran", "SY": "Syria", "AF": "Afghanistan",
    "YE": "Yemen", "SS": "South Sudan", "HT": "Haiti", "VG": "British Virgin Islands", "KY": "Cayman Islands",
    "BM": "Bermuda", "PA": "Panama", "LK": "Sri Lanka", "BD": "Bangladesh", "PK": "Pakistan", "NG": "Nigeria",
    "RU": "Russia", "UA": "Ukraine", "IT": "Italy", "ES": "Spain", "SE": "Sweden", "IE": "Ireland", "LU": "Luxembourg",
}


@dataclass
class Policy:
    text: str
    rules: Rules
    clause_titles: dict[str, str]
    baselines: dict[str, Baseline]
    groups: dict[str, int]  # jurisdiction name -> 1, 2, 3
    sections: dict[str, str] = field(default_factory=dict)  # "4.7" -> clause text

    # -- lookups --------------------------------------------------------------------

    def group_of(self, country_code: str) -> tuple[int, str, bool]:
        """(group, name, listed). Unlisted jurisdictions are Group 2 pending GFCC classification (Appendix C)."""
        code = (country_code or "").strip().upper()
        name = COUNTRY_NAMES.get(code, code or "unknown")
        if name in self.groups:
            return self.groups[name], name, True
        return 2, name, False

    def baseline_for(self, ssic: str | None) -> Baseline | None:
        return self.baselines.get((ssic or "").strip()) if ssic else None

    def band(self, score: float | None) -> str:
        if score is None:
            return "unknown"
        if score >= self.rules.strong_band:
            return "strong"
        if score >= self.rules.possible_band:
            return "possible"
        return "weak"

    def clause_text(self, clause: str) -> str:
        """The text of one numbered clause, e.g. '4.7' or '8.4', for prompts and the pack."""
        key = re.match(r"\d+\.\d+", clause)
        return self.sections.get(key.group(0), "") if key else ""

    def title(self, clause: str) -> str:
        key = re.match(r"\d+\.\d+", clause)
        return self.clause_titles.get(key.group(0), "") if key else ""


# -- parsing --------------------------------------------------------------------------

def _parse_table(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        if line.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


def _band(text: str) -> tuple[float, float]:
    m = re.search(r"(\d+)\s*-\s*(\d+)\s*per cent", text)
    return (float(m.group(1)) / 100, float(m.group(2)) / 100) if m else (0.0, 1.0)


def load_policy(path: Path = POLICY_PATH, rules: Rules | None = None) -> Policy:
    text = path.read_text(encoding="utf-8")
    titles: dict[str, str] = {}
    sections: dict[str, str] = {}
    for m in re.finditer(r"^\*\*(\d+\.\d+) ([^.*]+)\.\*\*(.*?)(?=^\*\*\d+\.\d+ |^## |\Z)", text, re.S | re.M):
        titles[m.group(1)] = m.group(2).strip()
        sections[m.group(1)] = (m.group(2).strip() + "." + m.group(3)).strip()

    baselines: dict[str, Baseline] = {}
    app_b = text.split("## Appendix B")[1].split("## Appendix C")[0] if "## Appendix B" in text else ""
    for row in _parse_table(app_b)[1:]:
        if len(row) >= 5 and row[0].isdigit():
            baselines[row[0]] = Baseline(ssic=row[0], industry=row[1], seasonality=row[2], cash_band=_band(row[3]),
                                         geography=[g.strip() for g in row[4].split(",")])

    groups: dict[str, int] = {}
    app_c = text.split("## Appendix C")[1].split("## Appendix D")[0] if "## Appendix C" in text else ""
    for row in _parse_table(app_c)[1:]:
        m = re.match(r"Group (\d)", row[0])
        if m and len(row) >= 2:
            names = re.split(r",\s*(?![A-Z][a-z]+ of|Democratic|Republic)", row[1])
            # "Korea, Republic of" and "Korea, Democratic People's Republic of" contain commas; stitch them back.
            fixed: list[str] = []
            for n in names:
                n = n.strip()
                if fixed and (n.startswith("Republic of") or n.startswith("Democratic")):
                    fixed[-1] = fixed[-1] + ", " + n
                else:
                    fixed.append(n)
            for name in fixed:
                groups[name] = int(m.group(1))

    return Policy(text=text, rules=rules or Rules(), clause_titles=titles, baselines=baselines, groups=groups,
                  sections=sections)
