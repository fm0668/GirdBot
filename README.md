# 双账户对冲网格策略 (Hedge Grid Bot)

一个基于Python的双账户对冲网格交易策略，专为币安永续合约设计。

## 📋 项目概述

本项目实现了一个双账户对冲网格交易策略，通过在两个账户中分别执行多头和空头网格交易，实现市场中性的套利收益。系统基于ATR指标动态计算网格参数，具备完善的风险控制和监控机制。

### 核心特性

- 🔄 **双账户对冲**：同时管理多头和空头账户，实现市场中性策略
- 📊 **ATR动态网格**：基于ATR指标动态计算网格间距和层数
- 🛡️ **风险控制**：实时监控风险指标，支持自动止损和紧急平仓
- 📈 **实时监控**：完整的系统状态监控和性能分析
- 🔧 **模块化设计**：清晰的架构分层，便于扩展和维护
- ⚡ **异步处理**：基于asyncio的高性能异步交易执行

## 🏗️ 系统架构

```
双账户对冲网格策略系统
├── 主策略层 (hedge_grid_strategy.py)
├── 配置管理层 (config/)
│   ├── 双账户配置管理
│   └── 执行器配置管理
├── 账户管理层 (core/dual_account_manager.py)
├── 网格计算层
│   ├── ATR计算器
│   ├── 网格参数计算器
│   └── 共享网格引擎
├── 执行器架构层
│   ├── 基础执行器（抽象）
│   ├── 多头执行器
│   ├── 空头执行器
│   ├── 执行器工厂
│   └── 同步控制器
├── 监控管理层
│   ├── 统一监控模块
│   └── 风险控制器
└── 工具库层 (utils/)
```

## 🚀 快速开始

### 环境要求

- Python 3.9+
- 币安账户（支持永续合约）
- 至少1000 USDT资金（推荐）

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd GirdBot
```

2. **创建虚拟环境**
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **配置环境变量**
```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下参数：

```env
# 币安API配置 - 账户A (多头)
BINANCE_API_KEY_A=your_api_key_a
BINANCE_SECRET_KEY_A=your_secret_key_a

# 币安API配置 - 账户B (空头)  
BINANCE_API_KEY_B=your_api_key_b
BINANCE_SECRET_KEY_B=your_secret_key_b

# 交易配置
TRADING_PAIR=DOGEUSDC
BASE_ASSET=DOGE
QUOTE_ASSET=USDC

# 网格策略参数
TARGET_PROFIT_RATE=0.002
SAFETY_FACTOR=0.8
ATR_LENGTH=14
ATR_MULTIPLIER=2.0

# 其他配置...
```

5. **启动策略**
```bash
./scripts/start_hedge_grid.sh
```

## 📊 使用说明

### 启动和停止

```bash
# 启动策略
./scripts/start_hedge_grid.sh

# 查看状态
./scripts/status_hedge_grid.sh

# 停止策略
./scripts/stop_hedge_grid.sh
```

### 监控和日志

```bash
# 实时查看日志
tail -f logs/hedge_grid.log

# 查看详细状态
./scripts/status_hedge_grid.sh --watch

# 查看最新50行日志
./scripts/status_hedge_grid.sh --logs 50
```

### 配置参数说明

| 参数 | 说明 | 默认值 | 建议范围 |
|------|------|--------|----------|
| `TARGET_PROFIT_RATE` | 目标利润率 | 0.002 | 0.001-0.005 |
| `SAFETY_FACTOR` | 安全系数 | 0.8 | 0.6-1.0 |
| `ATR_LENGTH` | ATR计算周期 | 14 | 10-30 |
| `ATR_MULTIPLIER` | ATR倍数 | 2.0 | 1.5-3.0 |
| `MAX_LEVERAGE` | 最大杠杆 | 10 | 3-20 |
| `MAX_DRAWDOWN_PCT` | 最大回撤 | 0.15 | 0.05-0.20 |

## 🛡️ 风险管理

### 内置风险控制

1. **回撤控制**：实时监控账户回撤，超过阈值自动停止
2. **仓位平衡**：监控双账户仓位差异，避免过度偏离
3. **保证金监控**：实时检查保证金比率，防止强平
4. **止损机制**：价格异常波动时自动触发紧急止损

### 风险提示

⚠️ **重要提醒**：
- 量化交易存在本金损失风险
- 建议使用小额资金进行测试
- 请充分理解策略逻辑后使用
- 网络延迟可能影响交易执行
- 市场极端行情下可能出现较大亏损

## 📈 性能监控

### 监控指标

- **账户余额**：实时双账户余额监控
- **盈亏统计**：累计盈亏和收益率
- **交易统计**：成交次数、胜率、平均利润
- **风险指标**：最大回撤、当前杠杆、风险级别
- **系统状态**：连接状态、订单状态、同步状态

### 告警机制

- 回撤超过阈值告警
- 余额差异过大告警
- 长时间无交易活动告警
- 系统异常状态告警

## 🔧 开发指南

### 项目结构

```
GirdBot/
├── config/                 # 配置管理
├── core/                   # 核心业务逻辑
│   ├── atr_calculator.py   # ATR计算
│   ├── grid_calculator.py  # 网格参数计算
│   ├── dual_account_manager.py  # 账户管理
│   ├── hedge_grid_executor.py   # 基础执行器
│   ├── long_account_executor.py # 多头执行器
│   ├── short_account_executor.py # 空头执行器
│   └── ...
├── utils/                  # 工具库
├── scripts/                # 启动脚本
├── tests/                  # 测试用例
└── logs/                   # 日志文件
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_atr_calculator.py

# 运行测试并显示覆盖率
pytest --cov=core tests/
```

### 添加新功能

1. 在对应模块中实现功能
2. 编写单元测试
3. 更新配置文件（如需要）
4. 更新文档

## 📚 API文档

### 核心模块

#### ATRCalculator
```python
from core.atr_calculator import ATRCalculator, ATRConfig

# 创建ATR计算器
calculator = ATRCalculator(exchange)

# 计算ATR通道
config = ATRConfig(length=14, multiplier=2.0)
result = await calculator.calculate_atr_channel("BTCUSDT", "1h", config)
```

#### DualAccountManager
```python
from core.dual_account_manager import DualAccountManager

# 创建账户管理器
manager = DualAccountManager(dual_config)

# 初始化账户
await manager.initialize_accounts()

# 获取账户状态
status = await manager.get_dual_account_status()
```

## 🔍 故障排除

### 常见问题

1. **API连接失败**
   - 检查API密钥配置
   - 确认网络连接正常
   - 验证API权限设置

2. **策略启动失败**
   - 检查账户余额是否充足
   - 确认没有未平仓位
   - 查看详细错误日志

3. **订单执行异常**
   - 检查交易对是否正确
   - 确认最小下单金额
   - 验证账户权限

### 日志分析

```bash
# 查看错误日志
grep "ERROR" logs/hedge_grid.log

# 查看最近的告警
grep "WARNING" logs/hedge_grid.log | tail -10

# 分析交易记录
grep "交易执行" logs/hedge_grid.log
```

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

### 开发流程

1. Fork项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

### 代码规范

- 使用Python Black进行代码格式化
- 遵循PEP8编码规范
- 添加必要的类型注解
- 编写完整的文档字符串

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## ⚖️ 免责声明

本软件仅供学习和研究使用。使用本软件进行实际交易的风险由用户自行承担。开发者不对因使用本软件而造成的任何损失负责。

在使用前，请：
- 充分了解量化交易的风险
- 在测试环境中验证策略
- 仅使用可承受损失的资金
- 遵守当地法律法规

## 📞 联系方式

- 项目主页：[GitHub Repository](https://github.com/yourusername/GirdBot)
- 问题反馈：[Issues](https://github.com/yourusername/GirdBot/issues)
- 讨论交流：[Discussions](https://github.com/yourusername/GirdBot/discussions)

---

**⭐ 如果这个项目对您有帮助，请给个Star支持！**