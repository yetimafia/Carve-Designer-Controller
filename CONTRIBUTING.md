# Contributing

Thank you for helping. This project was written mostly by an AI for a player who does not code, so cleanups, fixes,
tests and docs are all welcome.

## Making your own version

Anyone can **fork** this repository (the Fork button on GitHub) and change their own copy however they like, including a completely
different design. Nobody except the owner can change this repository's `main` branch; if you want your change included here, open a
pull request from your fork and the owner will decide.

## Workflow

1. Edit files in `src/` (never `replicating_turtles.py` directly).
2. `python build.py` to rebuild the single file.
3. `python -m pyflakes replicating_turtles.py` and the test suite (see README) must be clean.
4. Bump `VERSION` in `src/p1_core.py`: +0.1 for each batch of features, and a further +0.1 when it includes a bug fix.
5. Add a line to `CHANGELOG.md`.
6. Commit `src/`, `tests/` **and** the rebuilt `replicating_turtles.py` (CI checks they match).

## Comments

Please keep the style of the existing comments: say *why*, and say which version added it ("v7.6: ..."). Many odd-looking rules
come from how one modpack behaves; the comment is the only place that remembers it.

## Never commit secrets

Do not put GitHub tokens, passwords or personal paths in the repository, in code, tests or screenshots. The app only stores
a token on the user's own computer, and only if they opt in. `.gitignore` already skips the usual files.

## Testing against the game

The Lua programs are tested against a mock turtle (`tests/auto_mock.lua`) with switches that copy real-pack behaviour
(`strictCraft`, `driveNoDrop`, `driveTopOnly`). If you find a new real-game behaviour, add a switch and a test for it first.
