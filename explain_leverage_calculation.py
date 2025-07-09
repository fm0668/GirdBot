#!/usr/bin/env python3
"""
详细解释杠杆倍数计算和每格网格金额的逻辑
"""

import asyncio
import sys
import os
from decimal import Decimal
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.append('/root/GirdBot')

from src.core.atr_analyzer import ATRAnalyzer
from src.core.grid_calculator import GridCalculator
from src.exchange.binance_connector import BinanceConnector
from config.production import ProductionConfig


async def explain_leverage_and_grid_amount():
    """详细解释杠杆倍数计算和每格网格金额"""
    
    print("=" * 80)
    print("杠杆倍数计算和每格网格金额详细解释")
    print("=" * 80)
    
    # 初始化配置
    config = ProductionConfig()
    
    # 创建连接器
    connector = BinanceConnector(
        api_key=config.api_long.api_key,
        api_secret=config.api_long.api_secret,
        testnet=config.api_long.testnet
    )
    
    # 创建组件
    atr_analyzer = ATRAnalyzer(period=14, multiplier=2.0)
    grid_calculator = GridCalculator()
    
    try:
        # 连接到交易所
        await connector.connect()
        print("✓ 已连接到币安交易所")
        
        symbol = "DOGEUSDC"
        print(f"✓ 分析交易对: {symbol}")
        
        # 获取数据
        klines = await connector.get_klines(symbol=symbol, interval="1h", limit=64)
        atr_value = await atr_analyzer.calculate_atr(klines)
        upper_bound, lower_bound, _ = await atr_analyzer.calculate_atr_channel(klines)
        current_price = Decimal(str(klines[-1][4]))
        
        print(f"✓ 当前价格: {current_price:.8f}")
        print(f"✓ ATR值: {atr_value:.8f}")
        print(f"✓ ATR上轨: {upper_bound:.8f}")
        print(f"✓ ATR下轨: {lower_bound:.8f}")
        
        # 模拟数据
        unified_margin = Decimal("1000")  # 假设有1000 USDC可用保证金
        atr_multiplier = Decimal("0.26")
        grid_spacing = atr_value * atr_multiplier
        
        print(f"✓ 统一保证金: {unified_margin} USDC")
        print(f"✓ 网格间距: {grid_spacing:.8f}")
        
        print("\n" + "=" * 80)
        print("1. 杠杆倍数计算详解")
        print("=" * 80)
        
        # 1. 平均入场价格计算
        avg_entry_price = (upper_bound + lower_bound) / Decimal("2")
        print(f"\n【步骤1：计算平均入场价格】")
        print(f"公式: avg_entry_price = (upper_bound + lower_bound) / 2")
        print(f"计算: ({upper_bound:.8f} + {lower_bound:.8f}) / 2 = {avg_entry_price:.8f}")
        
        # 2. 维持保证金率（简化）
        mmr = Decimal("0.05")  # 假设5%
        print(f"\n【步骤2：维持保证金率】")
        print(f"MMR (维持保证金率): {mmr * 100:.1f}%")
        print(f"说明: 这是交易所要求的最低保证金比例，防止爆仓")
        
        # 3. 多头理论最大杠杆计算
        print(f"\n【步骤3：多头理论最大杠杆计算】")
        print(f"公式: max_leverage_long = 1 / (1 + mmr - lower_bound/avg_entry_price)")
        
        long_factor = Decimal("1") + mmr - (lower_bound / avg_entry_price)
        max_leverage_long = Decimal("1") / long_factor if long_factor > 0 else Decimal("1")
        
        print(f"long_factor = 1 + {mmr:.3f} - ({lower_bound:.8f}/{avg_entry_price:.8f})")
        print(f"long_factor = 1 + {mmr:.3f} - {lower_bound / avg_entry_price:.6f}")
        print(f"long_factor = {long_factor:.6f}")
        print(f"max_leverage_long = 1 / {long_factor:.6f} = {max_leverage_long:.2f}")
        
        print(f"\n解释:")
        print(f"• 多头最怕价格下跌到下轨，所以要确保即使价格跌到{lower_bound:.6f}也不会爆仓")
        print(f"• 价格跌幅 = (当前价 - 下轨) / 当前价 = {((avg_entry_price - lower_bound) / avg_entry_price * 100):.2f}%")
        print(f"• 考虑5%维持保证金要求，安全杠杆不能超过{max_leverage_long:.1f}倍")
        
        # 4. 空头理论最大杠杆计算
        print(f"\n【步骤4：空头理论最大杠杆计算】")
        print(f"公式: max_leverage_short = 1 / (upper_bound/avg_entry_price - 1 + mmr)")
        
        short_factor = (upper_bound / avg_entry_price) - Decimal("1") + mmr
        max_leverage_short = Decimal("1") / short_factor if short_factor > 0 else Decimal("1")
        
        print(f"short_factor = ({upper_bound:.8f}/{avg_entry_price:.8f}) - 1 + {mmr:.3f}")
        print(f"short_factor = {upper_bound / avg_entry_price:.6f} - 1 + {mmr:.3f}")
        print(f"short_factor = {short_factor:.6f}")
        print(f"max_leverage_short = 1 / {short_factor:.6f} = {max_leverage_short:.2f}")
        
        print(f"\n解释:")
        print(f"• 空头最怕价格上涨到上轨，所以要确保即使价格涨到{upper_bound:.6f}也不会爆仓")
        print(f"• 价格涨幅 = (上轨 - 当前价) / 当前价 = {((upper_bound - avg_entry_price) / avg_entry_price * 100):.2f}%")
        print(f"• 考虑5%维持保证金要求，安全杠杆不能超过{max_leverage_short:.1f}倍")
        
        # 5. 最终安全杠杆
        conservative_leverage = min(max_leverage_long, max_leverage_short)
        safety_factor = Decimal("0.8")
        usable_leverage = int(conservative_leverage * safety_factor)
        usable_leverage = max(1, usable_leverage)
        
        print(f"\n【步骤5：确定最终安全杠杆】")
        print(f"保守杠杆 = min(多头最大杠杆, 空头最大杠杆)")
        print(f"保守杠杆 = min({max_leverage_long:.2f}, {max_leverage_short:.2f}) = {conservative_leverage:.2f}")
        print(f"")
        print(f"安全系数 = {safety_factor} (留20%安全边际)")
        print(f"可用杠杆 = int({conservative_leverage:.2f} × {safety_factor}) = {usable_leverage}")
        print(f"")
        print(f"最终确定杠杆倍数: {usable_leverage}倍")
        
        print(f"\n【为什么是动态计算？】")
        print(f"1. 不同的ATR通道宽度 → 不同的价格风险范围 → 不同的安全杠杆")
        print(f"2. 不同的当前价格位置 → 不同的上下轨距离 → 不同的风险敞口")
        print(f"3. 不同的维持保证金率 → 不同的爆仓临界点 → 不同的杠杆限制")
        print(f"4. 市场波动性变化时，ATR值变化，通道宽度变化，杠杆也需要调整")
        
        print("\n" + "=" * 80)
        print("2. 每格网格金额计算详解")
        print("=" * 80)
        
        # 计算网格层数
        price_range = upper_bound - lower_bound
        max_levels = int(price_range / grid_spacing)
        max_levels = max(1, max_levels)
        
        print(f"\n【步骤1：计算可用资金总额】")
        print(f"总名义价值 = 统一保证金 × 可用杠杆")
        print(f"总名义价值 = {unified_margin} × {usable_leverage} = {unified_margin * usable_leverage} USDC")
        
        total_notional = unified_margin * Decimal(str(usable_leverage))
        
        print(f"\n【步骤2：计算网格层数】")
        print(f"价格区间 = 上轨 - 下轨 = {upper_bound:.8f} - {lower_bound:.8f} = {price_range:.8f}")
        print(f"网格层数 = 价格区间 / 网格间距 = {price_range:.8f} / {grid_spacing:.8f} = {max_levels}")
        
        print(f"\n【步骤3：计算每格金额】")
        print(f"每格金额 = 总名义价值 / 网格层数")
        print(f"每格金额 = {total_notional} / {max_levels} = {total_notional / max_levels:.2f} USDC")
        
        amount_per_grid = total_notional / max_levels
        
        print(f"\n【步骤4：验证最小名义价值要求】")
        min_notional = Decimal("10")  # 假设最小10 USDC
        print(f"币安要求每笔交易最少: {min_notional} USDC")
        print(f"我们每格金额: {amount_per_grid:.2f} USDC")
        
        if amount_per_grid >= min_notional:
            print(f"✓ 满足最小名义价值要求")
        else:
            print(f"❌ 不满足最小名义价值要求，需要调整网格间距")
            print(f"解决方案: 增大ATR倍数 → 增大网格间距 → 减少网格层数 → 增加每格金额")
        
        print("\n" + "=" * 80)
        print("3. 实际网格部署示例")
        print("=" * 80)
        
        print(f"\n【资金分配示例】")
        print(f"假设账户有 {unified_margin} USDC，使用 {usable_leverage} 倍杠杆:")
        print(f"")
        print(f"总可用资金: {total_notional} USDC")
        print(f"网格层数: {max_levels} 层")
        print(f"每层投入: {amount_per_grid:.2f} USDC")
        print(f"")
        
        # 计算单个网格的数量示例
        example_prices = [lower_bound + (grid_spacing * i) for i in range(min(5, max_levels))]
        
        print(f"【前5个网格示例】")
        for i, price in enumerate(example_prices):
            quantity = amount_per_grid / price
            print(f"网格{i+1}: 价格={price:.6f}, 金额={amount_per_grid:.2f} USDC, 数量={quantity:.4f} DOGE")
        
        print(f"\n【风险控制机制】")
        print(f"1. 杠杆限制: 最大{usable_leverage}倍，确保价格在ATR通道内不会爆仓")
        print(f"2. 分散投资: {max_levels}个网格分散风险，不把鸡蛋放在一个篮子里")
        print(f"3. 动态调整: 市场波动变化时，重新计算杠杆和金额")
        print(f"4. 安全边际: 使用80%的理论最大杠杆，留20%安全缓冲")
        
        print(f"\n【总结】")
        print(f"• 杠杆倍数: 基于ATR通道风险动态计算，范围1-20倍")
        print(f"• 每格金额: 基于可用资金和网格层数平均分配")
        print(f"• 风险可控: 确保在最坏情况下也不会爆仓")
        print(f"• 资金高效: 在安全前提下最大化资金利用率")
        
    except Exception as e:
        print(f"❌ 计算过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await connector.close()
        print("\n✓ 连接已关闭")


if __name__ == "__main__":
    asyncio.run(explain_leverage_and_grid_amount())
