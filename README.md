# GirdBot - 币安网格策略交易机器人

一个基于币安期货API的自动化网格交易策略，支持双向持仓模式的网格交易。

## 🚀 功能特性

- **智能网格交易**: 基于ATR指标的自适应网格间距
- **双向持仓模式**: 支持多头和空头同时操作
- **风险控制**: 多层止损保护和仓位管理
- **实时监控**: WebSocket实时价格和订单监控
- **自动重连**: 网络断线自动重连机制

## � 系统要求

- Python 3.8+
- 币安期货账户（需要API权限）
- Linux VPS（推荐）

## 🛠️ 安装部署

### 1. 克隆项目
```bash
git clone https://github.com/fm0668/GirdBot.git
cd GirdBot
```

### 2. 运行安装脚本
```bash
chmod +x install.sh
./install.sh
```

### 3. 配置API密钥
编辑 `.env` 文件，填入您的币安API密钥：
```bash
nano .env
```

配置示例：
```env
BINANCE_API_KEY=your_actual_api_key
BINANCE_API_SECRET=your_actual_api_secret
COIN_NAME=DOGE
CONTRACT_TYPE=USDT
GRID_SPACING=0.001
INITIAL_QUANTITY=10
LEVERAGE=20
```

### 4. 启动策略
```bash
./start_grid.sh
```

## 📊 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| COIN_NAME | 交易币种 | DOGE |
| CONTRACT_TYPE | 合约类型 | USDT |
| GRID_SPACING | 网格间距比例 | 0.001 (0.1%) |
| INITIAL_QUANTITY | 初始交易数量 | 10 |
| LEVERAGE | 杠杆倍数 | 20 |
| POSITION_THRESHOLD | 锁仓阈值 | 500 |
| POSITION_LIMIT | 持仓数量阈值 | 100 |

## 🎯 交易逻辑

1. **网格布局**: 根据当前价格上下布置买卖网格
2. **多头策略**: 价格下跌时买入，价格上涨时卖出止盈
3. **空头策略**: 价格上涨时卖出，价格下跌时买入止盈
4. **风险控制**: 持仓超过阈值时停止开新仓，执行风险管理

## 📱 管理命令

### 启动策略
```bash
./start_grid.sh
```

### 停止策略
```bash
./stop_grid.sh
```

### 查看状态
```bash
./status_grid.sh
```

### 测试环境
```bash
./test_setup.sh
```

## 📝 日志监控

策略运行时会在 `log/grid_binance.log` 文件中记录详细日志：

```bash
# 实时查看日志
tail -f log/grid_binance.log

# 查看最新100行日志
tail -100 log/grid_binance.log
```

## ⚠️ 风险提示

1. **资金风险**: 网格策略存在亏损风险，请合理配置仓位
2. **API安全**: 请妥善保管API密钥，建议使用只读+交易权限
3. **网络稳定**: 确保VPS网络稳定，避免断网导致的风险
4. **市场波动**: 极端行情下可能触发止损，请关注市场动态

**Q: 依赖安装失败？**
A: 检查Python版本(3.8+)，尝试升级pip: `python -m pip install --upgrade pip`

**Q: API连接失败？**
A: 检查API密钥是否正确，网络是否畅通，IP是否在白名单中

**Q: 策略启动失败？**
A: 查看logs目录下的日志文件，检查具体错误信息

### 日志文件说明

- `grid_strategy.log`: 主要策略运行日志
- `trades.log`: 交易执行记录
- 日志级别: DEBUG < INFO < WARNING < ERROR < CRITICAL

## 📞 技术支持

如遇技术问题，请：

1. 检查日志文件中的错误信息
2. 确认环境配置是否正确
3. 查看项目文档和参考资料
4. 提供详细的错误描述和日志信息

## 📄 许可证

本项目仅供学习和研究使用，请勿用于商业用途。使用本软件进行交易的风险由用户自行承担。

---

**版本**: v1.0.0  
**最后更新**: 2024年7月  
**开发团队**: Grid Strategy Team
