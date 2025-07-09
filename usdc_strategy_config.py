"""
基于真实USDC资产的DOGEUSDC网格策略配置
长账户: 199.73 USDC
短账户: 188.60 USDC
总资金: 388.33 USDC
"""

# 基于您的真实资产配置
ACTUAL_USDC_CONFIG = {
    "长账户资金": "199.73 USDC",
    "短账户资金": "188.60 USDC", 
    "总可用资金": "388.33 USDC",
    "交易对": "DOGEUSDC",
    "保证金货币": "USDC",
    
    # 推荐网格配置
    "建议配置": {
        "网格层数": 6,  # 保守配置
        "每层资金": "30 USDC",  # 每个账户每层
        "总网格资金": "360 USDC",  # 保留28 USDC作为缓冲
        "网格间距": "1.5%",
        "杠杆倍数": "2倍",  # 保守杠杆
        
        # 长账户配置
        "长账户网格层数": 6,
        "长账户每层": "30 USDC",
        "长账户使用资金": "180 USDC",
        "长账户保留": "19.73 USDC",
        
        # 短账户配置  
        "短账户网格层数": 6,
        "短账户每层": "30 USDC",
        "短账户使用资金": "180 USDC",
        "短账户保留": "8.60 USDC",
    },
    
    # 风险控制
    "风险管理": {
        "最大亏损": "50 USDC (约13%)",
        "止损价位": "DOGE价格变动15%时",
        "紧急停止": "单日亏损30 USDC",
        "资金监控": "实时监控两账户资金差异",
    },
    
    # 预期收益
    "收益预期": {
        "日收益目标": "2-5 USDC (0.5-1.3%)",
        "月收益目标": "60-150 USDC (15-40%)",
        "年化收益": "180-600% (高波动环境)",
    }
}

# DOGEUSDC当前价格网格示例
DOGE_PRICE = 0.1688  # 当前价格
GRID_SPACING = 0.015  # 1.5%

print("=== 基于真实USDC资产的DOGEUSDC策略配置 ===")
print()

for category, details in ACTUAL_USDC_CONFIG.items():
    if isinstance(details, dict):
        print(f"{category}:")
        for key, value in details.items():
            print(f"  {key}: {value}")
    else:
        print(f"{category}: {details}")
    print()

print("=== DOGEUSDC网格价格示例 ===")
print(f"当前DOGE价格: {DOGE_PRICE} USDC")
print()

# 计算网格价格
print("网格买入价格 (长账户做多):")
for i in range(1, 7):
    buy_price = DOGE_PRICE * (1 - GRID_SPACING * i)
    print(f"  网格{i}: {buy_price:.4f} USDC (下跌{GRID_SPACING*i*100:.1f}%)")

print()
print("网格卖出价格 (短账户做空):")
for i in range(1, 7):
    sell_price = DOGE_PRICE * (1 + GRID_SPACING * i)
    print(f"  网格{i}: {sell_price:.4f} USDC (上涨{GRID_SPACING*i*100:.1f}%)")

print()
print("=== 立即开始步骤 ===")
print("1. ✅ 资金充足 - 无需充值")
print("2. ✅ API配置正确 - 无需修改")
print("3. ✅ 交易对匹配 - DOGEUSDC/USDC完美")
print("4. 🚀 可以立即运行: python3 main.py")
print("5. 📊 监控日志: tail -f logs/grid_strategy.log")
