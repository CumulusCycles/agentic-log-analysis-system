# /done

After a PR is merged, clean up the local and remote branch and orphaned CI runs.

## Steps
1. Check PR is merged: `gh pr view --json state`
2. If not yet merged, report status and stop
3. `git checkout main`
4. `git pull origin main`
5. Delete local branch: `git branch -d <branch>`
6. Delete remote branch: `git push origin --delete <branch>`
7. Delete orphaned PR-time CI runs for the merged branch:
   ```bash
   # List run IDs for the merged feature branch (head_branch is stored on the
   # run, so this still works after the branch is deleted in step 6)
   gh run list --branch <branch> --limit 100 --json databaseId --jq '.[].databaseId' \
     | xargs -I{} gh run delete {}
   ```
   The post-merge runs on `main` are kept — they back the README badges. Only
   the feature-branch `pull_request` runs are removed.
8. Confirm cleanup complete
