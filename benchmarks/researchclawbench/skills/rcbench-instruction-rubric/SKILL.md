---
name: rcbench-instruction-rubric
description: Extract instruction requirements and discriminative retrieval anchors for a ResearchClawBench task before literature or data analysis. Use to establish the original task contract and prevent later planning from omitting requested evidence.
---

# ResearchClawBench Instruction Contract

Read only `INSTRUCTIONS.md` for scientific content. Do not inspect related work, web sources, or data contents at this stage. Never read hidden checklists, `target_study` material, other tasks' runs, or judge feedback, regardless of location.

Write `outputs/initial_rubric.json` using [../rcbench-workflow-controller/references/contracts.md](../rcbench-workflow-controller/references/contracts.md).

- Give each scientific goal a stable `G` ID and each explicit requirement a stable `I` ID; link requirements to goals.
- Preserve every stated input, output, method, baseline, metric, condition, numerical setting, and deliverable. Keep condition-specific comparisons distinct when pooling would lose the question.
- Preserve exact names, unusual phrases, numbers, conditions, and requested artifact forms in `retrieval_anchors`. Search clues do not authorize inventing paper-specific requirements.
- Put unstated protocol details in `unresolved_requirements`. Do not guess methods, labels, outcomes, papers, or figures.
- Use as many goals and requirements as the instruction needs. Deduplicate without erasing experimental distinctions.

Reread the raw instruction before finishing. Every experimentally meaningful comparison, method, numerical setting, input, and output must survive. This is a task contract, not an experiment plan or an expected answer.
