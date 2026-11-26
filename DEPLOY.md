# Deploying Hardware Hub

Two repositories, deployed in this order: **backend first, then frontend.** The guide pages and the
sitemap call the backend while the frontend builds and runs, so it has to exist first.

## 0. Before anything else

- **Make a new admin secret.** Do not reuse one that was ever pasted into a chat or a document:
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Choose a new `ADMIN_ID` too.
  The backend refuses to start if the secret is shorter than 16 characters.
- **If your database is on Neon, make a branch first.** A Neon branch is a copy that takes seconds and costs nothing
  to create. Use it for two things: to **rehearse** the schema change below before it touches the main branch,
  and as the **test database** (`TEST_DATABASE_URL`) so the tests never need your real data. Nothing in this
  project deletes data, but a branch is the cheapest insurance there is.

## 1. Backend

Set these on your host:

| Variable                   | Value                                                                                                                         |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`             | the production database URL                                                                                                   |
| `CORS_ORIGIN`              | the frontend's public address, for example `https://yourapp.vercel.app` (several allowed, comma-separated, no trailing slash) |
| `ADMIN_ID`, `ADMIN_SECRET` | the new values from step 0                                                                                                    |

Then bring the database up to date. It only **adds** tables, columns, indexes and slugs; it never drops or deletes:

```powershell
# from backend/, with DATABASE_URL pointing at the production database
python -m app.db.sync_schema
```

or open `sync_schema.sql` in the Neon SQL editor and run it (read it first; every statement is `IF NOT EXISTS`).
The output should say which columns and indexes it added and how many guides got slugs. Running it a second time must say "none".

If the guides are not in the database yet: `python -m app.db.seed` (skips titles that exist), or paste them in the admin panel.

Deploy the backend. Then check it from your own machine:

```powershell
python scripts/smoke_check.py --api https://your-backend.example.com
```

Every line must say PASS. A FAIL line says what to fix.

## 2. Frontend

Set on your host (Vercel: Project Settings, Environment Variables):

| Variable               | Value                                                               |
| ---------------------- | ------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL`  | the backend's public address                                        |
| `NEXT_PUBLIC_SITE_URL` | the frontend's own public address (without it the sitemap is empty) |

Deploy. The build downloads Google fonts, so it needs internet access. Then check everything together:

```powershell
python scripts/smoke_check.py --api https://your-backend.example.com --site https://yourapp.vercel.app
```

It also checks that the browser on your site is allowed by CORS, the pages and the guide pages load, an unknown
guide gives a 404, `sitemap.xml` lists the guides with your real address, and `robots.txt` blocks `/admin`.

## 3. Things to look at yourself (a script cannot judge these)

1. Open the site **on a phone**. The home page, a guide page, and the chat. Open the chat, go to a "needs a professional"
   answer (the guide _No power / PC will not turn on_: "Yes, completely nothing", then "Yes, all of that looks correct"),
   tap **Prepare a summary for a technician**, and tap into the device box. Check **Copy summary** is still visible when the
   keyboard is open.
2. Log in at `/admin/login`. Send the chat a nonsense message, for example `zzqx flurble wombat`, then check it
   appears under **Missed queries**, and dismiss it.
3. Open **Catalog**: every product photo shows the right product, and each "Check price" link opens an Indian store.
   A wrong photo is worse than "No photo yet".
4. Switch to dark mode, reload, and check it stays dark.
5. Vote "Yes" or "Not really" on a few final answers. The "X of Y said this fixed it" line appears only after 5 votes on the same answer.

## 4. After the deploy

- Submit `https://yourapp.vercel.app/sitemap.xml` in Google Search Console if you want the guides found by search.
- Keep the smoke check: run it again after any deploy.
- To change the schema later: edit the model, run `python -m app.db.sync_schema` (rehearse on a branch first), and regenerate
  the diagram and SQL (`python -m app.db.erd`, `python -m app.db.sync_schema --print-sql`; a test fails until you do).

## If something goes wrong

| Symptom                                                                            | Likely cause                                                                                     |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| The backend will not start and mentions `ADMIN_SECRET`                             | the secret is shorter than 16 characters                                                         |
| The website shows no guides, or the smoke check fails "every guide has a URL slug" | `sync_schema` has not been run on this database                                                  |
| Browser console says a request was blocked by CORS                                 | the frontend's exact address is missing from `CORS_ORIGIN` (check `https` and no trailing slash) |
| `sitemap.xml` is empty                                                             | `NEXT_PUBLIC_SITE_URL` is not set on the frontend                                                |
| `sitemap.xml` shows `localhost`                                                    | `NEXT_PUBLIC_SITE_URL` is set to a local address                                                 |
| Guide pages say "Guide not found" for every guide                                  | the frontend cannot reach the backend: check `NEXT_PUBLIC_API_URL` and that the backend is up    |
| The frontend build fails on fonts                                                  | the build machine has no internet access                                                         |
