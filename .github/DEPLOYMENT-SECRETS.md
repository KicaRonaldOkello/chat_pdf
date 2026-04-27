# GitHub: variables and secrets for `deploy.yml`

## One-time: bootstrap

The deploy role (OIDC) is created by Terraform. Run a **first** `terraform apply` with local or console credentials so `github_actions_role_arn` exists, then set repository secret `AWS_DEPLOY_ROLE_ARN` to that value. The GitHub workflow cannot assume a role that does not exist yet.

## Checklist (Repository secrets + variables)

Use this as a checklist when wiring **Repository secrets** and **Repository variables** (or **Environments**).

## Required repository **secrets** (sensitive)

| Name | Used for |
|------|----------|
| `AWS_DEPLOY_ROLE_ARN` | IAM role ARN for OIDC (output `github_actions_role_arn` from Terraform, or your own role). |
| `CLERK_SECRET_KEY` | Only if you add server routes that use Clerk’s secret; current API uses JWKS + issuer only, so you may **omit** unless you extend. |
| `OPENROUTER_API_KEY` | Optional. Required only if the pipeline passes it into Terraform; otherwise set only in Terraform/SSM. |

> **Not** secrets, but people often add them for CI:

| Name | Note |
|------|------|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Public in the built Angular bundle; a **variable** is enough. Same value you use in `frontend/.env`. |
| `DATABASE_URL` | **Not** in GitHub if the DB is created by Terraform. The ECS task gets `DATABASE_URL` from Terraform (RDS + password in state). Run migrations in CI with the **same** DSN: build from `terraform output rds_address` + `rds_password` (use local script or a follow-up). |

**Recommended to keep in Terraform / AWS only (not in GitHub):** RDS password, long-lived AWS keys. This workflow uses **OIDC** so there are no static `AWS_ACCESS_KEY` secrets for deploy.

## Repository **variables** (non-secret; plain text)

| Name | Example | Purpose |
|------|----------|--------|
| `AWS_REGION` | `us-east-1` | Region for CLI + Terraform. |
| `TERRAFORM_STATE_BUCKET` | `my-corp-terraform-state` | Bootstrap + backend (must match `backend.hcl`) |
| `TF_STATE_KEY` | `chat-pdf/terraform.tfstate` | S3 key for this stack |
| `EXISTING_DOCS_S3_BUCKET` | `your-pdf-bucket` | **Existing** documents bucket name (read/write by the API) |
| `CLERK_JWKS_URL` | `https://&lt;instance&gt;.clerk.accounts.dev/.well-known/jwks.json` | Backend JWT verify |
| `CLERK_ISSUER` | `https://&lt;instance&gt;.clerk.accounts.dev` | Issuer claim |
| `CLERK_JWT_AUDIENCE` | *(empty or custom)* | If you set authorized parties in Clerk |
| `GITHUB_ORG` | `acme` | `github_owner` for Terraform OIDC trust |
| `GITHUB_REPO` | `chat_pdf` | `github_repo` (repo name only) |
| `CORS_EXTRA_ORIGINS` | `https://custom.example.com` | Comma list *in addition* to the CloudFront URL (usually empty) |

**Optional** variable: `OPENROUTER_API_KEY` is better as a **secret**; if set as a variable, avoid if it must stay private.

## Values produced by Terraform (no GitHub storage needed for day-to-day)

After `apply` with `create_backend = true`:

- `url` — site URL: `https://&lt;cloudfront&gt;`
- `s3_frontend_bucket` — for `aws s3 sync` of the Angular `dist/`
- `ecr_repository_url` — for `docker tag/push`
- `github_actions_role_arn` — set once as `AWS_DEPLOY_ROLE_ARN`
- `rds_address`, `rds_port`, `db_name` + `rds_password` (sensitive output) — for ad-hoc migrations

## External (Clerk dashboard, not GitHub)

For each deployment URL:

- Add **Sign-in** / **Redirect** URLs: `https://&lt;cloudfront-domain&gt;/*` (and paths Clerk lists).
- Allowed **origins** for your Clerk + SPA setup as in Clerk’s docs.
- The **backend** only needs `CLERK_JWKS_URL` and `CLERK_ISSUER` in Terraform/ECS (or GitHub **variables** passed into `terraform plan` as `TF_VAR_…`).

## Summary

- **Store as secrets:** deploy role ARN (if you treat it as such), any third-party API keys you pass through CI, optional Clerk secret for future features.
- **Store as variables:** public Clerk key, `AWS_REGION`, state bucket names, `EXISTING_DOCS_S3_BUCKET`, `CLERK_JWKS_URL`, `CLERK_ISSUER`, GitHub org/repo for OIDC.
- **Do not** duplicate the RDS password in GitHub if Terraform and one-off `terraform output` are your source of truth; use **migrations** job with outputs or `aws ecs run-task` and the same DSN the task uses.
