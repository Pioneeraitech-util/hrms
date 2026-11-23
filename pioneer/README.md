# Pioneer HR deployment

This branch (`pioneer-prod`) is our copy of Frappe HR, cut from upstream `version-16`.
It runs at **https://hr.pioneeraitech.com** on the Mumbai server and deploys from
Delivery hub (project `hrms`, Pipeline = stack, context `pioneer`).

| File | What it is |
|---|---|
| `docker-compose.yml` | The stack: MariaDB, Redis, web (gunicorn + nginx), websocket, workers, scheduler |
| `apps.json` | Apps baked into the image: ERPNext `version-16` (HRMS requires it) and this branch |

The rest of the deploy lives in the deployer repo, `servers/stacks/hrms-prod/deploy.sh`:
it builds the image from frappe_docker's `images/layered/Containerfile` with this
`apps.json`, creates the site on the first run, and runs `bench migrate` after that.

## Making changes

Commit to `pioneer-prod`, then run the pipeline in Delivery hub. Each new commit builds
a new image; database and uploaded files live in Docker volumes and are kept.

## Taking upstream fixes

```bash
git fetch https://github.com/frappe/hrms version-16
git merge FETCH_HEAD        # on pioneer-prod
```
