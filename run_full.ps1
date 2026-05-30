# 启动完整385章工作流
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  小说改编工作流 - 全量运行 (1-385章)" -ForegroundColor Cyan  
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "开始时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host ""

# 运行工作流，输出同时显示在屏幕和保存到日志
$logFile = "workflow_run.log"
Write-Host "日志文件: $logFile" -ForegroundColor Gray
Write-Host ""

python -m workflow.cli run --novel 1.txt --start 1 --end 385 --advanced_decompose *>&1 | Tee-Object -FilePath $logFile

$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "  工作流执行完成!" -ForegroundColor Green
} else {
    Write-Host "  工作流执行失败 (exit code: $exitCode)" -ForegroundColor Red
}
Write-Host "  结束时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
