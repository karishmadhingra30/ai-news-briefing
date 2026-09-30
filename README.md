# AI News Briefing

Two daily AI briefings: one technical, one in plain English. Built for people who implement AI solutions and explain them to customers.

This repository is a reusable **agent skill/plugin**, with Python helpers. The host agent researches and writes; the code parses feeds, validates structured output, and renders email. There is no paid AI API dependency and no separate hosted server.

## What is included

- A configurable source list: official announcements, news, engineering sources, and public X discovery.
- Semantic ranking instructions with equal emphasis on implementation and customer-facing solutions engineering.
- Shared event IDs for both editions and sent-email coverage records for repeat detection.
- HTML/text email rendering, a fictional example, and behavioral tests.
- Cloud setup instructions and a daily schedule prompt.

## Try it without accounts or costs

Requires Python 3.11+; no dependencies to install.

```sh
python3 -m unittest discover -s tests -v
python3 skills/daily-briefing/scripts/briefing.py render --input examples/digest.json --out runs/preview
```

Open `runs/preview/technical.html` and `runs/preview/plain-english.html`. These are clearly labeled fictional examples. Nothing is sent.

To collect real candidates (outbound HTTPS required):

```sh
python3 skills/daily-briefing/scripts/briefing.py collect --hours 30 --out runs/candidates.json
```

Candidates still require agent research, date verification, grouping, and scoring. The collector is not itself an AI news classifier. Source failures are recorded in its output.

## Use with a cloud agent

See [Cloud setup](docs/CLOUD_SETUP.md) and the [schedule prompt](docs/SCHEDULE_PROMPT.md). Install this plugin through your workspace's supported plugin flow, or provide the skill package to a cloud task and verify its files/tools are accessible. A GitHub repository or local installation alone does not activate a cloud schedule.

Start in preview mode. Before enabling delivery, confirm that the cloud task can research, read its own sent briefing history, and send to your authorized address. The default template runs daily at 8 p.m. America/Los_Angeles, including weekends; email arrives after processing.

## Customize and share

Copy `skills/daily-briefing/references/preferences.example.json` to a private configuration location or save equivalent preferences in your cloud task. Edit sources and scoring criteria for your interests. Keep recipient addresses, credentials, and delivery history outside this repository.

Others can fork or download the package, use their own account and connections, and set their own schedule. Forking does not inherit the original user's email authorization, schedule, or usage allowance. No paid sources, paid model APIs, or hosting subscriptions are enabled by this package.

## Limits

Public X discovery is incomplete. RSS feeds can be short, blocked, or unavailable. Source-to-claim verification is performed by the agent; structural validation cannot establish truth. Sent-mail checks reduce duplicates but do not provide an atomic lock against simultaneous runs. Cloud tools and unattended email permissions vary by account and must be tested in the target environment.

Learn how the pieces work in [PROJECT_GUIDE.md](PROJECT_GUIDE.md).
