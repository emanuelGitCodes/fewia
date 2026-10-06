---
name: worktree-cleanup
description: List git worktrees whose branch is already merged into main, show the removal commands, and remove them after the user says yes. Use when the user asks to clean up, prune, or remove worktrees or stale branches.
argument-hint: "[--include-dirty]"
---

# Worktree cleanup

The feature loop creates one worktree per work item. Merged items leave
their worktrees behind. This skill removes them safely.

## Steps

1. Run the lister from the repository root:

   ```bash
   .claude/skills/worktree-cleanup/scripts/list-merged-worktrees.sh
   ```

   It prints one line per worktree whose branch is an ancestor of `main`.
   It skips the main checkout, the current directory, a detached HEAD, and
   a worktree with uncommitted changes.

2. Show the user the list and the two commands it will run for each row:

   ```bash
   git worktree remove <path>
   ```

   ```bash
   git branch -d <branch>
   ```

3. Wait for an explicit yes. Removal is destructive. Do not proceed on
   silence or on a partial answer.

4. Run the commands. Use `git worktree remove`, never `rm -rf`. Report
   each failure with its message. A worktree that fails to remove stays
   in the list for the user.

5. Finish with `git worktree prune` and the new worktree count.

## Rules

- Never remove the main checkout or the worktree the session runs in.
- Never delete a branch that is not merged. `git branch -d` refuses on its
  own. Do not switch to `-D`.
- A worktree with uncommitted changes needs the user's own decision. The
  lister hides it unless the user passes `--include-dirty`.
