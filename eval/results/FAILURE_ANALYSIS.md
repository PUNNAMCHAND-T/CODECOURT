# CodeCourt Evaluation: Failure Analysis Report

- **Evaluated Cases Total:** 270
- **Identified Failures:** 189
- **Report Generated:** 2026-10-09T15:37:59.251982+00:00

## Failure Mode Taxonomy Breakdown

| Failure Mode | Count | % of Failures | Description |
| :--- | :---: | :---: | :--- |
| `missed_injected_bug` | 189 | 100.0% | False negative (missed defect) |

## Failures by Review Architecture

| Architecture | Failure Count | Share |
| :--- | :---: | :---: |
| `multi_agent_judge` | 63 | 33.3% |
| `multi_agent_no_judge` | 63 | 33.3% |
| `single_agent` | 63 | 33.3% |

## Failures by Bug Domain

| Category | Failure Count | Share |
| :--- | :---: | :---: |
| `security` | 63 | 33.3% |
| `performance` | 54 | 28.6% |
| `maintainability` | 45 | 23.8% |
| `correctness` | 27 | 14.3% |

## Key Architectural Takeaways

1. **Clean PR Resilience:** Strict grounding eliminates false alarms on safe code.
2. **Ablation Duplication:** `multi_agent_no_judge` suffers from duplicate noise when agents overlap.
3. **Judge Synthesis:** `multi_agent_judge` eliminates duplicate noise through deduplication.
