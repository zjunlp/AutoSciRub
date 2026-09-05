# Minimal research task

Run `python scripts/autoscirub.py demo --project ./autoscirub-demo` from the
AutoSciRub checkout for a deterministic offline retrieval check. The destination
must be empty. This does not run a model or validate scientific reasoning.

Then open your agent in the demo directory and ask it to complete INSTRUCTIONS.md
with AutoSciRub. Expected numerical checks: control mean 13, treatment mean 17,
and difference 4. Reports and rubric wording may vary by agent. An agent/model
account is needed only for this second step. No literature API key is needed.
