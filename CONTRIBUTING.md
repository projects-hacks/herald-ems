# Team workflow (five people, one ZGX Nano, one Linux user)

We all SSH in as the same user (`hp18`), but everyone commits and pushes as **their own GitHub account**.

## 1–2. One command per person (terminal, own GitHub account)

We all SSH in as `hp18`, but each person has **their own SSH key and their own working copy**. Nothing is set globally.

```bash
~/Documents/team-last-minute/herald-ems/scripts/dev_git_setup.sh <handle> "<Full Name>" <your-github-email>
```

The script:
- creates `~/.ssh/id_ed25519_<handle>`;
- prints the public key for you to add at https://github.com/settings/ssh/new, then waits;
- checks that GitHub accepts it;
- clones into `~/work/<handle>/herald-ems`;
- sets repo-local `user.name`, `user.email`, and `core.sshCommand`, so that copy always commits and pushes as you.

Never run `git config --global user.*` or a global credential helper here.

Alternative with no key on the Nano: SSH agent forwarding from your laptop (`ForwardAgent yes` in your laptop's `~/.ssh/config`, plus `ssh-add`).

Everyone must be a collaborator on `projects-hacks/herald-ems`. The keys live under the shared login, so remove them from GitHub after the event.

## Shared secrets (Hugging Face token)

One file for the whole team, loaded by every `hp18` shell: `~/.config/herald/secrets.env` (mode 600, outside the repo). Fill in `HF_TOKEN` and `HF_REPO_ID`, then open a new terminal. Use a fine-grained token with write access to the team's adapter repo only, and revoke it after the event. Never paste tokens into the repo, chat, or notebooks.

## 3. Branches

Work on `feat/<area>` branches and merge to `main` through short PRs. `main` must always run the demo.

## 4. Ports and the GPU

- Models are served once, for everyone, by ZRT on `127.0.0.1:8080`. Don't start a second copy.
- Each person runs their own Herald server on their own port: 8101, 8102, 8103, 8104. Port 8100 is the demo instance.
- Only one GPU-heavy job at a time (fine-tuning, big model swaps). Announce it in the team chat first.

## 5. Owners (fill in)

| Area | Owner |
|---|---|
| ML: STT, LLM/VLM serving, extraction, LoRA + benchmark | TBD |
| State + relay backend | TBD |
| Frontend: NOW screen, phone capture page, ED screen | NOW screen: @tushar-fs; capture page and ED screen: TBD |
| Data + eval | TBD |
| Pitch + integration | TBD |
