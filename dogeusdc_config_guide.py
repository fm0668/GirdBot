"""
DOGEUSDC 网格策略配置建议
基于当前价格 0.168840 USDT
"""

# 推荐配置参数
DOGEUSDC_CONFIG = {
    "交易对": "DOGEUSDC",
    "当前价格": "0.168840 USDT",
    
    # 网格参数建议
    "网格层数": 8,  # 推荐6-10层
    "网格间距": "1.5%",  # DOGE波动较大，建议1-2%
    "每层资金": "100-200 USDT",  # 根据总资金调整
    
    # 风险控制
    "最大持仓": "2000 USDT per account",  # 单账户最大持仓
    "止损阈值": "15%",  # 总资金止损
    "ATR周期": 14,
    "ATR倍数": 1.5,  # DOGE适中波动
    
    # 账户分配
    "长账户资金": "建议1000-5000 USDT",
    "短账户资金": "建议1000-5000 USDT",
    "杠杆倍数": "2-3倍",  # 保守杠杆
    
    # 网格价格范围示例（基于0.169价格）
    "网格上边界": "0.185 USDT (+9.5%)",
    "网格下边界": "0.152 USDT (-10%)",
    "网格间距价格": "0.0025 USDT (约1.5%)"
}

# 资金配置示例
CAPITAL_EXAMPLES = {
    "保守型": {
        "总资金": "2000 USDT",
        "每账户": "1000 USDT", 
        "网格层数": 6,
        "每层资金": "150 USDT",
        "杠杆": "2倍"
    },
    
    "标准型": {
        "总资金": "10000 USDT",
        "每账户": "5000 USDT",
        "网格层数": 8, 
        "每层资金": "600 USDT",
        "杠杆": "3倍"
    },
    
    "积极型": {
        "总资金": "50000 USDT",
        "每账户": "25000 USDT",
        "网格层数": 10,
        "每层资金": "2500 USDT", 
        "杠杆": "3倍"
    }
}

print("=== DOGEUSDC 网格策略配置建议 ===")
print()
for key, value in DOGEUSDC_CONFIG.items():
    print(f"{key}: {value}")

print("\n=== 资金配置示例 ===")
for level, config in CAPITAL_EXAMPLES.items():
    print(f"\n{level}:")
    for param, val in config.items():
        print(f"  {param}: {val}")
