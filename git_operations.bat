@echo off
echo ========================================
echo Git Operations for Hybrid Search & Re-ranking
echo ========================================
echo.

echo [1/4] Checking git status...
git status
echo.

echo [2/4] Staging files...
git add src/querying.py src/dependencies.py
git status --short
echo.

echo [3/4] Committing changes...
git commit -m "Implement hybrid search and re-ranking for improved retrieval accuracy

- Add hybrid search combining semantic and keyword search
- Implement re-ranking of retrieved chunks with multi-heuristic scoring
- Enable both features by default for better answer quality"
echo.

echo [4/4] Pushing to GitHub...
git push
echo.

echo ========================================
echo Done! Check output above for any errors.
echo ========================================
pause


