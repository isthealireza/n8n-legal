# After you buy n8n: six steps

Do these in order. Nothing here asks you to paste a key into a chat, a
document, or a file in this repository.

**1. Purchase the n8n Starter plan.**

**2. Create an n8n API key** in n8n: Settings → n8n API → Create an API key.
Copy it once — n8n will not show it again.

**3. Add `N8N_BASE_URL` as a repository *variable*.**
GitHub → this repo → Settings → Secrets and variables → Actions → *Variables*
tab → New repository variable. Name it `N8N_BASE_URL`; the value is your
instance's root URL, with no `/api/v1` on the end.

**4. Add `N8N_API_KEY` as a repository *secret*.**
Same page, *Secrets* tab → New repository secret. Name it `N8N_API_KEY` and
paste the key from step 2. A secret, not a variable — GitHub masks secrets in
logs and never shows them again after saving.

**5. Run the Action manually.**
GitHub → Actions → "n8n sync (read-only)" → Run workflow. It also runs on a
schedule every 15 minutes once configured.

**6. Review the generated draft-vs-active report and the pull request.**
The run pushes to the `n8n-sync` branch and opens (or updates) one PR into
`main`. Read `docs/drift-report.md` on that branch, then merge if it looks
right.

---

**The first authenticated sync is read-only against n8n.** It issues `GET`
requests and nothing else; it changes no workflow, publishes nothing,
activates nothing, and deletes nothing.

**GitHub never updates n8n.** Sync is one-way, n8n → GitHub. Merging the PR
changes this repository and has no effect whatsoever on your running workflows.
