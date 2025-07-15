# 双账户对冲网格策略 - AI代码生成工程蓝图

## I. 系统架构总览

### 1.1 系统架构图

```
双账户对冲网格策略系统
┌─────────────────────────────────────────────────────────────────────────────┐
│                              主策略层                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┤
│  │                    hedge_grid_strategy.py                               │
│  │              双账户对冲网格策略主脚本                                   │
│  └─────────────────────────────────────────────────────────────────────────┤
├─────────────────────────────────────────────────────────────────────────────┤
│                             配置管理层                                      │
│  ┌────────────────────┬────────────────────┬──────────────────────────────┤
│  │  config/           │  config/           │  .env                        │
│  │  dual_account_     │  grid_executor_    │  环境变量配置                │
│  │  config.py         │  config.py         │                              │
│  │  双账户配置管理    │  执行器配置管理    │                              │
│  └────────────────────┴────────────────────┴──────────────────────────────┤
├─────────────────────────────────────────────────────────────────────────────┤
│                             账户管理层                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┤
│  │                    core/dual_account_manager.py                         │
│  │                        双账户连接和管理                                │
│  └─────────────────────────────────────────────────────────────────────────┤
├─────────────────────────────────────────────────────────────────────────────┤
│                          网格计算层（共享）                                 │
│  ┌───────────────────┬─────────────────────┬─────────────────────────────┤
│  │  core/            │  core/              │  core/                      │
│  │  atr_calculator.py│  grid_calculator.py │  shared_grid_engine.py      │
│  │  ATR指标计算      │  网格参数计算       │  共享网格参数引擎           │
│  └───────────────────┴─────────────────────┴─────────────────────────────┤
├─────────────────────────────────────────────────────────────────────────────┤
│                           执行器架构层                                      │
│  ┌───────────────────┬─────────────────────┬─────────────────────────────┤
│  │  core/            │  core/              │  core/                      │
│  │  hedge_grid_      │  long_account_      │  short_account_             │
│  │  executor.py      │  executor.py        │  executor.py                │
│  │  基础执行器       │  多头执行器         │  空头执行器                 │
│  │  (抽象基类)       │                     │                             │
│  └───────────────────┴─────────────────────┴─────────────────────────────┤
│  ┌───────────────────┬─────────────────────────────────────────────────────┤
│  │  core/            │  core/                                             │
│  │  executor_        │  sync_controller.py                                │
│  │  factory.py       │  同步控制器                                        │
│  │  执行器工厂       │                                                    │
│  └───────────────────┴─────────────────────────────────────────────────────┤
├─────────────────────────────────────────────────────────────────────────────┤
│                             监控管理层                                      │
│  ┌───────────────────┬─────────────────────────────────────────────────────┤
│  │  core/            │  core/                                             │
│  │  hedge_monitor.py │  risk_hedge_controller.py                          │
│  │  统一监控模块     │  对冲风险控制                                      │
│  └───────────────────┴─────────────────────────────────────────────────────┤
├─────────────────────────────────────────────────────────────────────────────┤
│                             工具库层                                        │
│  ┌───────────────────┬─────────────────────┬─────────────────────────────┤
│  │  utils/logger.py  │  utils/helpers.py   │  utils/order_tracker.py    │
│  │  日志管理         │  工具函数           │  订单跟踪器                 │
│  └───────────────────┴─────────────────────┴─────────────────────────────┤
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心数据流图

```
数据流向：外部数据 → 计算处理 → 参数分发 → 执行器 → 交易所

┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  币安交易所  │───→│  市场数据获取│───→│  ATR计算    │───→│  网格参数    │
│  K线/订单   │    │  (CCXT)     │    │             │    │  计算        │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                                │
┌─────────────┐    ┌─────────────┐    ┌─────────────┐           │
│  用户配置    │───→│  配置管理    │───→│  双账户管理  │←──────────┘
│  (.env)     │    │             │    │             │
└─────────────┘    └─────────────┘    └─────────────┘
                                                │
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  共享网格    │←───│  参数分发    │←───│             │
│  参数引擎    │    │             │    │             │
└─────────────┘    └─────────────┘    └─────────────┘
        │                                      │
        ├─────────────┐                       │
        ▼             ▼                       ▼
┌─────────────┐ ┌─────────────┐    ┌─────────────┐
│  多头执行器  │ │  空头执行器  │    │  同步控制器  │
│  (买入网格)  │ │  (卖出网格)  │    │             │
└─────────────┘ └─────────────┘    └─────────────┘
        │             │                       │
        ├─────────────┴───────────────────────┤
        ▼                                     ▼
┌─────────────┐                    ┌─────────────┐
│  币安账户A   │                    │  风险监控    │
│  (多头合约)  │                    │  & 止损     │
└─────────────┘                    └─────────────┘
        │
        ▼
┌─────────────┐
│  币安账户B   │
│  (空头合约)  │
└─────────────┘
```

## II. 项目结构定义

```
GirdBot/
├── README.md                           # 项目说明文档
├── requirements.txt                    # Python依赖包
├── .env                               # 环境变量配置
├── .gitignore                         # Git忽略文件
├── CLAUDE.md                          # 本工程蓝图文档
│
├── config/                            # 配置管理模块
│   ├── __init__.py
│   ├── dual_account_config.py         # 双账户配置管理
│   └── grid_executor_config.py        # 执行器配置管理
│
├── core/                              # 核心业务模块
│   ├── __init__.py
│   │
│   # 账户管理
│   ├── dual_account_manager.py        # 双账户连接和管理
│   │
│   # 网格计算层（共享）
│   ├── atr_calculator.py              # ATR指标计算
│   ├── grid_calculator.py             # 网格参数计算
│   ├── shared_grid_engine.py          # 共享网格参数引擎
│   │
│   # 执行器架构层
│   ├── hedge_grid_executor.py         # 基础执行器（抽象基类）
│   ├── long_account_executor.py       # 多头执行器
│   ├── short_account_executor.py      # 空头执行器
│   ├── executor_factory.py            # 执行器工厂
│   ├── sync_controller.py             # 同步控制器
│   │
│   # 监控管理层
│   ├── hedge_monitor.py               # 统一监控模块
│   └── risk_hedge_controller.py       # 对冲风险控制
│
├── utils/                             # 工具库模块
│   ├── __init__.py
│   ├── logger.py                      # 日志管理 (使用structlog + rich)
│   ├── helpers.py                     # 工具函数
│   ├── exceptions.py                  # 自定义异常类
│   └── order_tracker.py               # 订单跟踪器
│
├── hedge_grid_strategy.py             # 主策略脚本
│
├── scripts/                           # 启动脚本
│   ├── start_hedge_grid.sh           # 启动脚本
│   ├── stop_hedge_grid.sh            # 停止脚本
│   └── status_hedge_grid.sh          # 状态查询脚本
│
└── tests/                             # 测试模块
    ├── __init__.py
    ├── test_atr_calculator.py
    ├── test_grid_calculator.py
    ├── test_dual_account_manager.py
    ├── test_executors.py
    ├── test_sync_controller.py
    ├── test_risk_controller.py
    └── test_order_tracker.py
```

## III. 详细文件生成指令

### 3.1 配置管理层

#### 3.1.1 环境变量配置 (.env)

**目的**: 存储敏感配置信息，包括API密钥、交易对、基础参数等。

**实现要点**:
- 包含双账户的API密钥配置
- 交易对和基础交易参数
- 日志级别和输出配置
- 网格策略基础参数

**配置结构**:
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
ATR_SMOOTHING=RMA

# 系统配置
LOG_LEVEL=INFO
LOG_FILE=logs/hedge_grid.log
EXCHANGE_NAME=binance
```

#### 3.1.2 双账户配置管理 (config/dual_account_config.py)

**目的**: 管理双账户的连接配置、权限验证和余额同步设置。

**实现要点**:
- 使用Pydantic进行配置验证
- 支持从环境变量和配置文件加载
- 提供配置验证和默认值设定
- 支持开发和生产环境配置分离

**核心数据结构**:
```python
@dataclass
class AccountConfig:
    api_key: str
    secret_key: str
    testnet: bool = False
    enable_rate_limit: bool = True
    
@dataclass  
class DualAccountConfig:
    account_a: AccountConfig  # 多头账户
    account_b: AccountConfig  # 空头账户
    exchange_name: str = "binance"
    trading_pair: str
    base_asset: str
    quote_asset: str
    balance_sync_enabled: bool = True
    balance_tolerance_pct: Decimal = Decimal("0.05")
```

**关键方法签名**:
- `def load_from_env() -> DualAccountConfig`
- `def validate_config(self) -> bool`
- `def get_account_config(self, account_type: str) -> AccountConfig`

**【强制技术要求】**: 所有敏感信息必须使用环境变量，不得硬编码在代码中。

#### 3.1.3 执行器配置管理 (config/grid_executor_config.py)

**目的**: 管理网格执行器的所有运行参数，支持精细化控制。

**实现要点**:
- 继承自原有执行器配置基础
- 添加双账户特有的配置参数
- 支持单账户和双账户模式切换
- 提供参数验证和合理性检查

**核心数据结构**:
```python
@dataclass
class GridExecutorConfig:
    # 基础参数
    connector_name: str
    trading_pair: str
    account_mode: str  # 'SINGLE' | 'DUAL'
    
    # 挂单控制参数
    max_open_orders: int = 4
    max_orders_per_batch: int = 2
    order_frequency: float = 3.0
    activation_bounds: Optional[Decimal] = None
    upper_lower_ratio: Decimal = Decimal("0.5")
    
    # 订单类型和安全参数
    open_order_type: OrderType = OrderType.LIMIT
    close_order_type: OrderType = OrderType.LIMIT
    safe_extra_spread: Decimal = Decimal("0.001")
    leverage: int = 10
    
    # 对冲特有参数
    hedge_sync_enabled: bool = True
    risk_check_interval: float = 1.0
    stop_loss_enabled: bool = True
```

**关键方法签名**:
- `def validate_parameters(self) -> List[str]`
- `def create_long_config(self) -> GridExecutorConfig`
- `def create_short_config(self) -> GridExecutorConfig`
- `def to_dict(self) -> dict`

### 3.2 账户管理层

#### 3.2.1 双账户管理器 (core/dual_account_manager.py)

**目的**: 统一管理两个币安账户的连接、认证、余额同步和状态监控。

**实现要点**:
- 使用ccxt异步连接管理双账户
- 实现账户间余额平衡和划转
- 提供统一的API调用接口
- 实现连接状态监控和自动重连

**核心数据结构**:
```python
@dataclass
class AccountStatus:
    account_id: str
    connected: bool
    balance_usdc: Decimal
    open_orders_count: int
    open_positions_count: int
    last_heartbeat: datetime
    
@dataclass
class DualAccountStatus:
    account_a: AccountStatus
    account_b: AccountStatus
    is_balanced: bool
    balance_difference_pct: Decimal
    sync_status: str
```

**关键方法签名**:
- `async def initialize_accounts(self) -> bool`
- `async def pre_flight_checks(self) -> bool`
- `async def balance_accounts(self) -> bool`
- `async def cancel_all_orders(self, account_type: str) -> bool`
- `async def close_all_positions(self, account_type: str) -> bool`
- `async def get_account_balance(self, account_type: str) -> Decimal`
- `async def transfer_funds(self, from_account: str, to_account: str, amount: Decimal) -> bool`

**【强制技术要求】**: 必须使用ccxt.async_support库进行异步交易所连接。

**【强制技术要求】**: 所有金额计算必须使用Decimal类型，避免浮点数精度问题。

**实现要点**:
- pre_flight_checks方法必须在策略启动前执行，确保双账户为空仓状态
- balance_accounts方法需要检查两账户余额并进行平衡划转
- 实现WebSocket连接监控，检测连接状态并自动重连
- 提供统一的订单管理接口，屏蔽两个账户的差异

### 3.3 网格计算层（共享）

#### 3.3.1 ATR计算器 (core/atr_calculator.py)

**目的**: 实现高精度的ATR指标计算，为网格参数提供波动率数据。

**实现要点**:
- 支持多种平滑方法：RMA、SMA、EMA、WMA
- 使用pandas_ta库进行技术指标计算
- 实现ATR通道上下轨计算
- 支持实时数据更新

**核心数据结构**:
```python
@dataclass
class ATRResult:
    atr_value: Decimal
    upper_bound: Decimal  # ATR通道上轨
    lower_bound: Decimal  # ATR通道下轨
    channel_width: Decimal
    calculation_timestamp: datetime
    
@dataclass
class ATRConfig:
    length: int = 14
    multiplier: Decimal = Decimal("2.0")
    smoothing_method: str = "RMA"  # RMA, SMA, EMA, WMA
    source_high: str = "high"
    source_low: str = "low"
```

**关键方法签名**:
- `async def calculate_atr_channel(self, klines_df: pd.DataFrame, config: ATRConfig) -> ATRResult`
- `async def get_latest_klines(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame`
- `def calculate_true_range(self, df: pd.DataFrame) -> pd.Series`
- `def smooth_atr(self, tr_series: pd.Series, method: str, length: int) -> pd.Series`

**【强制技术要求】**: 必须使用pandas_ta库进行技术指标计算。

**【强制技术要求】**: K线数据获取必须使用ccxt的fetch_ohlcv方法。

#### 3.3.2 网格参数计算器 (core/grid_calculator.py)

**目的**: 基于ATR结果和账户信息，计算最优的网格层数、间距和单格金额。

**实现要点**:
- 整合ATR计算结果和账户余额信息
- 实现动态网格间距计算
- 计算最大安全杠杆倍数
- 优化网格层数和单格金额分配

**核心数据结构**:
```python
@dataclass
class GridParameters:
    # 网格基础参数
    upper_bound: Decimal
    lower_bound: Decimal
    grid_spacing: Decimal
    grid_levels: int
    
    # 资金管理参数
    total_balance: Decimal
    usable_leverage: int
    amount_per_grid: Decimal
    
    # 风险控制参数
    stop_loss_upper: Decimal  # 空头止损线
    stop_loss_lower: Decimal  # 多头止损线
    max_drawdown_pct: Decimal
    
    calculation_timestamp: datetime
```

**关键方法签名**:
- `async def calculate_grid_parameters(self, atr_result: ATRResult, account_balances: Dict[str, Decimal]) -> GridParameters`
- `async def calculate_grid_spacing(self, upper_bound: Decimal, target_profit_rate: Decimal, trading_fees: Decimal) -> Decimal`
- `async def calculate_grid_levels(self, price_range: Decimal, grid_spacing: Decimal) -> int`
- `async def calculate_max_leverage(self, atr_result: ATRResult, mmr: Decimal, safety_factor: Decimal) -> int`
- `async def calculate_amount_per_grid(self, total_balance: Decimal, leverage: int, grid_levels: int, min_notional: Decimal) -> Decimal`

**【强制技术要求】**: 所有价格和金额计算必须使用Decimal类型。

**【强制技术要求】**: 网格层数计算必须考虑交易所最小名义价值限制。

#### 3.3.3 共享网格参数引擎 (core/shared_grid_engine.py)

**目的**: 作为网格参数的"单一数据源"，协调ATR计算和网格参数分发。

**实现要点**:
- 整合ATR计算器和网格计算器
- 为双执行器提供统一的参数接口
- 实现参数缓存和更新机制
- 支持参数实时同步

**核心数据结构**:
```python
@dataclass
class GridLevel:
    level_id: int
    price: Decimal
    amount: Decimal
    side: str  # 'LONG' | 'SHORT'
    status: str = "NOT_ACTIVE"
    
@dataclass
class SharedGridData:
    parameters: GridParameters
    long_levels: List[GridLevel]
    short_levels: List[GridLevel]
    last_update: datetime
    is_valid: bool = True
```

**关键方法签名**:
- `async def initialize_grid_parameters(self, config: DualAccountConfig) -> bool`
- `async def update_grid_parameters(self) -> bool`
- `def get_grid_levels_for_account(self, account_type: str) -> List[GridLevel]`
- `def get_current_parameters(self) -> GridParameters`
- `async def generate_grid_levels(self, parameters: GridParameters) -> Tuple[List[GridLevel], List[GridLevel]]`

**【强制技术要求】**: 该模块必须确保全局参数一致性，避免两个执行器使用不同参数。

### 3.4 执行器架构层

#### 3.4.1 基础执行器 (core/hedge_grid_executor.py)

**目的**: 定义网格执行器的抽象基类，实现通用的状态机和订单管理逻辑。

**实现要点**:
- 实现完全抽象的网格执行引擎
- 定义状态机驱动的主控制循环
- 提供抽象方法让子类实现具体交易逻辑
- 实现通用的订单管理和风险控制

**核心枚举和数据结构**:
```python
class GridLevelStates(Enum):
    NOT_ACTIVE = "NOT_ACTIVE"
    OPEN_ORDER_PLACED = "OPEN_ORDER_PLACED"
    OPEN_ORDER_FILLED = "OPEN_ORDER_FILLED"
    CLOSE_ORDER_PLACED = "CLOSE_ORDER_PLACED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"

class RunnableStatus(Enum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    STOPPED = "STOPPED"

@dataclass
class TrackedOrder:
    order_id: str
    level_id: int
    side: str
    amount: Decimal
    price: Decimal
    status: str
    created_timestamp: datetime
```

**抽象方法签名**:
- `async def _place_open_order(self, level: GridLevel) -> Optional[TrackedOrder]`
- `async def _place_close_order(self, level: GridLevel) -> Optional[TrackedOrder]`
- `def _should_place_order_at_level(self, level: GridLevel, current_price: Decimal) -> bool`

**关键具体方法签名**:
- `async def control_task(self) -> None`
- `def get_open_orders_to_create(self) -> List[GridLevel]`
- `def get_close_orders_to_create(self) -> List[GridLevel]`
- `async def execute_order_operations(self, open_orders: List[GridLevel], close_orders: List[GridLevel], cancel_open: List[str], cancel_close: List[str]) -> None`
- `def _calculate_upper_lower_distribution(self, total_orders: int) -> Tuple[int, int]`

**【强制技术要求】**: 基类必须与交易方向完全解耦，不能包含买卖方向的具体逻辑。

**必须实现的抽象方法完整列表**:
```python
# 核心交易逻辑抽象方法
async def _place_open_order(self, level: GridLevel) -> Optional[TrackedOrder]:
    """执行开仓订单，子类实现具体买入/卖出逻辑"""
    raise NotImplementedError

async def _place_close_order(self, level: GridLevel) -> Optional[TrackedOrder]:
    """执行平仓订单，子类实现具体卖出/买入逻辑"""
    raise NotImplementedError

def _should_place_order_at_level(self, level: GridLevel, current_price: Decimal) -> bool:
    """判断在当前价格是否应该在指定网格层级挂单"""
    raise NotImplementedError

def _get_order_side_for_level(self, level: GridLevel, is_open: bool) -> str:
    """获取指定网格层级和操作类型对应的订单方向"""
    raise NotImplementedError

def _calculate_target_price_for_close(self, open_level: GridLevel) -> Decimal:
    """计算平仓目标价格"""
    raise NotImplementedError
```

#### 3.4.2 多头执行器 (core/long_account_executor.py)

**目的**: 继承基础执行器，实现专门的多头网格交易逻辑。

**实现要点**:
- 继承HedgeGridExecutor并实现抽象方法
- 专注于买入开仓、卖出平仓逻辑
- 实现多头特有的挂单策略
- 支持止盈和风险控制

**关键实现方法签名**:
- `async def _place_open_order(self, level: GridLevel) -> Optional[TrackedOrder]`  # 买入开仓
- `async def _place_close_order(self, level: GridLevel) -> Optional[TrackedOrder]`  # 卖出平仓
- `def _should_place_order_at_level(self, level: GridLevel, current_price: Decimal) -> bool`  # 多头挂单策略
- `def _create_buy_order_candidate(self, level: GridLevel) -> OrderCandidate`
- `def _create_sell_order_candidate(self, level: GridLevel, price: Decimal, amount: Decimal) -> OrderCandidate`

**核心实现任务**: 该文件的主要任务是实现基类HedgeGridExecutor中定义的5个抽象方法，专注于多头网格交易逻辑 (买入开仓 -> 卖出平仓)。

**【强制技术要求】**: 开仓订单必须使用TradeType.BUY，平仓订单必须使用TradeType.SELL。

**【强制技术要求】**: 永续合约订单必须指定PositionAction.OPEN或PositionAction.CLOSE。

#### 3.4.3 空头执行器 (core/short_account_executor.py)

**目的**: 继承基础执行器，实现专门的空头网格交易逻辑。

**实现要点**:
- 继承HedgeGridExecutor并实现抽象方法
- 专注于卖出开仓、买入平仓逻辑
- 实现空头特有的挂单策略
- 支持止盈和风险控制

**关键实现方法签名**:
- `async def _place_open_order(self, level: GridLevel) -> Optional[TrackedOrder]`  # 卖出开仓
- `async def _place_close_order(self, level: GridLevel) -> Optional[TrackedOrder]`  # 买入平仓
- `def _should_place_order_at_level(self, level: GridLevel, current_price: Decimal) -> bool`  # 空头挂单策略
- `def _create_sell_order_candidate(self, level: GridLevel) -> OrderCandidate`
- `def _create_buy_order_candidate(self, level: GridLevel, price: Decimal, amount: Decimal) -> OrderCandidate`

**核心实现任务**: 该文件的主要任务是实现基类HedgeGridExecutor中定义的5个抽象方法，专注于空头网格交易逻辑 (卖出开仓 -> 买入平仓)。

**【强制技术要求】**: 开仓订单必须使用TradeType.SELL，平仓订单必须使用TradeType.BUY。

#### 3.4.4 执行器工厂 (core/executor_factory.py)

**目的**: 根据配置创建合适的执行器实例，支持单账户和双账户模式。

**实现要点**:
- 实现工厂模式创建执行器
- 支持单账户模式（只创建多头执行器）
- 支持双账户模式（创建双执行器和同步控制器）
- 提供执行器配置的深度复制和定制

**关键方法签名**:
- `@staticmethod def create_executors(config: GridExecutorConfig) -> Tuple[List[HedgeGridExecutor], Optional[SyncController]]`
- `@staticmethod def create_single_account_strategy(config: GridExecutorConfig) -> LongAccountExecutor`
- `@staticmethod def create_dual_account_strategy(config: GridExecutorConfig) -> Tuple[LongAccountExecutor, ShortAccountExecutor, SyncController]`

#### 3.4.5 同步控制器 (core/sync_controller.py)

**目的**: 协调双执行器的同步运行，实现风险控制和状态管理。

**实现要点**:
- 管理双执行器的生命周期
- 实现状态同步和风险监控
- 处理异常情况和故障转移
- 提供统一的启动停止接口

**核心数据结构**:
```python
@dataclass
class SyncStatus:
    long_executor_status: RunnableStatus
    short_executor_status: RunnableStatus
    sync_enabled: bool
    last_sync_timestamp: datetime
    errors: List[str]
```

**关键方法签名**:
- `async def start_hedge_strategy(self) -> bool`
- `async def stop_hedge_strategy(self) -> bool`
- `async def sync_monitoring_loop(self) -> None`
- `async def sync_grid_parameters(self) -> None`
- `async def check_hedge_risk(self) -> bool`
- `async def handle_executor_failure(self, failed_executor: str) -> None`

**【强制技术要求】**: 同步控制器必须确保双执行器的原子性操作，避免状态不一致。

### 3.5 监控管理层

#### 3.5.1 统一监控模块 (core/hedge_monitor.py)

**目的**: 提供系统运行状态的实时监控和告警机制。

**实现要点**:
- 监控双账户的连接状态和余额变化
- 跟踪网格执行器的性能指标
- 实现异常检测和告警机制
- 提供Web界面或日志输出

**核心数据结构**:
```python
@dataclass
class MonitorMetrics:
    # 账户指标
    account_a_balance: Decimal
    account_b_balance: Decimal
    total_unrealized_pnl: Decimal
    
    # 执行器指标
    long_open_orders: int
    short_open_orders: int
    completed_grid_cycles: int
    
    # 性能指标
    total_trades: int
    win_rate: Decimal
    avg_profit_per_trade: Decimal
    
    # 风险指标
    max_drawdown: Decimal
    current_leverage: Decimal
    risk_level: str
    
    timestamp: datetime
```

**关键方法签名**:
- `async def start_monitoring(self) -> None`
- `async def collect_metrics(self) -> MonitorMetrics`
- `async def check_alerts(self, metrics: MonitorMetrics) -> List[str]`
- `async def generate_report(self) -> str`
- `def update_performance_metrics(self, trade_result: TradeResult) -> None`

#### 3.5.2 对冲风险控制器 (core/risk_hedge_controller.py)

**目的**: 实现对冲策略的风险管控，包括止损、限仓等功能。

**实现要点**:
- 监控净敞口和风险暴露
- 实现动态止损逻辑
- 检测市场异常和流动性风险
- 提供紧急停机机制

**核心数据结构**:
```python
@dataclass
class RiskMetrics:
    net_position: Decimal  # 净持仓
    gross_exposure: Decimal  # 总敞口
    leverage_ratio: Decimal  # 杠杆比率
    unrealized_pnl: Decimal  # 未实现盈亏
    drawdown_pct: Decimal  # 回撤百分比
    margin_ratio: Decimal  # 保证金比率
    
@dataclass
class RiskLimits:
    max_drawdown_pct: Decimal = Decimal("0.15")
    max_leverage: int = 10
    max_position_imbalance_pct: Decimal = Decimal("0.1")
    min_margin_ratio: Decimal = Decimal("0.2")
```

**关键方法签名**:
- `async def check_risk_limits(self) -> List[str]`
- `async def calculate_risk_metrics(self) -> RiskMetrics`
- `async def should_trigger_stop_loss(self) -> Tuple[bool, str]`
- `async def emergency_shutdown(self, reason: str) -> bool`
- `def update_risk_limits(self, new_limits: RiskLimits) -> None`

**【强制技术要求】**: 风险控制必须在每个交易周期执行，不能跳过。

#### 3.6.0 自定义异常类 (utils/exceptions.py)

**目的**: 定义系统中所有自定义异常类，提供清晰的错误分类和处理。

**必须定义的异常类**:
```python
class GridBotException(Exception):
    """网格机器人基础异常类"""
    pass

class AccountConnectionError(GridBotException):
    """账户连接异常"""
    pass

class InsufficientBalanceError(GridBotException):
    """余额不足异常"""
    pass

class OrderPlacementError(GridBotException):
    """订单下单异常"""
    pass

class GridParameterError(GridBotException):
    """网格参数错误异常"""
    pass

class RiskControlError(GridBotException):
    """风险控制异常"""
    pass

class ConfigurationError(GridBotException):
    """配置错误异常"""
    pass

class SyncControllerError(GridBotException):
    """同步控制器异常"""
    pass

class ATRCalculationError(GridBotException):
    """ATR计算异常"""
    pass

class ExchangeAPIError(GridBotException):
    """交易所API异常"""
    pass
```

**实现要点**:
- 每个异常类都继承自GridBotException
- 支持错误码和详细错误信息
- 提供异常恢复建议

### 3.6 工具库层

#### 3.6.1 日志管理器 (utils/logger.py)

**目的**: 提供统一的日志管理，支持多级别、多输出目标的日志记录。

**实现要点**:
- 使用structlog结合rich库实现结构化和美化日志
- 支持控制台和文件双重输出
- 实现日志轮转和压缩
- 提供结构化日志记录
- 支持敏感信息脱敏

**推荐日志库组合**:
```python
import structlog
from rich.logging import RichHandler
from rich.console import Console
import logging.handlers

# 使用structlog + rich实现美观的结构化日志
# 支持JSON格式文件输出和彩色控制台输出
```

**关键方法签名**:
- `def setup_logger(name: str, level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger`
- `def get_logger(name: str) -> logging.Logger`
- `def mask_sensitive_data(data: dict) -> dict`
- `def log_trade_event(logger: logging.Logger, event_type: str, data: dict) -> None`

**【强制技术要求】**: 绝不能在日志中输出API密钥等敏感信息。

**敏感数据脱敏规则**:
- API密钥: 只显示前4位和后4位，中间用***代替
- 订单ID: 只在调试级别显示完整ID
- 账户余额: 生产环境下进行四舍五入处理
- 价格信息: 允许记录，但需要标注时区

#### 3.6.2 工具函数库 (utils/helpers.py)

**目的**: 提供通用的工具函数和数据处理方法。

**实现要点**:
- 价格和数量的精度处理
- 时间戳转换和时区处理
- 数据验证和错误处理
- 常用数学计算函数

**关键方法签名**:
- `def round_to_precision(value: Decimal, precision: int) -> Decimal`
- `def calculate_percentage_change(old_value: Decimal, new_value: Decimal) -> Decimal`
- `def format_timestamp(timestamp: datetime, timezone: str = "UTC") -> str`
- `def validate_trading_pair(symbol: str) -> bool`
- `def safe_divide(numerator: Decimal, denominator: Decimal, default: Decimal = Decimal("0")) -> Decimal`

#### 3.6.3 订单跟踪器 (utils/order_tracker.py)

**目的**: 跟踪和管理所有订单的生命周期状态。

**实现要点**:
- 维护订单状态映射表
- 提供订单查询和更新接口
- 实现订单状态变更通知
- 支持订单历史记录

**核心数据结构**:
```python
@dataclass
class OrderRecord:
    order_id: str
    account_type: str  # 'LONG' | 'SHORT'
    trading_pair: str
    side: str  # 'BUY' | 'SELL'
    order_type: str
    amount: Decimal
    price: Decimal
    status: str
    grid_level_id: int
    created_timestamp: datetime
    updated_timestamp: datetime
    filled_amount: Decimal = Decimal("0")
    avg_fill_price: Decimal = Decimal("0")
```

**关键方法签名**:
- `def add_order(self, order: OrderRecord) -> None`
- `def update_order_status(self, order_id: str, status: str, filled_amount: Decimal = None) -> bool`
- `def get_order(self, order_id: str) -> Optional[OrderRecord]`
- `def get_orders_by_status(self, status: str) -> List[OrderRecord]`
- `def get_orders_by_account(self, account_type: str) -> List[OrderRecord]`
- `def cleanup_completed_orders(self, keep_days: int = 7) -> int`

### 3.7 主策略脚本

#### 3.7.1 主策略脚本 (hedge_grid_strategy.py)

**目的**: 作为整个系统的入口点，协调所有模块的初始化和运行。

**实现要点**:
- 解析命令行参数和配置文件
- 初始化所有核心模块
- 启动主策略循环
- 处理优雅关闭和异常情况

**关键方法签名**:
- `async def main() -> None`
- `async def initialize_system() -> Tuple[DualAccountManager, SharedGridEngine, List[HedgeGridExecutor]]`
- `async def start_strategy() -> None`
- `async def shutdown_strategy() -> None`
- `def setup_signal_handlers() -> None`
- `async def health_check_loop() -> None`

**主要执行流程**:
1. **环境初始化**: 调用`load_dotenv()`加载.env文件，调用`setup_logger()`初始化日志系统
2. **配置加载**: 调用`DualAccountConfig.load_from_env()`和`GridExecutorConfig.load_from_env()`
3. **账户管理**: 创建`DualAccountManager`实例，调用`initialize_accounts()`和`pre_flight_checks()`
4. **网格引擎**: 创建`SharedGridEngine`实例，调用`initialize_grid_parameters()`
5. **执行器创建**: 调用`ExecutorFactory.create_executors()`根据模式创建执行器
6. **监控启动**: 创建`HedgeMonitor`和`RiskHedgeController`，启动监控循环
7. **策略运行**: 调用`SyncController.start_hedge_strategy()`进入主策略循环
8. **优雅关闭**: 响应SIGINT信号，调用`shutdown_strategy()`进行资源清理

**【强制技术要求】**: 必须实现信号处理器支持CTRL+C优雅关闭。

**【强制技术要求】**: 必须在启动前执行完整的预检流程，确保系统状态正确。

### 3.8 启动脚本层

#### 3.8.1 启动脚本 (scripts/start_hedge_grid.sh)

**目的**: 提供简单的系统启动接口，包含环境检查和进程管理。

**实现要点**:
- 检查Python环境和依赖包
- 验证配置文件完整性
- 启动策略进程并后台运行
- 记录启动日志和PID

**脚本详细功能**:
```bash
#!/bin/bash
# 1. 检查Python版本 (>=3.9)
if ! python3 --version | grep -q "3.9\|3.10\|3.11\|3.12"; then
    echo "Error: Python 3.9+ required"
    exit 1
fi

# 2. 检查虚拟环境和依赖
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found"
    exit 1
fi
source venv/bin/activate
pip check

# 3. 验证配置文件存在性
if [ ! -f ".env" ]; then
    echo "Error: .env file not found"
    exit 1
fi

# 4. 检查PID文件，避免重复启动
PID_FILE="hedge_grid.pid"
if [ -f "$PID_FILE" ]; then
    if ps -p $(cat $PID_FILE) > /dev/null; then
        echo "Error: Strategy already running (PID: $(cat $PID_FILE))"
        exit 1
    fi
fi

# 5. 启动策略进程并记录PID
nohup python3 hedge_grid_strategy.py > logs/strategy.log 2>&1 &
echo $! > $PID_FILE
echo "Strategy started with PID: $(cat $PID_FILE)"
```

#### 3.8.2 停止脚本 (scripts/stop_hedge_grid.sh)

**目的**: 安全停止策略进程，确保资源正确清理。

**脚本详细功能**:
```bash
#!/bin/bash
PID_FILE="hedge_grid.pid"

# 1. 检查PID文件是否存在
if [ ! -f "$PID_FILE" ]; then
    echo "No PID file found. Strategy may not be running."
    exit 1
fi

# 2. 读取PID并检查进程状态
PID=$(cat $PID_FILE)
if ! ps -p $PID > /dev/null; then
    echo "Process $PID not found. Cleaning up PID file."
    rm -f $PID_FILE
    exit 1
fi

# 3. 发送SIGTERM信号进行优雅关闭
echo "Sending graceful shutdown signal to PID: $PID"
kill -TERM $PID

# 4. 等待进程退出 (最多30秒)
for i in {1..30}; do
    if ! ps -p $PID > /dev/null; then
        echo "Strategy stopped gracefully"
        rm -f $PID_FILE
        exit 0
    fi
    sleep 1
done

# 5. 强制终止
echo "Forcing shutdown..."
kill -KILL $PID
rm -f $PID_FILE
echo "Strategy forcefully stopped"
```

#### 3.8.3 状态查询脚本 (scripts/status_hedge_grid.sh)

**目的**: 查询策略运行状态和关键指标。

**脚本详细功能**:
```bash
#!/bin/bash
PID_FILE="hedge_grid.pid"
LOG_FILE="logs/strategy.log"

# 1. 检查进程状态
echo "=== Hedge Grid Strategy Status ==="
if [ -f "$PID_FILE" ]; then
    PID=$(cat $PID_FILE)
    if ps -p $PID > /dev/null; then
        echo "Status: RUNNING (PID: $PID)"
        echo "Started: $(ps -o lstart= -p $PID)"
        echo "CPU Usage: $(ps -o %cpu= -p $PID)%"
        echo "Memory Usage: $(ps -o %mem= -p $PID)%"
    else
        echo "Status: STOPPED (stale PID file)"
    fi
else
    echo "Status: NOT_RUNNING"
fi

# 2. 显示最新日志 (最后20行)
echo -e "\n=== Latest Logs ==="
if [ -f "$LOG_FILE" ]; then
    tail -20 "$LOG_FILE"
else
    echo "No log file found"
fi

# 3. 调用Python脚本获取详细状态
echo -e "\n=== Account Status ==="
python3 -c "
import sys
sys.path.append('.')
from utils.status_checker import get_account_status
print(get_account_status())
" 2>/dev/null || echo "Unable to fetch account status"
```

## IV. 技术约束和实现规范

### 4.1 强制技术要求汇总

1. **异步编程**: 所有交易所交互必须使用ccxt.async_support库
2. **数值精度**: 所有价格和金额计算必须使用Decimal类型
3. **技术指标**: 必须使用pandas_ta库进行技术指标计算
4. **配置管理**: 敏感信息必须使用环境变量，不得硬编码
5. **错误处理**: 每个异步方法都必须包含try-catch异常处理
6. **日志安全**: 绝不能在日志中输出API密钥等敏感信息
7. **状态一致性**: 双执行器必须确保原子性操作，避免状态不一致
8. **风险控制**: 风险检查必须在每个交易周期执行
9. **优雅关闭**: 必须支持CTRL+C信号的优雅关闭处理
10. **预检流程**: 系统启动前必须执行完整的账户和配置预检

### 4.2 代码质量要求

1. **类型注解**: 所有函数参数和返回值必须包含类型注解
2. **文档字符串**: 每个类和公共方法必须包含详细的文档字符串
3. **错误消息**: 异常消息必须清晰描述错误原因和建议解决方案
4. **单元测试**: 核心计算逻辑必须编写对应的单元测试
5. **代码复用**: 优先使用继承和组合，避免重复代码

### 4.3 性能和可靠性要求

1. **连接管理**: 实现交易所连接池和自动重连机制
2. **内存管理**: 定期清理历史订单和日志数据，避免内存泄漏
3. **并发控制**: 使用asyncio.Lock保护共享资源的并发访问
4. **限频控制**: 严格遵守交易所API限频要求
5. **故障恢复**: 实现自动故障检测和恢复机制

## V. 系统集成指导

### 5.1 模块依赖关系

```
主策略脚本 (hedge_grid_strategy.py)
    ↓
配置管理层 (config/)
    ↓
账户管理层 (core/dual_account_manager.py)
    ↓
网格计算层 (core/atr_calculator.py, grid_calculator.py, shared_grid_engine.py)
    ↓
执行器架构层 (core/hedge_grid_executor.py, long_account_executor.py, short_account_executor.py)
    ↓
监控管理层 (core/hedge_monitor.py, risk_hedge_controller.py)
    ↓
工具库层 (utils/)
```

### 5.2 启动序列

1. **环境初始化**: 加载.env配置，设置日志系统
2. **配置验证**: 验证双账户配置和执行器参数
3. **账户连接**: 建立币安API连接，执行预检流程
4. **参数计算**: 计算ATR指标和网格参数
5. **执行器创建**: 根据模式创建单/双执行器
6. **监控启动**: 启动风险控制和性能监控
7. **策略运行**: 进入主循环，开始网格交易
8. **优雅关闭**: 响应关闭信号，清理资源

### 5.3 测试指导

1. **单元测试**: 测试核心计算逻辑（ATR、网格参数计算）
2. **集成测试**: 测试模块间交互（账户管理、执行器协作）
3. **模拟测试**: 使用testnet进行完整策略测试
4. **压力测试**: 测试高频交易和异常情况处理
5. **安全测试**: 验证敏感信息保护和权限控制

## VI. 结语

本工程蓝图为"双账户对冲网格策略"提供了完整的技术实现指导。通过严格遵循这些设计要求和技术约束，AI代码生成器将能够构建出一个高质量、高可靠性的量化交易系统。

每个模块都经过精心设计，确保系统的可扩展性、可维护性和安全性。请在实现过程中严格遵守所有【强制技术要求】，并充分利用现代Python异步编程的优势。

---
*本蓝图版本: 1.0*  
*最后更新: 2025-01-15*