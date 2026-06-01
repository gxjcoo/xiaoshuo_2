# 全新3章测试
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  全新运行 - 生成前3章" -ForegroundColor Cyan  
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "开始时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host ""

python -m workflow.cli run --novel 1.txt --start 1 --end 3 --advanced_decompose

$exitCode = $LASTEXITCODE
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "  3章生成完成!" -ForegroundColor Green
} else {
    Write-Host "  失败 (exit code: $exitCode)" -ForegroundColor Red
}
Write-Host "  结束时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
