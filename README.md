<p align="center">
  <a href="https://github.com/lupaxa-git-hooks-toolbox">
    <img src="https://raw.githubusercontent.com/the-lupaxa-project/brand-assets/master/logos/organisations/git-hooks-toolbox/readme-logo.png" alt="Git Hooks Toolbox" />
  </a>
</p>

<h1 align="center">Prompt Default Branch Commit</h1>

Ask before a commit on the default branch. The question is read from `/dev/tty`, so the [git hooks multiplexer](https://github.com/lupaxa-git-hooks-toolbox/git-hooks-multiplexer) can keep Git's stdin. With no terminal, the commit continues.

The protected branch is `master`. Set `REMOTE_LOOKUP` to `True` in `src/pre-commit` to use `origin`'s HEAD branch instead. A failed lookup still uses `master`.

## Install With Setup Git Hooks

[setup-git-hooks](https://github.com/lupaxa-git-hooks-toolbox/setup-git-hooks) fetches `src/pre-commit` from this repository. In the consuming repo, add an entry to `hooks/pre-commit-config.yml`:

```yaml
- name: Prompt default branch
  filename: prompt-default-branch
  url: https://github.com/lupaxa-git-hooks-toolbox/prompt-default-branch-commit
  version: HEAD
```

That installs `hooks/pre-commit/NN-prompt-default-branch`. The multiplexer must already be installed as `.git/hooks/pre-commit`.

> **Note:** `setup-hooks --force` overwrites the generated file. An edit to `REMOTE_LOOKUP` in `hooks/pre-commit/NN-*` does not survive that reinstall. Change the constant in this repository, then install again.

## Remote Lookup

`REMOTE_LOOKUP` defaults to `False`. `True` runs `git remote show origin` on every commit and protects the `HEAD branch` it prints. There is no separate config file for the flag.

## Development

These steps are only for changing this repository. Using the hook does not need a pip install.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install pytest ruff mypy bump-my-version
python -m pytest
```

<a href="https://github.com/the-lupaxa-project">
  <img src="https://raw.githubusercontent.com/the-lupaxa-project/brand-assets/master/logos/components/footer-for-child-orgs.svg" alt="The Lupaxa Project Footer" width="100%" />
</a>
