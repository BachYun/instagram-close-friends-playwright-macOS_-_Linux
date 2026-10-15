# Publishing to GitHub

Publish this clean source folder, **not** the older working folder containing a real
Chrome profile, follower CSV, exports and progress history. Start with a private
repository, review its files, then deliberately change visibility if desired.

## 1. Install/test the clean source

From the extracted repository folder:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python close_friends_csv.py --version
.venv/bin/python -m pytest -q -m 'not browser'
.venv/bin/python scripts/check_publish.py
```

Do not continue after a failed command. Browser tests are optional locally and do not
need any Instagram account. See TESTING.md.

## 2. Authenticate GitHub CLI

For macOS with Homebrew already installed:

```bash
brew install gh
gh auth login --hostname github.com --git-protocol https --web --scopes workflow
gh auth setup-git
gh auth status
```

Verify the displayed GitHub account before creating the repo. Complete the browser
sign-in yourself. The `workflow` scope permits uploading the included Actions workflow.
Never copy GitHub tokens into the project or into a support conversation.

## 3. Initialize the repository and commit identity

```bash
git init -b main
git config user.name "$(gh api user --jq .login)"
```

In GitHub account Settings → Emails, copy your GitHub-provided `noreply` address. Replace
the placeholder below with that address. This avoids publishing a personal email in the
commit, and only changes Git configuration for this repository.

```bash
git config user.email "YOUR_GITHUB_NOREPLY_EMAIL"
```

## 4. Stage only reviewed public files

```bash
.venv/bin/python scripts/check_publish.py --stage
git diff --cached --stat
git diff --cached
```

`--stage` validates the working files, stages only `PUBLIC_FILES.txt`, and scans the actual
index. It does not commit or push. Press `q` to leave Git's diff viewer. Review the complete
diff, not only the file count. Only the exact synthetic example CSV belongs in this repo.

If the check fails, do not push. It checks the index, not history; deleting a leaked file
in a later commit does not remove earlier copies. `.gitignore` is not an eraser. Rotate
any actual exposed credentials before addressing Git history.

When satisfied:

```bash
git commit -m "Initial beta: no-reload Close Friends helper"
```

## 5. Create and upload

This creates a **private** repository under the GitHub account authenticated by `gh` and
pushes the commit:

```bash
gh repo create instagram-close-friends-playwright --private --source=. --remote=origin --push --description "Local Playwright Close Friends helper with CSV tracking, manual login and separate verification."
gh repo view --web
```

If that repository name already exists, do not force-push over it. Choose another name,
or deliberately connect the local repository to the correct existing empty repository.
Do not create a separate GitHub README/license/gitignore through the web UI: they are
already included locally.

GitHub's Actions tab should show the offline test workflow. CI is configured here, not
already verified on GitHub. The included Dependabot configuration may open dependency
update pull requests; it does not auto-merge them.

## 6. Public release, after review

To make the repository public, use repository Settings → General → Danger Zone →
Change repository visibility. Review the consequences before confirming. Keep real
account data local even when the repository is private.

After testing this exact build on an authorized account and reviewing CI, a beta release
can be created without uploading any runtime data:

```bash
gh release create v0.1.0-beta --prerelease --title "v0.1.0-beta" --notes-file docs/RELEASE_NOTES.md
```

This command creates a tag from the default branch if the tag does not exist. Do not call
the release production-ready unless the evidence supports that. Update the release notes
with the actual environment/date/results of any live validation; do not report unrun tests.

## Subsequent code changes

Update `PUBLIC_FILES.txt` deliberately when adding a public source or documentation file.
Never add runtime data to that manifest. Then:

```bash
.venv/bin/python -m pytest -q -m 'not browser'
.venv/bin/python scripts/check_publish.py --stage
git diff --cached
git commit -m "Describe the change"
git push
```

Primary instructions checked for this guide:
- https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github
- https://cli.github.com/manual/gh_repo_create
- https://cli.github.com/manual/gh_auth_login
- https://cli.github.com/manual/gh_auth_setup-git
- https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address
- https://docs.github.com/en/get-started/git-basics/ignoring-files
- https://cli.github.com/manual/gh_release_create
