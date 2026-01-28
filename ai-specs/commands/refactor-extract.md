# Command: Extract Module

Extract endpoints or classes from a monolithic file to a new module.

## Usage

```
/refactor-extract {source_file} {target_file} {pattern}
```

## Process

1. **Identify targets** matching the pattern in source file
2. **Create branch**: `git checkout -b refactor/extract-{target_name}`
3. **Create target file** with proper imports and structure
4. **Move code** exactly as-is (no logic changes)
5. **Update source file** to import from target
6. **Fix imports** in all affected files
7. **Run tests**: `pytest tests/ -v`
8. **Commit**: descriptive message with line counts
9. **Report** what was moved and new line counts

## Example

```
/refactor-extract backend/api/main.py backend/api/routers/leads.py "/leads/*"
```

This will:
1. Find all endpoints starting with `/leads/` in main.py
2. Move them to routers/leads.py
3. Add `app.include_router(leads.router)` to main.py
4. Update any imports
5. Run tests
6. Commit the change

## Rules

- **Never rewrite logic** while extracting
- **Keep function signatures** identical
- **Test after every extraction**
- **One extraction per commit**
