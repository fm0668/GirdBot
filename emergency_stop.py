#!/usr/bin/env python3
"""
紧急停止脚本
用于紧急情况下强制平仓所有持仓和撤销所有挂单
"""

import asyncio
import os
import sys
from decimal import Decimal
from dotenv import load_dotenv

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dual_account_manager import create_dual_account_manager
from base_types import OrderType, TradeType, PositionAction


async def emergency_stop():
    """紧急停止：平仓所有持仓，撤销所有挂单"""
    print("🚨 紧急停止程序")
    print("=" * 50)
    print("⚠️  警告：此操作将强制平仓所有持仓并撤销所有挂单")
    print("⚠️  此操作不可逆，请确认您真的需要执行紧急停止")
    
    # 安全确认
    while True:
        response = input("\n确认执行紧急停止？(YES/no): ").strip()
        if response == "YES":
            break
        elif response.lower() in ['no', 'n', '']:
            print("👋 用户取消紧急停止")
            return
        else:
            print("请输入 YES 确认，或 no 取消")
    
    try:
        print("\n🚨 开始执行紧急停止...")
        
        # 创建双账户管理器
        dual_manager = await create_dual_account_manager()
        trading_pair = os.getenv('TRADING_PAIR', 'DOGE/USDC:USDC')
        
        # 1. 撤销所有挂单
        print("\n📝 撤销所有挂单...")
        await cancel_all_orders(dual_manager, trading_pair)
        
        # 2. 平仓所有持仓
        print("\n📊 平仓所有持仓...")
        await close_all_positions(dual_manager, trading_pair)
        
        # 3. 验证清理结果
        print("\n🔍 验证清理结果...")
        await verify_emergency_stop(dual_manager, trading_pair)
        
        print("\n✅ 紧急停止执行完成")
        
        await dual_manager.close()
        
    except Exception as e:
        print(f"❌ 紧急停止执行失败: {e}")
        import traceback
        traceback.print_exc()


async def cancel_all_orders(dual_manager, trading_pair):
    """撤销所有挂单"""
    try:
        # 获取当前挂单
        long_orders = await dual_manager.long_client.exchange.fetch_open_orders(trading_pair)
        short_orders = await dual_manager.short_client.exchange.fetch_open_orders(trading_pair)
        
        total_orders = len(long_orders) + len(short_orders)
        print(f"   发现 {total_orders} 个挂单需要撤销")
        
        if total_orders == 0:
            print("   ✅ 无挂单需要撤销")
            return
        
        # 并行撤销所有订单
        cancel_tasks = []
        
        # 撤销做多账户订单
        for order in long_orders:
            cancel_tasks.append(
                dual_manager.long_client.cancel_order(
                    "binance_futures", trading_pair, order['id']
                )
            )
        
        # 撤销做空账户订单
        for order in short_orders:
            cancel_tasks.append(
                dual_manager.short_client.cancel_order(
                    "binance_futures", trading_pair, order['id']
                )
            )
        
        # 执行撤单
        results = await asyncio.gather(*cancel_tasks, return_exceptions=True)
        
        # 统计结果
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - success_count
        
        print(f"   ✅ 成功撤销: {success_count} 个")
        if error_count > 0:
            print(f"   ❌ 撤销失败: {error_count} 个")
        
        # 等待撤单完成
        await asyncio.sleep(2)
        
    except Exception as e:
        print(f"   ❌ 撤销挂单异常: {e}")
        raise


async def close_all_positions(dual_manager, trading_pair):
    """平仓所有持仓"""
    try:
        # 获取持仓信息
        long_positions = await dual_manager.long_client.get_position_info(trading_pair)
        short_positions = await dual_manager.short_client.get_position_info(trading_pair)
        
        close_tasks = []
        
        # 处理做多账户持仓
        long_pos = long_positions.get('long_position', Decimal('0'))
        short_pos_in_long = long_positions.get('short_position', Decimal('0'))
        
        if long_pos > 0:
            print(f"   做多账户多头持仓: {long_pos}，执行市价平仓")
            close_tasks.append(
                market_close_position(dual_manager.long_client, trading_pair, "long", long_pos)
            )
        
        if short_pos_in_long > 0:
            print(f"   做多账户空头持仓: {short_pos_in_long}，执行市价平仓")
            close_tasks.append(
                market_close_position(dual_manager.long_client, trading_pair, "short", short_pos_in_long)
            )
        
        # 处理做空账户持仓
        long_pos_in_short = short_positions.get('long_position', Decimal('0'))
        short_pos = short_positions.get('short_position', Decimal('0'))
        
        if long_pos_in_short > 0:
            print(f"   做空账户多头持仓: {long_pos_in_short}，执行市价平仓")
            close_tasks.append(
                market_close_position(dual_manager.short_client, trading_pair, "long", long_pos_in_short)
            )
        
        if short_pos > 0:
            print(f"   做空账户空头持仓: {short_pos}，执行市价平仓")
            close_tasks.append(
                market_close_position(dual_manager.short_client, trading_pair, "short", short_pos)
            )
        
        if not close_tasks:
            print("   ✅ 无持仓需要平仓")
            return
        
        # 执行平仓
        results = await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # 统计结果
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = len(results) - success_count
        
        print(f"   ✅ 成功平仓: {success_count} 个")
        if error_count > 0:
            print(f"   ❌ 平仓失败: {error_count} 个")
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"     错误 {i+1}: {result}")
        
        # 等待平仓完成
        await asyncio.sleep(3)
        
    except Exception as e:
        print(f"   ❌ 平仓异常: {e}")
        raise


async def market_close_position(client, trading_pair, side, amount):
    """市价平仓"""
    try:
        if side == "long":
            # 平多头：卖出
            await client.place_order(
                "binance_futures", trading_pair, OrderType.MARKET,
                TradeType.SELL, amount, Decimal('0'), PositionAction.CLOSE
            )
        else:
            # 平空头：买入
            await client.place_order(
                "binance_futures", trading_pair, OrderType.MARKET,
                TradeType.BUY, amount, Decimal('0'), PositionAction.CLOSE
            )
        
        print(f"     ✅ {side}持仓平仓完成: {amount}")
        
    except Exception as e:
        print(f"     ❌ {side}持仓平仓失败: {e}")
        raise


async def verify_emergency_stop(dual_manager, trading_pair):
    """验证紧急停止结果"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # 检查持仓
            long_positions = await dual_manager.long_client.get_position_info(trading_pair)
            short_positions = await dual_manager.short_client.get_position_info(trading_pair)
            
            total_positions = (
                long_positions.get('long_position', Decimal('0')) +
                long_positions.get('short_position', Decimal('0')) +
                short_positions.get('long_position', Decimal('0')) +
                short_positions.get('short_position', Decimal('0'))
            )
            
            # 检查挂单
            long_orders = await dual_manager.long_client.exchange.fetch_open_orders(trading_pair)
            short_orders = await dual_manager.short_client.exchange.fetch_open_orders(trading_pair)
            
            total_orders = len(long_orders) + len(short_orders)
            
            print(f"   持仓检查: {total_positions}")
            print(f"   挂单检查: {total_orders} 个")
            
            if total_positions == 0 and total_orders == 0:
                print("   ✅ 验证通过：已实现0持仓，0挂单")
                return True
            else:
                if attempt < max_retries - 1:
                    print(f"   ⚠️  验证未通过，重试 ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(3)
                else:
                    print(f"   ❌ 验证失败：仍有持仓={total_positions}，挂单={total_orders}")
                    return False
                    
        except Exception as e:
            print(f"   ❌ 验证异常: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(3)
            else:
                return False
    
    return False


async def main():
    """主函数"""
    load_dotenv()
    
    # 检查环境
    if not os.getenv('BINANCE_LONG_API_KEY') or not os.getenv('BINANCE_SHORT_API_KEY'):
        print("❌ 缺少API密钥配置")
        return
    
    await emergency_stop()


if __name__ == "__main__":
    print("🚨 双账户网格交易系统 - 紧急停止工具")
    print("⚠️  此工具用于紧急情况下强制停止所有交易活动")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 紧急停止被中断")
    except Exception as e:
        print(f"❌ 紧急停止异常: {e}")
