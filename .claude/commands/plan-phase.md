# Plan Phase Command

You are planning a new phase of work for this project. Follow these steps:

1. Read `.planning/roadmap.md` to understand the phases
2. Read `.planning/state.md` to understand current state
3. Identify which phase we're starting
4. Create a detailed plan with:
   - Clear goals for this phase
   - Specific tasks broken down into steps
   - Acceptance criteria
   - Estimated complexity (S/M/L for each task)
5. Save the plan to `.planning/phase-{N}/plan.md`
6. Update `.planning/state.md` with the new phase
7. Use TodoWrite to create tasks for this phase

For GOV2DB specifically, consider:
- Current DB quality issues that need investigation
- QA scan results to guide priorities
- Safety modes for testing (use --max-decisions 5)
- Hebrew text handling complexities
- Cloudflare bypass requirements (--no-headless)

Present the plan and wait for approval before starting implementation.