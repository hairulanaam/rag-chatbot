# deploy.ps1 - Jalankan dengan: .\deploy.ps1
Write-Host "🚀 Deploying to HF Spaces..." -ForegroundColor Cyan

git checkout --orphan hf-deploy
git add .
git commit -m "deploy: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
git push hf hf-deploy:main --force
git checkout main
git branch -D hf-deploy

Write-Host "✅ Deploy selesai!" -ForegroundColor Green
