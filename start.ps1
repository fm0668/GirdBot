# 双账户对冲网格策略启动脚本 (PowerShell)
# 使用方法: .\start.ps1

param(
    [switch]$TestMode = $false,
    [switch]$CheckOnly = $false
)

Write-Host "=== 双账户对冲网格策略启动器 ===" -ForegroundColor Green
Write-Host ""

# 检查环境变量
function Check-Environment {
    Write-Host "1. 检查环境变量..." -ForegroundColor Yellow
    
    $requiredVars = @(
        "LONG_API_KEY", "LONG_API_SECRET",
        "SHORT_API_KEY", "SHORT_API_SECRET"
    )
    
    $missingVars = @()
    foreach ($var in $requiredVars) {
        if (-not $env:$var) {
            $missingVars += $var
        }
    }
    
    if ($missingVars.Count -gt 0) {
        Write-Host "❌ 缺少环境变量:" -ForegroundColor Red
        foreach ($var in $missingVars) {
            Write-Host "   - $var" -ForegroundColor Red
        }
        Write-Host ""
        Write-Host "请参考 .env.example 文件设置环境变量" -ForegroundColor Yellow
        return $false
    }
    
    Write-Host "✅ 环境变量检查通过" -ForegroundColor Green
    return $true
}

# 检查Python环境
function Check-Python {
    Write-Host "2. 检查Python环境..." -ForegroundColor Yellow
    
    try {
        $pythonVersion = python --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Python未安装或不在PATH中" -ForegroundColor Red
            return $false
        }
        Write-Host "✅ Python版本: $pythonVersion" -ForegroundColor Green
    }
    catch {
        Write-Host "❌ Python检查失败: $_" -ForegroundColor Red
        return $false
    }
    
    return $true
}

# 检查依赖包
function Check-Dependencies {
    Write-Host "3. 检查依赖包..." -ForegroundColor Yellow
    
    $dependencies = @("aiohttp", "ccxt", "pandas", "numpy", "python-dotenv")
    $missingDeps = @()
    
    foreach ($dep in $dependencies) {
        try {
            $result = python -c "import $dep" 2>&1
            if ($LASTEXITCODE -ne 0) {
                $missingDeps += $dep
            }
        }
        catch {
            $missingDeps += $dep
        }
    }
    
    if ($missingDeps.Count -gt 0) {
        Write-Host "❌ 缺少依赖包:" -ForegroundColor Red
        foreach ($dep in $missingDeps) {
            Write-Host "   - $dep" -ForegroundColor Red
        }
        Write-Host ""
        Write-Host "请运行: pip install -r requirements.txt" -ForegroundColor Yellow
        return $false
    }
    
    Write-Host "✅ 依赖包检查通过" -ForegroundColor Green
    return $true
}

# 创建必要目录
function Ensure-Directories {
    Write-Host "4. 检查目录结构..." -ForegroundColor Yellow
    
    $dirs = @("logs", "config", "src", "src/core", "src/exchange")
    
    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            Write-Host "❌ 缺少目录: $dir" -ForegroundColor Red
            return $false
        }
    }
    
    Write-Host "✅ 目录结构检查通过" -ForegroundColor Green
    return $true
}

# 主函数
function Main {
    $allChecks = $true
    
    # 执行检查
    $allChecks = $allChecks -and (Check-Environment)
    $allChecks = $allChecks -and (Check-Python)
    $allChecks = $allChecks -and (Check-Dependencies)
    $allChecks = $allChecks -and (Ensure-Directories)
    
    if (-not $allChecks) {
        Write-Host ""
        Write-Host "❌ 环境检查失败，无法启动策略" -ForegroundColor Red
        exit 1
    }
    
    if ($CheckOnly) {
        Write-Host ""
        Write-Host "✅ 所有检查通过，环境配置正确" -ForegroundColor Green
        return
    }
    
    Write-Host ""
    Write-Host "5. 启动策略..." -ForegroundColor Yellow
    Write-Host ("-" * 50)
    
    # 启动策略
    if ($TestMode) {
        Write-Host "🧪 测试模式启动" -ForegroundColor Cyan
        $env:STRATEGY_MODE = "test"
    }
    
    try {
        python main.py
    }
    catch {
        Write-Host "❌ 策略启动失败: $_" -ForegroundColor Red
        exit 1
    }
}

# 显示帮助信息
if ($args -contains "-h" -or $args -contains "--help") {
    Write-Host "双账户对冲网格策略启动脚本"
    Write-Host ""
    Write-Host "用法:"
    Write-Host "  .\start.ps1                # 正常启动"
    Write-Host "  .\start.ps1 -TestMode      # 测试模式启动"
    Write-Host "  .\start.ps1 -CheckOnly     # 仅检查环境"
    Write-Host ""
    Write-Host "参数:"
    Write-Host "  -TestMode     启用测试模式"
    Write-Host "  -CheckOnly    仅执行环境检查"
    Write-Host "  -h, --help    显示帮助信息"
    exit 0
}

# 执行主函数
Main
