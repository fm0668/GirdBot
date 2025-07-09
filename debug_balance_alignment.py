#!/usr/bin/env python3
"""
调试余额对齐问题
"""
import asyncio
import os
from decimal import Decimal
from dotenv import load_dotenv

from config.production import ProductionConfig
from src.core.dual_account_manager import DualAccountManager

async def debug_balance_alignment():
    """调试余额对齐状态"""
    print("🔍 调试余额对齐状态...")
    
    # 加载环境变量
    load_dotenv()
    
    # 创建配置
    config = ProductionConfig()
    
    # 创建双账户管理器
    long_config = {
        "api_key": config.api_long.api_key,
        "api_secret": config.api_long.api_secret,
        "testnet": config.api_long.testnet
    }
    
    short_config = {
        "api_key": config.api_short.api_key,
        "api_secret": config.api_short.api_secret,
        "testnet": config.api_short.testnet
    }
    
    dual_manager = DualAccountManager(long_config, short_config)
    
    try:
        # 初始化
        await dual_manager.initialize()
        
        # 同步账户信息
        long_info, short_info = await dual_manager.sync_account_info()
        
        print("=" * 60)
        print("📊 长账户信息")
        print("=" * 60)
        print(f"钱包余额: {long_info.balance}")
        print(f"可用余额: {long_info.available_balance}")
        print(f"保证金余额: {long_info.position_value}")
        print(f"未实现盈亏: {long_info.unrealized_pnl}")
        print(f"持仓数量: {len(long_info.positions)}")
        
        for pos in long_info.positions:
            print(f"  持仓: {pos.symbol} {pos.side} {pos.size} @ {pos.entry_price}")
        
        print("\n" + "=" * 60)
        print("📊 短账户信息")
        print("=" * 60)
        print(f"钱包余额: {short_info.balance}")
        print(f"可用余额: {short_info.available_balance}")
        print(f"保证金余额: {short_info.position_value}")
        print(f"未实现盈亏: {short_info.unrealized_pnl}")
        print(f"持仓数量: {len(short_info.positions)}")
        
        for pos in short_info.positions:
            print(f"  持仓: {pos.symbol} {pos.side} {pos.size} @ {pos.entry_price}")
        
        print("\n" + "=" * 60)
        print("⚖️ 余额对齐检查")
        print("=" * 60)
        
        # 检查余额对齐
        alignment = await dual_manager.check_balance_alignment("DOGEUSDC")
        print(f"长账户可用余额: {alignment['long_balance']}")
        print(f"短账户可用余额: {alignment['short_balance']}")
        print(f"余额差异: {alignment['difference']}")
        print(f"余额比率: {alignment['ratio']}")
        print(f"是否对齐: {alignment['is_aligned']}")
        
        # 计算总资金对齐
        total_long = long_info.balance
        total_short = short_info.balance
        total_diff = abs(total_long - total_short)
        total_ratio = min(total_long, total_short) / max(total_long, total_short) if max(total_long, total_short) > 0 else 0
        
        print(f"\n📊 总资金对齐检查:")
        print(f"长账户总资金: {total_long}")
        print(f"短账户总资金: {total_short}")
        print(f"总资金差异: {total_diff}")
        print(f"总资金比率: {total_ratio}")
        print(f"总资金是否对齐: {total_ratio > 0.9}")
        
        # 净持仓检查
        long_net_position = sum(pos.size * (1 if pos.side == "LONG" else -1) for pos in long_info.positions)
        short_net_position = sum(pos.size * (1 if pos.side == "LONG" else -1) for pos in short_info.positions)
        net_total_position = long_net_position + short_net_position
        
        print(f"\n📊 净持仓检查:")
        print(f"长账户净持仓: {long_net_position}")
        print(f"短账户净持仓: {short_net_position}")
        print(f"总净持仓: {net_total_position}")
        print(f"是否对冲: {abs(net_total_position) < 10}")  # 允许10个币的误差
        
        # 健康检查
        print("\n" + "=" * 60)
        print("🏥 健康检查")
        print("=" * 60)
        
        health = await dual_manager.health_check("DOGEUSDC")
        print(f"整体健康: {health['is_healthy']}")
        print(f"长账户连接: {health['long_connection']}")
        print(f"短账户连接: {health['short_connection']}")
        print(f"余额对齐: {health['balance_aligned']}")
        print(f"错误列表: {health['errors']}")
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await dual_manager.close()

if __name__ == "__main__":
    asyncio.run(debug_balance_alignment())
