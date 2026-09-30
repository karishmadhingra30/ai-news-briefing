# Cloud setup

## Runtime and package

Use a cloud task in ChatGPT Work with web research and your authorized Gmail connection. Codex Remote controls a computer and is not this cloud execution mode. Cloud availability depends on your plan/workspace.

The package contains `.codex-plugin/plugin.json` and a `daily-briefing` skill. The supported plugin distribution path is described in [Build skills](https://learn.chatgpt.com/docs/build-skills). Install a reviewed release through the plugin controls available to your account. Do not assume that adding a GitHub link installs or synchronizes it. If installation is unavailable, use the skill and references as attached context and verify the cloud task can read them; scripts require an available Python environment.

## Verify before scheduling

1. Open a cloud task and make the package available. Confirm the loaded version is 0.1.0.
2. Connect Gmail in that cloud workspace. Confirm profile, search/read, and send tools are available. The history design needs read access to this workflow's own sent messages, so it is not a send-only integration.
3. Ask for a preview of both editions from the last 24 hours, with a source coverage report. Check claims, dates, and links.
4. Authorize the two editions to your own account, if not already authorized. Send a test pair, then verify them in Sent. Trigger recovery again: both existing edition subjects should cause delivery to be skipped.
5. Create one recurring **cloud** schedule using `SCHEDULE_PROMPT.md`, daily at 20:00 America/Los_Angeles. Verify the UI shows the timezone/cadence and cloud execution. Do not use a local desktop automation as a substitute.
6. Check the first scheduled run and its two delivery IDs. If an account policy requires interactive approval for every email, unattended delivery has not been established; report that limitation rather than claiming success.

## Durable history without a database

Each delivered email contains an `AI-BRIEFING-RECORD` footer. The next run searches only the workflow's sent emails, including those in Trash with `in:anywhere in:sent` and reads their records and source links. A cloud container may be replaced between runs, but Sent persists in the connected account. Preview emails do not count as coverage. Permanently deleting these emails also removes this history; this design does not provide an independent archive.

If one edition fails, the next attempt reconstructs the same events from the successful edition and sends only the missing edition. If a send result is ambiguous, check Sent before retrying. Never run concurrent instances: this design is best-effort idempotency, not a transactional send service.

If history access is unavailable, stop delivery and provide previews. Do not claim to have deduplicated against inaccessible history.

## Costs and secrets

The agent uses the host plan's allowance. The helper uses standard Python and public HTTPS feeds. No service purchase or external API billing is configured. Paid collection, model APIs, or hosting require separate explicit approval. Do not put OAuth tokens, passwords, or personal addresses in the repository or prompts intended for public sharing.

## Installation status

This file describes the setup process. It is not evidence that the plugin is installed in a cloud account, that email has been delivered, or that a schedule is active. Verify each in the actual target environment.
