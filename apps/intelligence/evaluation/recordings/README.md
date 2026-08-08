# Evaluation recordings

Empty on purpose. Recordings are real model responses to the cases in
`../cases.yaml`, and there is no honest way to produce one without calling a
model. A hand-written file here would let the evaluation suite pass against
answers no model ever gave.

Create them once you have an API key:

```bash
docker compose exec intelligence python -m intelligence.cli llm record \
  --provider anthropic \
  --output /app/evaluation/recordings/extract_problem_v1.json
```

Then replay them for free, forever:

```bash
docker compose exec intelligence python -m intelligence.cli llm evaluate --provider fixture
```

A replay run proves the plumbing works — schema validation, taxonomy mapping,
the scorer. It proves nothing about the model, because the answers are fixed.
Measuring the model means `--provider anthropic`, which costs roughly a cent for
the full case set.

Re-record whenever `PROMPT_VERSION` changes. The fixture provider refuses to
replay recordings made under a different prompt rather than reporting on a
prompt that is no longer in use.

**Commit the recordings you produce.** They are small, and having them in
history means a prompt or schema change can be replayed against exactly what the
model said before it — which is the regression signal §70 is asking for. A
recording is also a record of what was true at the time, which a re-run against
a newer model can never reconstruct.
