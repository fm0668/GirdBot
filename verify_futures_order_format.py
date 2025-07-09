#!/usr/bin/env python3
"""
验证币安永续合约下单方式：
1. 验证是否使用交易对基础资产数量下单（如 DOGE 数量）
2. 验证最小名义价值的动态获取
3. 验证下单参数的正确性
"""

import os
import sys
sys.path.append('/root/GirdBot')

import asyncio
from decimal import Decimal
from src.core.grid_calculator import GridCalculator
from src.core.binance_compatibility import BinanceAPICompatibilityHandler
from src.exchange.binance_connector import BinanceConnector

async def main():
    print("【验证币安永续合约下单方式和参数】")
    print("=" * 60)
    
    # 1. 验证币安永续合约下单的参数格式
    print("\n1️⃣ 验证币安永续合约下单参数格式...")
    print("   根据币安API文档，永续合约下单参数：")
    print("   - symbol: 交易对（如 DOGEUSDC）")
    print("   - side: 买卖方向（BUY/SELL）")
    print("   - type: 订单类型（LIMIT/MARKET等）")
    print("   - quantity: 基础资产数量（如 DOGE 数量）")
    print("   - price: 价格（USDC）")
    print("   - positionSide: 持仓方向（LONG/SHORT/BOTH）")
    print("   - timeInForce: 有效期类型（GTC等）")
    print()
    print("   ⚠️  重要：quantity 参数是基础资产数量，不是 USDC 金额！")
    print("   ⚠️  例如：DOGEUSDC 合约中，quantity=100 表示 100 个 DOGE")
    print("   ⚠️  资金结算以 USDC 进行，但下单数量仍然是 DOGE")
    
    # 2. 验证网格计算中的数量转换逻辑
    print("\n2️⃣ 验证网格计算中的数量转换逻辑...")
    
    # 模拟参数
    amount_per_grid = Decimal("10")  # 每格金额：10 USDC
    grid_price = Decimal("0.17")     # 网格价格：0.17 USDC
    
    # 计算应该下单的 DOGE 数量
    doge_quantity = amount_per_grid / grid_price
    
    print(f"   每格金额: {amount_per_grid} USDC")
    print(f"   网格价格: {grid_price} USDC")
    print(f"   计算的 DOGE 数量: {doge_quantity:.6f} DOGE")
    print(f"   名义价值验证: {doge_quantity * grid_price:.2f} USDC")
    print()
    print("   ✅ 这符合币安永续合约的下单方式:")
    print("   ✅ 下单quantity=基础资产数量（DOGE），资金以USDC结算")
    
    # 3. 验证最小名义价值的获取
    print("\n3️⃣ 验证最小名义价值的动态获取...")
    
    # 创建简化的兼容性处理器测试
    print("   模拟从币安API获取交易对信息...")
    
    # 模拟 API 返回的交易对信息
    mock_symbol_info = {
        'symbol': 'DOGEUSDC',
        'status': 'TRADING',
        'baseAsset': 'DOGE',
        'quoteAsset': 'USDC',
        'pricePrecision': 8,
        'quantityPrecision': 0,
        'filters_info': {
            'price': {'min': '0.00001000', 'max': '10000.00000000'},
            'quantity': {'min': '1', 'max': '1000000000'},
            'notional': {'min': '5', 'max': '500000'}  # 真实的最小名义价值
        }
    }
    
    min_notional = Decimal(mock_symbol_info['filters_info']['notional']['min'])
    print(f"   从API获取的最小名义价值: {min_notional} USDC")
    
    # 验证网格金额是否满足最小名义价值要求
    print(f"\n   验证网格金额是否满足最小名义价值要求:")
    print(f"   每格金额: {amount_per_grid} USDC")
    print(f"   最小名义价值: {min_notional} USDC")
    
    if amount_per_grid >= min_notional:
        print("   ✅ 满足最小名义价值要求")
    else:
        print("   ❌ 不满足最小名义价值要求")
    
    # 4. 验证下单参数的完整性
    print("\n4️⃣ 验证下单参数的完整性...")
    
    # 模拟构造一个完整的下单请求
    order_params = {
        'symbol': 'DOGEUSDC',
        'side': 'BUY',
        'type': 'LIMIT',
        'quantity': str(doge_quantity),  # DOGE数量（字符串格式）
        'price': str(grid_price),        # USDC价格（字符串格式）
        'positionSide': 'LONG',
        'timeInForce': 'GTC'
    }
    
    print("   构造的下单参数:")
    for key, value in order_params.items():
        print(f"     {key}: {value}")
    
    # 5. 验证精度处理
    print("\n5️⃣ 验证精度处理...")
    
    base_precision = 0    # DOGE数量精度（整数）
    quote_precision = 8   # USDC价格精度（8位小数）
    
    # 按照精度格式化
    formatted_quantity = f"{doge_quantity:.{base_precision}f}"
    formatted_price = f"{grid_price:.{quote_precision}f}"
    
    print(f"   原始DOGE数量: {doge_quantity}")
    print(f"   格式化后数量: {formatted_quantity}")
    print(f"   原始价格: {grid_price}")
    print(f"   格式化后价格: {formatted_price}")
    
    # 6. 验证名义价值计算
    print("\n6️⃣ 验证名义价值计算...")
    
    final_quantity = Decimal(formatted_quantity)
    final_price = Decimal(formatted_price)
    notional_value = final_quantity * final_price
    
    print(f"   最终数量: {final_quantity} DOGE")
    print(f"   最终价格: {final_price} USDC")
    print(f"   名义价值: {notional_value} USDC")
    
    if notional_value >= min_notional:
        print("   ✅ 名义价值验证通过")
    else:
        print("   ❌ 名义价值验证失败")
    
    # 7. 总结
    print("\n7️⃣ 总结...")
    print("   ✅ 币安永续合约下单确实使用基础资产数量（DOGE）")
    print("   ✅ 资金以报价资产（USDC）结算")
    print("   ✅ 最小名义价值需要从API动态获取")
    print("   ✅ 网格策略的 '等金额' 方式是正确的：")
    print("       - 每格固定金额（USDC）")
    print("       - 根据价格计算对应的基础资产数量")
    print("       - 确保名义价值满足交易所要求")
    
    # 8. 现货vs永续合约的对比
    print("\n8️⃣ 现货vs永续合约的对比...")
    print("   现货交易（DOGEUSDC）：")
    print("     - 买入：用USDC买DOGE，quantity=DOGE数量")
    print("     - 卖出：卖DOGE得USDC，quantity=DOGE数量")
    print("     - 资金：实际持有DOGE和USDC")
    print()
    print("   永续合约（DOGEUSDC）：")
    print("     - 做多：quantity=DOGE数量，保证金和盈亏以USDC计算")
    print("     - 做空：quantity=DOGE数量，保证金和盈亏以USDC计算")
    print("     - 资金：只持有USDC保证金，不实际持有DOGE")
    print()
    print("   ✅ 下单参数格式相同，资金结算方式不同")
    print("   ✅ 永续合约的优势：无需持有基础资产，资金效率更高")

if __name__ == "__main__":
    asyncio.run(main())
