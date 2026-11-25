# Screenshot Capture Guide

## Purpose

This directory contains guidance for capturing real product screenshots and three **illustrative SVG preview assets**. The SVG files are wireframe-style documentation aids. They are not screenshots, not evidence of a running UI, and must never be presented as fabricated product captures.

## Illustrative assets

| File | What it represents |
| --- | --- |
| `landing-preview.svg` | Abstract layout of a landing page. |
| `dashboard-preview.svg` | Abstract dashboard layout with placeholder counters. |
| `report-preview.svg` | Abstract report layout with placeholder sections. |

Each SVG visibly states "Illustrative preview - not a product screenshot".

## Before capturing real screenshots

1. Run the application using the steps in [deployment.md](../deployment.md).
2. Apply migrations and create a test user.
3. Load the workspace pages and confirm all templates and static assets resolve.
4. Use a clean browser profile at a fixed viewport, for example 1440x900.
5. Use synthetic or fully authorized sample media only.
6. Remove real names, emails, case numbers, tokens, and file paths from the view.
7. Confirm that model results are labelled honestly; do not stage fake accuracy numbers.

## Capture targets

### Landing page

Target: `/`

Include:

- Product name and short description.
- Primary navigation.
- Sign-in entry point.
- Any visible honesty notice about inconclusive predictions.

Save as:

```text
docs/screenshots/landing.png
```

### Dashboard

Target: `/dashboard/`

Include:

- Open investigation count.
- Recent jobs table.
- Status badges showing queued, succeeded, failed, and inconclusive states.
- No claimed model performance metrics.

Save as:

```text
docs/screenshots/dashboard.png
```

### Report

Target: `/reports/` (report registry/list page). There is no HTML report-detail route. Report detail and PDF download are API-only via authenticated `GET /api/reports/{id}/` and `GET /api/reports/{id}/download/`.

Include:

- Report registry heading and description.
- Search/filter controls.
- Generated documents table with format, generated date, and PDF download action.
- No claimed model performance metrics.

Save as:

```text
docs/screenshots/report.png
```

## Browser capture commands

Using Chrome or Edge in headless mode:

```bash
chrome --headless --disable-gpu --window-size=1440,900 --screenshot=docs/screenshots/landing.png http://localhost/
chrome --headless --disable-gpu --window-size=1440,900 --screenshot=docs/screenshots/dashboard.png http://localhost/dashboard/
chrome --headless --disable-gpu --window-size=1440,900 --screenshot=docs/screenshots/report.png http://localhost/reports/
```

Replace commands with your browser's executable path as needed.

## PDF report capture

PDFs are available only through authenticated `GET /api/reports/{id}/download/`. If you capture a PDF first page instead, render it to PNG with an approved local tool, then store it as `report.png`. Do not edit the rendered image to change results.

## Naming and documentation

- Use lowercase filenames: `landing.png`, `dashboard.png`, `report.png`.
- Add a short caption when embedding screenshots in documentation.
- State the capture date and viewport in the caption if precision matters.
- Keep SVG previews clearly separate from real captures in Markdown tables.

## Privacy checklist

- No real faces without permission.
- No personal identifiers.
- No internal hostnames or IP addresses.
- No API tokens or session cookies.
- No proprietary dataset samples.
- No unredacted legal or HR case material.
