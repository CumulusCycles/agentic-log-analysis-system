# /done

After a PR is merged, clean up the local and remote branch.

## Steps
1. Check PR is merged: `gh pr view --json state`
2. If not yet merged, report status and stop
3. `git checkout main`
4. `git pull origin main`
5. Delete local branch: `git branch -d <branch>`
6. Delete remote branch: `git push origin --delete <branch>`
7. Confirm cleanup complete
