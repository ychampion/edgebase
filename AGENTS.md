# Edgebase Agent Instructions

Keep this file minimal. Do not add generated architecture summaries here.

Before broad code exploration, ask Edgebase for fresh structural context:

```bash
edgebase context "<task>" --budget 1200
```

Run the focused tests for files you change, then `python -m unittest` before claiming completion.
