# 网格间距配置说明

## 配置文件位置
- 主配置文件: `config/base_config.py`
- 生产环境配置: `config/production.py`

## 网格间距参数
```python
# 在 TradingConfig 类中
grid_spacing_multiplier: float = 0.26  # 网格间距ATR倍数（可调参数）
```

## 参数调整建议

### 1. 保守策略 (0.5 - 1.0)
- 网格间距较大，网格层数较少
- 适合波动较小的市场
- 单次盈利较高，但交易频率低

### 2. 平衡策略 (0.2 - 0.5) 
- 网格间距适中，网格层数适中
- 适合正常波动的市场
- 平衡盈利和交易频率

### 3. 激进策略 (0.1 - 0.2)
- 网格间距较小，网格层数较多
- 适合波动较大的市场
- 单次盈利较低，但交易频率高

### 4. 当前默认设置
- ATR倍数: 0.26
- 策略类型: 平衡策略
- 适用场景: 大部分市场条件

## 修改方法

### 方法1: 直接修改配置文件
```python
# 在 config/base_config.py 中找到 TradingConfig 类
class TradingConfig:
    # ...其他配置...
    grid_spacing_multiplier: float = 0.26  # 修改这个值
```

### 方法2: 通过环境变量
```bash
export GRID_SPACING_MULTIPLIER=0.3
```

### 方法3: 在策略运行时动态调整
```python
# 在 main.py 中
strategy_config.grid_spacing_percent = Decimal("0.3")
```

## 测试和验证
运行测试脚本查看效果：
```bash
python3 compare_grid_spacing_methods.py
```

## 注意事项
1. 修改参数后需要重启策略
2. 建议在模拟环境中测试新参数
3. 根据市场条件和风险承受能力调整
4. 过小的间距可能导致过于频繁的交易
5. 过大的间距可能错过交易机会
