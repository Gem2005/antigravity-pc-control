# Contributing

Contributions, bug reports, and new Windows diagnostic scripts are welcome!

## Development Setup

```powershell
git clone https://github.com/Gem2005/antigravity-pc-control.git
cd antigravity-pc-control
uv --directory server sync --group dev
```

## Running Tests

```powershell
uv --directory server run pytest
```

## Coding Guidelines

- Keep `pc_control_mcp.py` 64-bit safe when calling Win32 APIs via `ctypes` (always declare `.argtypes` and `.restype`).
- Maintain the 3-tier safety boundary in `rules/AGENTS.md`—never bypass UAC, credential screens, or destructive-action confirmations.
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, `chore:`) for commit messages.
