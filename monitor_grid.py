#!/usr/bin/env python3
"""
双账户网格交易系统监控脚本
独立的监控工具，用于查看系统状态和持仓情况
"""

import asyncio
import os
import sys
from decimal import Decimal
from dotenv import load_dotenv

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dual_account_manager import create_dual_account_manager
from base_types import PriceType


async def monitor_system_status():
    """监控系统状态"""
    print("👁️  双账户网格交易系统监控")
    print("=" * 60)
    
    try:
        # 创建双账户管理器
        dual_manager = await create_dual_account_manager()
        
        trading_pair = os.getenv('TRADING_PAIR', 'DOGE/USDC:USDC')
        quote_asset = os.getenv('QUOTE_ASSET', 'USDC')
        
        while True:
            try:
                print(f"\n📊 系统状态监控 - {asyncio.get_event_loop().time()}")
                print("-" * 60)
                
                # 1. 连接状态
                print("🔗 连接状态:")
                long_ws = dual_manager.long_client.is_websocket_connected()
                short_ws = dual_manager.short_client.is_websocket_connected()
                print(f"   做多账户WebSocket: {'✅' if long_ws else '❌'}")
                print(f"   做空账户WebSocket: {'✅' if short_ws else '❌'}")
                
                # 2. 账户余额
                print("\n💰 账户余额:")
                dual_balance = await dual_manager.get_dual_account_balance()
                print(f"   做多账户: {dual_balance.long_account_balance} {quote_asset}")
                print(f"   做空账户: {dual_balance.short_account_balance} {quote_asset}")
                print(f"   总余额: {dual_balance.total_balance} {quote_asset}")
                print(f"   余额比例: {dual_balance.balance_ratio:.3f}")
                print(f"   余额平衡: {'✅' if dual_balance.is_balanced() else '⚠️'}")
                
                # 3. 当前价格
                print(f"\n💹 {trading_pair} 价格:")
                try:
                    current_price = await dual_manager.long_client.get_price(
                        "binance_futures", trading_pair, PriceType.MidPrice
                    )
                    bid_price = await dual_manager.long_client.get_price(
                        "binance_futures", trading_pair, PriceType.BestBid
                    )
                    ask_price = await dual_manager.long_client.get_price(
                        "binance_futures", trading_pair, PriceType.BestAsk
                    )
                    
                    print(f"   当前价格: {current_price}")
                    print(f"   买一价格: {bid_price}")
                    print(f"   卖一价格: {ask_price}")
                    print(f"   买卖价差: {ask_price - bid_price}")
                    
                except Exception as e:
                    print(f"   ❌ 获取价格失败: {e}")
                
                # 4. 持仓情况
                print(f"\n📈 持仓情况:")
                try:
                    position_summary = await dual_manager.get_position_summary(trading_pair)
                    
                    print(f"   做多账户多头: {position_summary['long_account'].get('long_position', 0)}")
                    print(f"   做多账户空头: {position_summary['long_account'].get('short_position', 0)}")
                    print(f"   做空账户多头: {position_summary['short_account'].get('long_position', 0)}")
                    print(f"   做空账户空头: {position_summary['short_account'].get('short_position', 0)}")
                    print(f"   总多头持仓: {position_summary['total_long_position']}")
                    print(f"   总空头持仓: {position_summary['total_short_position']}")
                    print(f"   净持仓: {position_summary['net_position']}")
                    print(f"   对冲状态: {'✅' if position_summary['is_hedged'] else '⚠️'}")
                    
                except Exception as e:
                    print(f"   ❌ 获取持仓失败: {e}")
                
                # 5. 挂单情况
                print(f"\n📝 挂单情况:")
                try:
                    long_orders = await dual_manager.long_client.exchange.fetch_open_orders(trading_pair)
                    short_orders = await dual_manager.short_client.exchange.fetch_open_orders(trading_pair)
                    
                    print(f"   做多账户挂单: {len(long_orders)} 个")
                    print(f"   做空账户挂单: {len(short_orders)} 个")
                    print(f"   总挂单数: {len(long_orders) + len(short_orders)} 个")
                    
                    # 显示挂单详情
                    if long_orders:
                        print("   做多账户挂单详情:")
                        for order in long_orders[:3]:  # 只显示前3个
                            side = order['side']
                            amount = order['amount']
                            price = order['price']
                            print(f"     {side} {amount} @ {price}")
                    
                    if short_orders:
                        print("   做空账户挂单详情:")
                        for order in short_orders[:3]:  # 只显示前3个
                            side = order['side']
                            amount = order['amount']
                            price = order['price']
                            print(f"     {side} {amount} @ {price}")
                            
                except Exception as e:
                    print(f"   ❌ 获取挂单失败: {e}")
                
                # 6. 风险指标
                print(f"\n⚠️  风险指标:")
                try:
                    # 计算风险指标
                    net_position = abs(position_summary.get('net_position', Decimal('0')))
                    total_position = (
                        position_summary.get('total_long_position', Decimal('0')) +
                        position_summary.get('total_short_position', Decimal('0'))
                    )
                    
                    # 资金使用率
                    if dual_balance.total_balance > 0:
                        # 假设平均杠杆20倍
                        estimated_margin = total_position * current_price / 20 if 'current_price' in locals() else Decimal('0')
                        margin_usage = estimated_margin / dual_balance.total_balance * 100
                        print(f"   预估保证金使用率: {margin_usage:.1f}%")
                    
                    print(f"   净持仓风险: {net_position}")
                    print(f"   总持仓规模: {total_position}")
                    
                    # 风险等级
                    if net_position > Decimal('1000'):
                        risk_level = "🔴 高风险"
                    elif net_position > Decimal('500'):
                        risk_level = "🟡 中风险"
                    else:
                        risk_level = "🟢 低风险"
                    
                    print(f"   风险等级: {risk_level}")
                    
                except Exception as e:
                    print(f"   ❌ 计算风险指标失败: {e}")
                
                print("\n" + "=" * 60)
                print("按 Ctrl+C 退出监控")
                
                # 等待30秒后刷新
                await asyncio.sleep(30)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ 监控异常: {e}")
                await asyncio.sleep(5)
        
    except Exception as e:
        print(f"❌ 监控系统启动失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if 'dual_manager' in locals():
            await dual_manager.close()


async def quick_status():
    """快速状态检查"""
    print("⚡ 快速状态检查")
    print("-" * 30)
    
    try:
        dual_manager = await create_dual_account_manager()
        trading_pair = os.getenv('TRADING_PAIR', 'DOGE/USDC:USDC')
        
        # 余额
        dual_balance = await dual_manager.get_dual_account_balance()
        print(f"💰 总余额: {dual_balance.total_balance} USDC")
        
        # 持仓
        position_summary = await dual_manager.get_position_summary(trading_pair)
        print(f"📈 净持仓: {position_summary['net_position']}")
        
        # 挂单
        long_orders = await dual_manager.long_client.exchange.fetch_open_orders(trading_pair)
        short_orders = await dual_manager.short_client.exchange.fetch_open_orders(trading_pair)
        print(f"📝 总挂单: {len(long_orders) + len(short_orders)} 个")
        
        # 价格
        current_price = await dual_manager.long_client.get_price(
            "binance_futures", trading_pair, PriceType.MidPrice
        )
        print(f"💹 当前价格: {current_price}")
        
        await dual_manager.close()
        
    except Exception as e:
        print(f"❌ 快速检查失败: {e}")


async def main():
    """主函数"""
    load_dotenv()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        await quick_status()
    else:
        await monitor_system_status()


if __name__ == "__main__":
    print("👁️  双账户网格交易系统监控工具")
    print("使用方法:")
    print("  python monitor_grid.py          # 持续监控")
    print("  python monitor_grid.py --quick  # 快速检查")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 监控已退出")
    except Exception as e:
        print(f"❌ 监控工具异常: {e}")
