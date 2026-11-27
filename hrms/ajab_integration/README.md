# Ajab integration (AI interviews)

This integration connects Frappe HR to Ajab, the AI interview platform, through Ajab's public API (`/api/v1`). HR stays the system of record. Ajab runs the interviews and sends the results back.

## Set up (once, as HR Manager or System Manager)

1. **Create the key in Ajab.** An Ajab organisation admin goes to **Settings → API Keys** and creates a key with the **Full access** preset. At minimum the key needs:
   - the ATS integration scopes;
   - `webhooks:manage`, so Ajab can push updates;
   - `members:sync`, for employee sync.
2. **Connect from HR.** Open **Ajab Integration Settings** in HR, click **Connect to Ajab**, and paste the Ajab API address and the key.
   - HR checks the key with `GET /me` and stores it encrypted.
   - If the key has `webhooks:manage`, HR also points Ajab's webhook at this site and stores the signing secret encrypted.
   - Ajab keeps **one webhook per organisation**, so connecting replaces any other webhook URL that organisation had.

## Day to day

| Where | Button | What happens |
|---|---|---|
| Job Opening | Ajab → Send to Ajab / Update in Ajab | Creates or updates the Ajab job (title, description as plain text, active if Open) |
| Job Applicant | Ajab → Schedule AI interview | Finds the Ajab candidate by email or creates it, then creates the interview. Ajab emails the link unless that preference is off. Sends the job first if needed. |
| Job Applicant | Ajab → Refresh from Ajab | Reads the status, plus scores once analysis is complete |
| Job Applicant | Ajab → Cancel AI interview | Cancels it in Ajab while the interview is still `created` |
| Employee | Ajab → Sync to Ajab | Creates or updates the Ajab team member (`empId` = Employee ID) with the role set in settings |
| Settings | Sync all employees | Same as Sync to Ajab, for every active employee, in the background |
| Settings | Disconnect | Deletes Ajab's webhook if it points here, then forgets the key and secret |

The results land on the Job Applicant's **AI Interview** tab: status, final/interview/resume scores, the AI recommendation and a summary. A timeline comment is added for each step.

## Webhook

- **Endpoint:** `POST /api/method/hrms.ajab_integration.api.webhook`. It is a guest endpoint, rate limited.
- **Signature:** the request must carry `x-ajab-signature: t=…,v1=…`, an HMAC-SHA256 of `t.body`, at most 5 minutes old. HR also checks that the organisation id matches.
- **Duplicates:** an event id is handled only once (kept for 7 days).
- **Event handling:**
  - `interview.started`, `interview.completed` and `interview.cancelled` update the status directly.
  - `interview.analysis.completed` queues a job that reads `GET /interviews/:id/results`. Payloads never carry scores.

## Code

- `api.py`: whitelisted methods and the webhook
- `client.py`: HTTP client with error messages HR users can read
- `setup.py`: custom fields, created on `after_migrate`
- Settings doctype: `hr/doctype/ajab_integration_settings`
- Form buttons: `public/js/ajab/`
- Tests: `test_ajab_integration.py`. Ajab is mocked. Run on a test site with `bench --site <test-site> run-tests --module hrms.ajab_integration.test_ajab_integration`.
