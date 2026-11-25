# DEEPFAKE SENTINEL REST API

## Status of this document

This document describes the live API mounted at `/api/` by `config/api_router.py` and included from `config/urls.py`. There is no `/api/v1/` prefix and there are no `/health/` or `/ready/` API routes. Container health checks are transport-level checks described in `docs/deployment.md`.

## Base conventions

- Base URL: `/api/`
- Formats: JSON for request and response bodies, except uploads (`multipart/form-data`) and file downloads (binary).
- Authentication:
  - Browser clients use Django session authentication with CSRF protection on unsafe methods.
  - API clients use DRF token authentication: `Authorization: Token <token>`.
  - `POST /api/auth/register/` and `POST /api/auth/login/` return a token as both `token` and `key`.
- Authorization: most endpoints require authentication; user and activity routes require staff/admin access.
- IDs: media, investigations, and report IDs are UUIDs; users and analysis records use integer IDs.
- Timestamps: ISO 8601 strings.
- Pagination: DRF page-number pagination on list endpoints. Responses contain `count`, `next`, `previous`, and `results`; use `?page=<n>` to change pages. The default page size is `API_PAGE_SIZE` (20).
- Uploads: send one or more files as `files` (repeatable) or `file`. The backend accepts the first uploaded file set it finds.
- Idempotency: there is no `Idempotency-Key` support.

## Error format

Errors use DRF response bodies, not a custom `error.code` envelope.

Validation failure example:

```json
{
  "files": [
    {
      "file": "frame.png",
      "error": "Unsupported media type."
    }
  ]
}
```

Common responses:

| Status | Meaning |
| --- | --- |
| `400` | Invalid request body, query parameter, or upload. |
| `401` | Authentication credentials were not provided or are invalid. |
| `403` | Authenticated user lacks access to the object or route. |
| `404` | Resource is missing, hidden by permissions, or the stored file is unavailable. |
| `413` | Upload exceeds the configured size limit. |
| `500` | Unexpected server or worker failure. |

## Result vocabulary

| Field/value | Meaning |
| --- | --- |
| `verdict: INCONCLUSIVE` | No supported verdict is available. This is used when no trained checkpoint is configured. |
| `verdict: LIKELY_MANIPULATED` | Stored signals support a manipulation finding. |
| `verdict: LIKELY_AUTHENTIC` | Stored signals support an authenticity finding. |
| `confidence: null` | No numeric confidence is available. Missing checkpoints produce no confidence value. |
| `model_status` | Records whether a trained checkpoint was applied for that analysis record. |

Heuristic indicators, metadata anomalies, and forensic risk levels are observations, not proof. Dashboard metrics are computed from stored records and must not be presented as model accuracy or validation results.

---

## API root and browsable API

### `GET /api/`

Public browsable API root listing available routes.

### `/api/api-auth/`

DRF browsable API login/logout support.

---

## Authentication

### `POST /api/auth/register/`

Creates a user and token. Public.

```json
{
  "username": "analyst",
  "email": "analyst@example.com",
  "password": "a-strong-password",
  "password2": "a-strong-password",
  "role": "investigator"
}
```

The response includes `id`, `username`, `email`, `role`, `user`, `profile`, `token`, and `key`.

### `POST /api/auth/login/`

Authenticates a user and returns the current token. Public.

```json
{
  "username": "analyst",
  "password": "a-strong-password"
}
```

### `POST /api/auth/logout/`

Deletes the current user's token and returns `{"detail": "Successfully logged out."}`.

### `GET /api/auth/me/`

Returns the current user, profile, role, and staff/superuser flags.

---

## Accounts (admin only)

### `GET /api/accounts/users/`

Lists users. Supports `?search=<username-or-email>` and pagination.

### `GET|PATCH|PUT /api/accounts/users/{id}/`

Retrieves or updates a user. `PATCH` accepts a partial `UserAdminSerializer` body; `PUT` behaves as partial update. `DELETE` removes the user.

### `GET /api/accounts/activity/`

Lists activity log entries, newest first, with pagination.

---

## Media

### `GET /api/media/`

Lists media visible to the current user.

Query parameters:

| Parameter | Meaning |
| --- | --- |
| `status` | Media status, uppercased before filtering. |
| `media_type` | `IMAGE`, `VIDEO`, or `AUDIO`. |
| `investigation` | Investigation UUID. |
| `search` | Matches original filename or SHA-256. |
| `page` | Page number. |

Each item includes `id`, `owner`, `owner_username`, `investigation`, `investigation_title`, `download_url`, `original_name`, `media_type`, `mime_type`, `size_bytes`, `sha256`, `status`, `uploaded_at`, `updated_at`, `error_message`, and `events`. `download_url` points to the protected `GET /api/media/{id}/download/` endpoint (absolute when a request context is available, relative otherwise); raw storage fields and direct file URLs are not exposed.

### `POST /api/media/`

Uploads one or more files and queues `process_media` for each created media record.

Request: `multipart/form-data` with `files` (or `file`) and optional `investigation`.

```text
files=@frame.jpg
files=@clip.mp4
investigation=8d7c2e5f-...
```

Response `201 Created`:

```json
{
  "created": [
    {
      "id": "1f0b...",
      "original_name": "frame.jpg",
      "media_type": "IMAGE",
      "sha256": "9f2c...",
      "status": "PENDING"
    }
  ],
  "count": 1
}
```

If some uploads fail, the response also includes `errors`. If all fail, the request returns `400` with the same error list. A successful upload writes an `AnalysisEvent` with `stage: "pipeline"` and `status: "QUEUED"` containing the Celery task ID.

### `GET /api/media/{id}/`

Returns one media record with its analysis events and writes an `EVIDENCE_ACCESS_LOG` row with action `VIEW`.

### `GET /api/media/{id}/download/`

Streams the original file as an attachment and writes an `EVIDENCE_ACCESS_LOG` row with action `DOWNLOAD`.

### `GET /api/media/{id}/status/`

Returns `id`, `status`, `sha256`, `error_message`, and `updated_at`.

### `POST /api/media/{id}/reprocess/`

Resets media to `PENDING`, clears `error_message`, writes a `QUEUED` pipeline event, queues `process_media`, and returns `202 Accepted` with status fields, `detail`, and `task`.

### `GET /api/media/{id}/history/`

Returns paginated `AnalysisEvent` records ordered oldest first. Each event has `id`, `stage`, `status`, `message`, and `created_at`.

---

## Investigations

### `GET /api/investigations/`

Lists visible cases.

Query parameters:

| Parameter | Meaning |
| --- | --- |
| `status` | `OPEN`, `IN_PROGRESS`, `CLOSED`, or `ARCHIVED`. |
| `priority` | Case priority, uppercased before filtering. |
| `search` | Matches title, `case_id`, assignee username, or assignee email. |
| `page` | Page number. |

### `POST /api/investigations/`

Creates a case and writes a `TIMELINE_EVENT` for creation. The creator is taken from the authenticated user. `case_id`, `status`, `priority`, title, description, assignee, and linked media are handled by `InvestigationSerializer`. Use `assigned_to` for the assignee (a user ID or username); `assignee` is accepted as an alias. Priorities are `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`; lowercase input is normalized and legacy `normal` maps to `MEDIUM`. Linked media must be visible to the current user.

### `GET /api/investigations/{id}/`

Returns one case with creator, assignee, linked media, the 10 most recent `observations`, and the 10 most recent `access_history` records for linked media.

### `PATCH /api/investigations/{id}/`

Partially updates a case. Changing `status` writes a timeline event describing the old and new status.

### `POST /api/investigations/{id}/observations/`

Adds an observation authored by the current user and writes a timeline event.

### `GET /api/investigations/{id}/timeline/`

Returns paginated timeline events ordered oldest first.

### `GET /api/investigations/{id}/summary/`

Returns case details plus `media_count`, `observation_count`, `timeline_event_count`, `evidence_access_count`, `media_by_type`, `media_by_status`, `recent_events`, and `recent_observations`.

---

## Modality analyses

These endpoints return the analysis record for a media artifact. They do not start jobs; uploading or reprocessing media starts processing.

### `GET /api/analyses/image/{media_id}/`

Returns the image analysis record with `model_version`, `model_status`, `verdict`, `confidence`, `indicators`, `face_count`, `artifact_score`, `created_at`, and `updated_at`.

### `GET /api/analyses/video/{media_id}/`

Returns the video analysis record with model fields plus `frame_count`, `sampled_frames`, `suspicious_frames`, and `temporal_consistency`.

### `GET /api/analyses/audio/{media_id}/`

Returns the audio analysis record with model fields plus `duration_seconds`, `sample_rate`, `waveform_path`, `spectrogram_path`, `features`, and `suspicious_segments`.

---

## Evidence endpoints

### `GET /api/forensics/{media_id}/`

Returns the forensic record with `summary`, `anomalies`, `evidence`, `risk_level`, and `created_at`.

### `GET /api/metadata/{media_id}/`

Returns the metadata record with `raw`, `exif`, `technical`, `anomalies`, and `created_at`.

### `GET /api/integrity/{media_id}/`

Returns the integrity record with `original_hash`, `current_hash`, `status`, and `verified_at`.

### `GET /api/explanations/{media_id}/`

Returns the explanation record with `summary`, `indicators`, `recommendations`, `limitations`, `evidence_source`, and `created_at`.

---

## Reports

### `GET /api/reports/`

Lists reports visible to the current user, newest first.

Query parameters:

| Parameter | Meaning |
| --- | --- |
| `search` | Matches `report_id`, media filename, media SHA-256, investigation `case_id`, investigation title, or generator username. |
| `page` | Page number. |

There is no report `status` field or filter, and no CSV or JSON format filter.

Each item includes `id`, `report_id`, `media`, `media_id`, `media_name`, `investigation`, `investigation_id`, `generated_by`, `generated_by_username`, `download_url`, `version`, `sha256`, `hash_chain`, and `created_at`.

### `POST /api/reports/`

Creates a PDF report from stored evidence.

```json
{
  "media": "1f0b8c2e-..."
}
```

### `POST /api/reports/generate/{media_id}/`

Creates a PDF report for the given media artifact without a request body. This is the shortcut used by the workspace UI.

### `GET /api/reports/{id}/`

Returns one report record, including an absolute `download_url`.

### `GET /api/reports/{id}/download/`

Streams the generated PDF as an attachment with `Content-Type: application/pdf` and filename `<report_id>.pdf`.

Browser clients should include CSRF protection and session credentials. Token clients should send:

```text
Authorization: Token <token>
Accept: application/pdf
```

A missing, inaccessible, or file-less report returns `404` with a `detail` message. The protected frontend download URL pattern is `/api/reports/{id}/download/`.

---

## Dashboard

### `GET /api/analytics/dashboard/`

Returns metrics computed from stored records and scoped to the authenticated user's media and investigations. Privileged users see metrics across all records:

```json
{
  "total_media": 12,
  "analyses": 0,
  "open_cases": 0,
  "reports": 0,
  "media_counts": {
    "IMAGE": 5,
    "VIDEO": 4,
    "AUDIO": 3,
    "UNKNOWN": 0
  },
  "potentially_manipulated": 2,
  "status_counts": {},
  "confidence_distribution": {},
  "recent_investigations": [],
  "detection_history": [],
  "model_metrics": []
}
```

In the example, `analyses`, `open_cases`, and `reports` are placeholder `0` values; live responses return integer counts. `analyses` counts analysis records for scoped media, `open_cases` counts scoped investigations whose status is not `CLOSED` or `RESOLVED`, and `reports` counts reports from `report_queryset_for_user`.

`model_metrics` contains `ModelMetric` records created from local training or evaluation runs. The application does not fabricate accuracy, precision, recall, or F1 values.
