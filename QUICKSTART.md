# GirdBot 快速启动指南

## 🚀 一键部署

### 1. 克隆并安装
```bash
git clone https://github.com/fm0668/GirdBot.git
cd GirdBot
chmod +x install.sh && ./install.sh
```

### 2. 配置API密钥
```bash
nano .env
```
将以下内容填入.env文件：
```env
BINANCE_API_KEY=你的币安API密钥
BINANCE_API_SECRET=你的币安API秘钥
COIN_NAME=DOGE
CONTRACT_TYPE=USDT
GRID_SPACING=0.001
INITIAL_QUANTITY=10
LEVERAGE=20
POSITION_THRESHOLD=500
POSITION_LIMIT=100
SYNC_TIME=10
ORDER_FIRST_TIME=10
```

### 3. 启动策略
```bash
./start_grid.sh
```

## 📱 管理命令

| 命令 | 功能 | 说明 |
|------|------|------|
| `./start_grid.sh` | 启动策略 | 启动网格交易策略 |
| `./stop_grid.sh` | 停止策略 | 安全停止策略 |
| `./status_grid.sh` | 查看状态 | 查看运行状态和日志 |
| `./test_setup.sh` | 测试环境 | 检查环境配置 |

## 📊 监控日志
```bash
# 实时监控
tail -f log/grid_binance.log

# 查看最新日志
tail -100 log/grid_binance.log

# 查看错误日志
grep "ERROR" log/grid_binance.log
```

## ⚠️ 重要提醒

1. **确保API权限**：API密钥必须有期货交易权限
2. **启用双向持仓**：在币安期货设置中启用双向持仓模式
3. **充足资金**：确保账户有足够的USDT余额
4. **网络稳定**：确保VPS网络连接稳定

## 🔧 故障排除

### API连接失败
- 检查API密钥是否正确
- 确认网络能访问币安API
- 验证API权限设置

### 策略异常停止
```bash
# 查看进程状态
./status_grid.sh

# 查看错误日志
grep "ERROR\|CRITICAL" log/grid_binance.log

# 重启策略
./stop_grid.sh && ./start_grid.sh
```

## 📈 预期表现

- **适用市场**：震荡行情效果最佳
- **盈利模式**：通过频繁的网格交易获取价差
- **风险控制**：自动止损和仓位管理
- **资金效率**：杠杆交易提高资金利用率
