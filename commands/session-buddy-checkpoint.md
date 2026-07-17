______________________________________________________________________

argument-hint:

- checkpoint-name
  description: Create a session checkpoint with progress summary
  id: 01K6GZZRTDXPTKXJ5YMF07CK2H

______________________________________________________________________

Use the `mcp__session-buddy__checkpoint` tool to create a session checkpoint.

This command will:

1. Create a checkpoint of the current development session
1. Analyze code quality and calculate quality scores
1. Summarize progress made so far
1. Document any pending tasks or context
1. Prepare for seamless session resumption

The tool will analyze the working directory and provide comprehensive quality metrics.

## Notes-as-Memory Format

When creating checkpoint summaries, use structured notes instead of full conversation replay. This reduces token usage by ~90% while preserving essential context:

```markdown
## Checkpoint Notes

- **Decision**: [What was decided and which option was chosen]
- **Reason**: [Why — the constraint, tradeoff, or requirement that drove the choice]
- **Files changed**: [exact/path/to/file.py (created|modified), ...]
- **Next step**: [The single next action after this checkpoint]
- **Blockers**: [None | description of what is blocking progress]
```

Do not replay the full conversation. Do not summarize what was discussed. Only record decisions, reasons, files, and next steps.
