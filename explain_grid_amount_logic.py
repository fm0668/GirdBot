#!/usr/bin/env python3
"""
详细解释网格金额计算逻辑
"""
from decimal import Decimal

def demonstrate_grid_amount_calculation():
    """演示网格金额计算逻辑"""
    print("=" * 80)
    print("网格金额计算逻辑详细解释")
    print("=" * 80)
    
    # 模拟参数
    unified_margin = Decimal("100")  # 统一保证金 100 USDC
    usable_leverage = 12  # 可用杠杆 12倍
    upper_bound = Decimal("0.18099")  # 价格上轨
    lower_bound = Decimal("0.16099")  # 价格下轨
    atr_value = Decimal("0.005")  # ATR值
    atr_multiplier = Decimal("0.26")  # ATR倍数
    min_notional = Decimal("10")  # 最小名义价值 10 USDC
    
    print(f"📊 初始参数:")
    print(f"  统一保证金: {unified_margin} USDC")
    print(f"  可用杠杆: {usable_leverage}x")
    print(f"  价格上轨: {upper_bound}")
    print(f"  价格下轨: {lower_bound}")
    print(f"  ATR值: {atr_value}")
    print(f"  初始ATR倍数: {atr_multiplier}")
    print(f"  最小名义价值要求: {min_notional} USDC")
    
    # 1. 计算总名义价值（这个不变）
    total_notional = unified_margin * usable_leverage
    print(f"\n💰 总名义价值计算:")
    print(f"  total_notional = {unified_margin} × {usable_leverage} = {total_notional} USDC")
    
    # 2. 演示调整过程
    print(f"\n🔄 网格层数调整过程:")
    
    iteration = 0
    while True:
        iteration += 1
        
        # 计算网格间距
        grid_spacing = atr_value * atr_multiplier
        
        # 计算网格层数
        price_range = upper_bound - lower_bound
        max_levels = int(price_range / grid_spacing)
        max_levels = max(1, max_levels)
        
        # 计算每格金额
        amount_per_grid = total_notional / max_levels
        
        print(f"\n  第{iteration}次迭代:")
        print(f"    ATR倍数: {atr_multiplier:.3f}")
        print(f"    网格间距: {atr_value} × {atr_multiplier:.3f} = {grid_spacing:.6f}")
        print(f"    价格区间: {upper_bound} - {lower_bound} = {price_range:.5f}")
        print(f"    网格层数: {price_range:.5f} ÷ {grid_spacing:.6f} = {max_levels}")
        print(f"    每格金额: {total_notional} ÷ {max_levels} = {amount_per_grid:.2f} USDC")
        
        # 检查是否满足最小名义价值要求
        if amount_per_grid >= min_notional:
            print(f"    ✅ 满足最小名义价值要求: {amount_per_grid:.2f} >= {min_notional}")
            break
        else:
            print(f"    ❌ 不满足最小名义价值要求: {amount_per_grid:.2f} < {min_notional}")
            print(f"    🔧 需要调整: 增大ATR倍数 → 增大网格间距 → 减少网格层数 → 增大每格金额")
            
            # 增大ATR倍数
            atr_multiplier *= Decimal("1.1")
            
            if atr_multiplier > Decimal("5.0"):
                print(f"    ⚠️  ATR倍数过大({atr_multiplier:.3f})，停止调整")
                break
    
    print(f"\n🎯 最终结果:")
    print(f"  网格层数: {max_levels}")
    print(f"  每格金额: {amount_per_grid:.2f} USDC")
    print(f"  网格间距: {grid_spacing:.6f}")
    print(f"  ATR倍数: {atr_multiplier:.3f}")
    
    # 3. 解释为什么要这样调整
    print(f"\n💡 调整逻辑解释:")
    print(f"  1. 问题根源: 每格金额太小，不满足币安最小名义价值要求")
    print(f"  2. 解决思路: 减少网格层数，让每格金额变大")
    print(f"  3. 具体方法: 增大ATR倍数 → 增大网格间距 → 减少网格层数")
    print(f"  4. 数学关系:")
    print(f"     • 网格层数 = 价格区间 ÷ 网格间距")
    print(f"     • 网格间距 = ATR值 × ATR倍数")
    print(f"     • 每格金额 = 总名义价值 ÷ 网格层数")
    print(f"  5. 因此: ATR倍数↑ → 网格间距↑ → 网格层数↓ → 每格金额↑")

def demonstrate_quantity_conversion():
    """演示数量转换逻辑"""
    print(f"\n" + "=" * 80)
    print("数量转换逻辑详细解释")
    print("=" * 80)
    
    # 模拟数据
    amount_per_grid = Decimal("80")  # 每格金额 80 USDC
    prices = [Decimal("0.16099"), Decimal("0.17099"), Decimal("0.18099")]  # 不同价格水平
    
    print(f"📊 每格金额: {amount_per_grid} USDC")
    print(f"\n🔄 在不同价格水平下的数量转换:")
    
    for i, price in enumerate(prices, 1):
        quantity = amount_per_grid / price
        notional_value = quantity * price
        
        print(f"\n  第{i}个网格:")
        print(f"    价格: {price}")
        print(f"    数量计算: {amount_per_grid} ÷ {price} = {quantity:.0f} 个DOGE")
        print(f"    验证名义价值: {quantity:.0f} × {price} = {notional_value:.2f} USDC")
        print(f"    ✅ 每格名义价值始终保持 {amount_per_grid} USDC")
    
    print(f"\n💡 为什么要转换为数量?")
    print(f"  1. 币安API下单需要指定数量(quantity)，而不是金额")
    print(f"  2. 不同价格水平下，相同的USDC金额对应不同的DOGE数量")
    print(f"  3. 通过 '数量 = 金额 ÷ 价格' 转换，确保每格使用相同的资金量")
    print(f"  4. 这样可以实现等金额网格，而不是等数量网格")
    
    print(f"\n🎯 实际交易中的应用:")
    print(f"  • 做多单: 在价格下跌时买入，价格越低买入数量越多")
    print(f"  • 做空单: 在价格上涨时卖出，价格越高卖出数量越少")
    print(f"  • 风险控制: 每格使用相同的资金量，风险均匀分布")

def demonstrate_real_world_example():
    """演示实际交易示例"""
    print(f"\n" + "=" * 80)
    print("实际交易示例")
    print("=" * 80)
    
    # 模拟实际参数
    amount_per_grid = Decimal("80")  # 每格80 USDC
    current_price = Decimal("0.17099")  # 当前价格
    
    # 网格价格
    grid_prices = [
        Decimal("0.16099"),  # 下方网格1
        Decimal("0.16599"),  # 下方网格2
        Decimal("0.17099"),  # 当前价格
        Decimal("0.17599"),  # 上方网格1
        Decimal("0.18099"),  # 上方网格2
    ]
    
    print(f"📊 网格配置:")
    print(f"  每格金额: {amount_per_grid} USDC")
    print(f"  当前价格: {current_price}")
    
    print(f"\n🔄 网格层级详情:")
    print(f"  {'价格':<10} {'数量':<12} {'类型':<8} {'名义价值':<10} {'操作'}")
    print(f"  {'-'*50}")
    
    for price in grid_prices:
        quantity = amount_per_grid / price
        notional = quantity * price
        
        if price < current_price:
            grid_type = "做多"
            action = "买入挂单"
        elif price > current_price:
            grid_type = "做空"
            action = "卖出挂单"
        else:
            grid_type = "当前"
            action = "参考价格"
        
        print(f"  {price:<10} {quantity:<12.0f} {grid_type:<8} {notional:<10.2f} {action}")
    
    print(f"\n💡 交易逻辑:")
    print(f"  • 价格下跌触发做多网格: 以低价买入更多数量")
    print(f"  • 价格上涨触发做空网格: 以高价卖出较少数量")
    print(f"  • 每格使用相同资金量: 风险均匀分布")
    print(f"  • 双账户对冲: 一个账户做多，另一个账户做空")

if __name__ == "__main__":
    demonstrate_grid_amount_calculation()
    demonstrate_quantity_conversion()
    demonstrate_real_world_example()
    
    print(f"\n" + "=" * 80)
    print("总结")
    print("=" * 80)
    print(f"1. 增大ATR倍数的作用:")
    print(f"   • 解决每格金额过小的问题")
    print(f"   • 确保满足币安最小名义价值要求")
    print(f"   • 通过减少网格层数来增大每格金额")
    print(f"")
    print(f"2. 转换为数量的原因:")
    print(f"   • 币安API下单需要指定数量参数")
    print(f"   • 实现等金额网格策略")
    print(f"   • 在不同价格水平下保持相同的资金使用量")
    print(f"   • 确保风险均匀分布")
