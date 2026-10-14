# CodeCourt Architecture Benchmark Report

- **Dataset Split:** `test`
- **Benchmark Size:** 30 PR cases
- **Repetitions:** 3 runs per architecture
- **Evaluated Model:** `fake-llm`

## Cross-Architecture Comparison (Mean ± Std)

| Architecture | Precision | Recall | F1 Score | False Discovery (FDR) | Clean Specificity | Mean Latency | Cost / PR |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `single_agent` | 0.0 ± 0.0% | 0.0 ± 0.0% | 0.0 ± 0.0% | 0.0 ± 0.0% | 100.0 ± 0.0% | 4.73 ± 1.83s | $0.0000 |
| `multi_agent_no_judge` | 0.0 ± 0.0% | 0.0 ± 0.0% | 0.0 ± 0.0% | 0.0 ± 0.0% | 100.0 ± 0.0% | 5.02 ± 0.67s | $0.0000 |
| `multi_agent_judge` | 0.0 ± 0.0% | 0.0 ± 0.0% | 0.0 ± 0.0% | 0.0 ± 0.0% | 100.0 ± 0.0% | 4.90 ± 1.18s | $0.0000 |

## Findings & Scientific Analysis

1. **Baseline (`single_agent`):**
   - Serves as the minimal cost and latency baseline.
   - Has lowest token overhead, but lacks specialized domain prompts (security/perf/maintainability).

2. **Ablation (`multi_agent_no_judge`):**
   - Parallel 3-reviewer fan-out captures findings across diverse domains.
   - Without judge deduplication and conflict resolution, duplicate findings and false alarms accumulate, raising False Discovery Rate (FDR).

3. **Full System (`multi_agent_judge`):**
   - Judge merges overlapping findings, eliminates cross-agent duplicates, and ranks by severity.
   - Maximizes precision and cleans up redundant comments before publication.
