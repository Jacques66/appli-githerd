# -*- coding: utf-8 -*-
"""
GitHerd — Git utility functions.

Low-level Git operations and helpers.
"""

import subprocess

from .config import DEFAULT_REPO_CONFIG


def run_git(cmd, cwd=None, timeout=30):
    """Run a git command and return (returncode, stdout, stderr).

    On timeout, the partial stderr captured before the kill is included
    in the returned stderr string so the caller can show the actual
    network/auth failure git was reporting.
    """
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            timeout=timeout
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired as e:
        partial = ""
        if e.stderr:
            try:
                partial = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
            except Exception:
                partial = ""
            partial = partial.strip()
        msg = f"Timeout after {timeout}s"
        if partial:
            msg += f" — last stderr: {partial}"
        return 1, "", msg
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"
    except Exception as e:
        return 1, "", str(e)


def commits_ahead(base, tip, cwd=None, git="git"):
    """Count commits that tip has ahead of base."""
    code, out, err = run_git([git, "rev-list", "--count", f"{base}..{tip}"], cwd=cwd)
    if code != 0:
        raise RuntimeError(err)
    return int(out)


def commits_behind(base, tip, cwd=None, git="git"):
    """Count commits that tip is behind base."""
    code, out, err = run_git([git, "rev-list", "--count", f"{tip}..{base}"], cwd=cwd)
    if code != 0:
        return 0
    return int(out)


def get_tracked_branches(remote, prefix, cwd=None, git="git"):
    """Get list of remote branches matching prefix."""
    code, out, err = run_git(
        [git, "for-each-ref", "--format=%(refname:short)",
         f"refs/remotes/{remote}/{prefix}"],
        cwd=cwd
    )
    if code != 0:
        raise RuntimeError(err)
    return out.splitlines() if out else []


def get_changed_files(base, tip, cwd=None, git="git"):
    """Get set of files changed between base and tip."""
    code, out, err = run_git([git, "diff", "--name-only", f"{base}...{tip}"], cwd=cwd)
    if code != 0:
        return set()
    return set(out.splitlines()) if out else set()


def are_files_disjoint(branches, main_ref, remote, cwd=None, git="git"):
    """Check if all branches modify disjoint sets of files."""
    all_files = []
    for branch in branches:
        files = get_changed_files(main_ref, f"{remote}/{branch}", cwd=cwd, git=git)
        all_files.append(files)

    for i in range(len(all_files)):
        for j in range(i + 1, len(all_files)):
            if all_files[i] & all_files[j]:
                return False
    return True


def remote_ref_exists(remote, branch, cwd=None, git="git"):
    """Check if a remote tracking ref exists locally (e.g., origin/main)."""
    code, _, _ = run_git(
        [git, "rev-parse", "--verify", f"refs/remotes/{remote}/{branch}"],
        cwd=cwd
    )
    return code == 0


def local_main_ahead(remote, main, cwd=None, git="git"):
    """Check if local main is ahead of remote main.

    Returns:
        int: Number of commits ahead, or -1 if remote ref doesn't exist (bootstrap needed)
    """
    # Check if remote ref exists first
    if not remote_ref_exists(remote, main, cwd=cwd, git=git):
        # Remote main doesn't exist - need bootstrap push
        return -1
    try:
        return commits_ahead(f"{remote}/{main}", main, cwd=cwd, git=git)
    except Exception:
        return 0


def delete_remote_branch(branch_name, remote, cwd=None, git="git"):
    """Delete a remote branch."""
    code, out, err = run_git([git, "push", remote, "--delete", branch_name], cwd=cwd)
    return code == 0, err


def is_git_repo(path, git="git"):
    """Check if path is a git repository."""
    code, _, _ = run_git([git, "rev-parse", "--git-dir"], cwd=path)
    return code == 0


def get_short_head(cwd=None, git="git"):
    """Return the short HEAD commit hash, or empty string on failure."""
    code, out, _ = run_git([git, "rev-parse", "--short", "HEAD"], cwd=cwd)
    return out.strip() if code == 0 else ""


def get_remote_url(remote, cwd=None, git="git"):
    """Return the URL configured for a remote, or empty string."""
    code, out, _ = run_git([git, "remote", "get-url", remote], cwd=cwd)
    return out.strip() if code == 0 else ""


def check_git_health(repo_path, remote, main_branch, git="git"):
    """Check if git is functional for this repository.

    Returns (ok: bool, error_message: str). Failure messages now
    include the offending command and any stderr emitted by git so
    the caller can show useful context in the log.
    """
    cmd = [git, "rev-parse", "--git-dir"]
    code, _, err = run_git(cmd, cwd=repo_path)
    if code != 0:
        return False, f"Not a Git repository ({' '.join(cmd)}): {err}"

    cmd = [git, "remote"]
    code, out, err = run_git(cmd, cwd=repo_path)
    if code != 0:
        return False, f"Git remote error ({' '.join(cmd)}): {err}"
    if remote not in out.splitlines():
        return False, f"Remote '{remote}' not found"

    cmd = [git, "fetch", remote, "--dry-run"]
    code, _, err = run_git(cmd, cwd=repo_path)
    if code != 0:
        return False, f"Fetch failed ({' '.join(cmd)}): {err}"

    return True, ""


def detect_repo_settings(repo_path, git_binary="git"):
    """Auto-detect remote and main branch for a repository."""
    settings = DEFAULT_REPO_CONFIG.copy()

    code, out, _ = run_git([git_binary, "remote"], cwd=repo_path)
    if code == 0 and out:
        remotes = out.splitlines()
        if remotes:
            settings["remote"] = remotes[0]

    remote = settings["remote"]
    code, out, _ = run_git(
        [git_binary, "symbolic-ref", f"refs/remotes/{remote}/HEAD"],
        cwd=repo_path
    )
    if code == 0 and out:
        parts = out.split("/")
        if len(parts) >= 4:
            settings["main_branch"] = parts[-1]
    else:
        code, out, _ = run_git(
            [git_binary, "branch", "-r", "--list", f"{remote}/main"],
            cwd=repo_path
        )
        if code == 0 and out.strip():
            settings["main_branch"] = "main"
        else:
            code, out, _ = run_git(
                [git_binary, "branch", "-r", "--list", f"{remote}/master"],
                cwd=repo_path
            )
            if code == 0 and out.strip():
                settings["main_branch"] = "master"

    return settings
