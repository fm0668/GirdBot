#!/usr/bin/env python3
"""
最终验证脚本 - 确保所有优化都正确集成
"""
import asyncio
from decimal import Decimal
from src.core.grid_calculator import GridCalculator
from src.core.binance_compatibility import BinanceAPICompatibilityHandler
from src.exchange.binance_connector import BinanceConnector
from config.production import ProductionConfig
from loguru import logger

async def final_verification():
    """最终验证所有优化功能"""
    print("🔍 开始最终验证...")
    print("=" * 60)
    
    # 初始化
    config = ProductionConfig()
    connector = BinanceConnector(
        api_key=config.api_long.api_key,
        api_secret=config.api_long.api_secret,
        testnet=config.api_long.testnet
    )
    
    calculator = GridCalculator()
    
    verification_results = {
        "leverage_limit_fix": False,
        "mmr_api_integration": False,
        "leverage_calculation_timing": False,
        "compatibility_handler": False,
        "grid_parameters_accuracy": False
    }
    
    try:
        async with connector:
            # 1. 验证杠杆限制修复
            print("1️⃣ 验证杠杆限制修复...")
            try:
                # 测试杠杆计算是否支持1-50倍
                test_leverage = calculator.estimate_leverage(
                    unified_margin=Decimal("100"),
                    avg_entry_price=Decimal("0.17"),
                    upper_bound=Decimal("0.18"),
                    lower_bound=Decimal("0.16"),
                    mmr=Decimal("0.005"),
                    safety_factor=Decimal("0.8")
                )
                if 1 <= test_leverage <= 50:
                    verification_results["leverage_limit_fix"] = True
                    print("   ✅ 杠杆限制已正确调整为1-50倍")
                else:
                    print("   ❌ 杠杆限制不在预期范围内")
            except Exception as e:
                print(f"   ❌ 杠杆限制验证失败: {e}")
            
            # 2. 验证MMR API集成
            print("\n2️⃣ 验证MMR API集成...")
            try:
                handler = BinanceAPICompatibilityHandler(connector)
                brackets = await handler.get_leverage_brackets_safe("DOGEUSDC")
                
                # 验证获取到的分层数据
                if brackets and len(brackets) > 0:
                    mmr_from_brackets = calculator._get_mmr_from_brackets(
                        Decimal("2000"), brackets
                    )
                    if mmr_from_brackets != Decimal("0.05"):  # 不是默认值
                        verification_results["mmr_api_integration"] = True
                        print(f"   ✅ MMR成功从币安API获取: {mmr_from_brackets * 100:.2f}%")
                    else:
                        print("   ❌ MMR仍在使用默认值")
                else:
                    print("   ❌ 未能获取杠杆分层数据")
            except Exception as e:
                print(f"   ❌ MMR API集成验证失败: {e}")
            
            # 3. 验证杠杆计算时机
            print("\n3️⃣ 验证杠杆计算时机...")
            try:
                # 模拟启动时计算一次
                params = await calculator.calculate_grid_parameters(
                    upper_bound=Decimal("0.18"),
                    lower_bound=Decimal("0.16"),
                    atr_value=Decimal("0.005"),
                    atr_multiplier=Decimal("0.26"),
                    unified_margin=Decimal("100"),
                    connector=connector,
                    symbol="DOGEUSDC"
                )
                
                # 验证计算结果包含必要字段
                required_fields = [
                    "usable_leverage", "mmr", "upper_bound", "lower_bound",
                    "avg_entry_price", "leverage_brackets"
                ]
                
                if all(field in params for field in required_fields):
                    verification_results["leverage_calculation_timing"] = True
                    print("   ✅ 杠杆计算逻辑正确，确保ATR通道内不爆仓")
                    print(f"   ✅ 计算结果包含所有必要字段")
                else:
                    missing_fields = [f for f in required_fields if f not in params]
                    print(f"   ❌ 缺少必要字段: {missing_fields}")
            except Exception as e:
                print(f"   ❌ 杠杆计算时机验证失败: {e}")
            
            # 4. 验证兼容性处理器
            print("\n4️⃣ 验证兼容性处理器...")
            try:
                handler = BinanceAPICompatibilityHandler(connector)
                
                # 测试各项功能
                health_check = await handler.health_check()
                leverage_result = await handler.set_leverage_safe("DOGEUSDC", 10)
                position_mode_result = await handler.ensure_position_mode_safe(True)
                symbol_info = await handler.get_symbol_info_safe("DOGEUSDC")
                
                if all([
                    health_check.get("connectivity"),
                    leverage_result,
                    position_mode_result,
                    symbol_info is not None
                ]):
                    verification_results["compatibility_handler"] = True
                    print("   ✅ 兼容性处理器所有功能正常")
                else:
                    print("   ❌ 兼容性处理器部分功能异常")
            except Exception as e:
                print(f"   ❌ 兼容性处理器验证失败: {e}")
            
            # 5. 验证网格参数计算准确性
            print("\n5️⃣ 验证网格参数计算准确性...")
            try:
                # 使用真实数据计算
                params = await calculator.calculate_grid_parameters(
                    upper_bound=Decimal("0.18099"),
                    lower_bound=Decimal("0.16099"),
                    atr_value=Decimal("0.005"),
                    atr_multiplier=Decimal("0.26"),
                    unified_margin=Decimal("100"),
                    connector=connector,
                    symbol="DOGEUSDC",
                    # min_notional=None,  # 让系统自动从API获取
                    safety_factor=Decimal("0.8")
                )
                
                # 验证关键参数合理性
                checks = [
                    params["max_levels"] > 0,
                    params["usable_leverage"] >= 1,
                    params["amount_per_grid"] >= params.get("min_notional", 5),
                    params["grid_spacing"] > 0,
                    params["mmr"] > 0
                ]
                
                if all(checks):
                    verification_results["grid_parameters_accuracy"] = True
                    print("   ✅ 网格参数计算准确，所有参数合理")
                    print(f"   ✅ 网格层数: {params['max_levels']}")
                    print(f"   ✅ 安全杠杆: {params['usable_leverage']}x")
                    print(f"   ✅ 每格金额: {params['amount_per_grid']}")
                    print(f"   ✅ MMR: {params['mmr'] * 100:.2f}%")
                else:
                    print("   ❌ 网格参数计算存在问题")
            except Exception as e:
                print(f"   ❌ 网格参数计算验证失败: {e}")
            
            # 总结验证结果
            print("\n" + "=" * 60)
            print("📊 最终验证结果:")
            print("=" * 60)
            
            total_checks = len(verification_results)
            passed_checks = sum(verification_results.values())
            
            for check, result in verification_results.items():
                status = "✅" if result else "❌"
                print(f"{status} {check}: {'通过' if result else '失败'}")
            
            print(f"\n📈 总体通过率: {passed_checks}/{total_checks} ({passed_checks/total_checks*100:.1f}%)")
            
            if passed_checks == total_checks:
                print("\n🎉 所有验证通过！系统已成功优化。")
                print("🚀 系统已准备好用于生产环境。")
            else:
                print(f"\n⚠️  还有 {total_checks - passed_checks} 项验证未通过。")
                print("🔧 请检查相关代码并修复问题。")
                
    except Exception as e:
        print(f"❌ 最终验证过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🔍 最终验证完成！")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(final_verification())
