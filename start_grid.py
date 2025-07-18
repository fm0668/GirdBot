#!/usr/bin/env python3
"""
双账户网格交易系统启动脚本
简化的启动入口，包含环境检查和安全确认
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dual_grid_controller import DualGridController


def check_environment():
    """检查环境配置"""
    print("🔍 检查环境配置...")
    
    # 加载环境变量
    load_dotenv()
    
    # 检查必需的API密钥
    required_keys = [
        'BINANCE_LONG_API_KEY',
        'BINANCE_LONG_API_SECRET',
        'BINANCE_SHORT_API_KEY',
        'BINANCE_SHORT_API_SECRET'
    ]
    
    missing_keys = []
    for key in required_keys:
        if not os.getenv(key):
            missing_keys.append(key)
    
    if missing_keys:
        print("❌ 缺少必需的API密钥:")
        for key in missing_keys:
            print(f"   {key}")
        print("\n请在.env文件中配置这些密钥")
        return False
    
    # 检查交易对配置
    trading_pair = os.getenv('TRADING_PAIR')
    if not trading_pair:
        print("❌ 缺少交易对配置 (TRADING_PAIR)")
        return False
    
    # 显示当前配置
    print("✅ 环境配置检查通过")
    print(f"\n📋 当前配置:")
    print(f"   交易对: {trading_pair}")
    print(f"   计价货币: {os.getenv('QUOTE_ASSET', 'USDC')}")
    print(f"   测试网: {os.getenv('USE_TESTNET', 'true')}")
    print(f"   最大杠杆: {os.getenv('MAX_LEVERAGE', '20')}x")
    print(f"   ATR周期: {os.getenv('ATR_PERIOD', '14')}")
    print(f"   目标利润率: {float(os.getenv('TARGET_PROFIT_RATE', '0.002'))*100:.2f}%")
    print(f"   最大开仓订单: {os.getenv('MAX_OPEN_ORDERS', '5')}")
    
    return True


def safety_confirmation():
    """安全确认"""
    print("\n⚠️  安全确认")
    print("=" * 50)
    print("双账户网格交易系统将执行以下操作:")
    print("1. 🧹 清理所有现有持仓和挂单")
    print("2. ⚖️  平衡两个账户的余额")
    print("3. 📊 计算网格参数")
    print("4. 🚀 启动双向网格交易")
    print("5. 👁️  持续监控和风险控制")
    print("\n注意事项:")
    print("- 系统将自动平仓所有现有持仓")
    print("- 系统将撤销所有现有挂单")
    print("- 请确保两个账户都有足够的USDC余额")
    print("- 建议先在测试网环境下验证")
    
    # 检查是否为测试网
    is_testnet = os.getenv('USE_TESTNET', 'true').lower() == 'true'
    if is_testnet:
        print("\n✅ 当前为测试网环境")
    else:
        print("\n⚠️  当前为生产环境，请谨慎操作！")
    
    print("\n" + "=" * 50)
    
    while True:
        response = input("确认启动系统？(yes/no): ").lower().strip()
        if response in ['yes', 'y']:
            return True
        elif response in ['no', 'n']:
            return False
        else:
            print("请输入 yes 或 no")


async def main():
    """主函数"""
    print("🚀 双账户网格交易系统启动器")
    print("=" * 50)
    
    try:
        # 1. 检查环境
        if not check_environment():
            print("❌ 环境检查失败，请修复配置后重试")
            return
        
        # 2. 安全确认
        if not safety_confirmation():
            print("👋 用户取消启动")
            return
        
        print("\n🚀 启动双账户网格交易系统...")
        print("=" * 50)
        
        # 3. 创建并运行控制器
        controller = DualGridController()
        await controller.run()
        
    except KeyboardInterrupt:
        print("\n🛑 用户中断系统")
    except Exception as e:
        print(f"❌ 系统启动失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n👋 系统已退出")


if __name__ == "__main__":
    # 设置事件循环策略 (Windows兼容性)
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # 运行主程序
    asyncio.run(main())
