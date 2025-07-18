"""
实盘启动前安全检查
确保所有配置正确，API连接正常，账户余额充足
"""

import asyncio
import os
from decimal import Decimal
from dotenv import load_dotenv
import ccxt.async_support as ccxt

from config.grid_executor_config import GridExecutorConfig
from config.dual_account_config import DualAccountConfig
from utils.logger import get_logger


class PreLaunchChecker:
    """启动前检查器"""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.exchange_a = None
        self.exchange_b = None
        self.check_results = {}
    
    async def run_all_checks(self):
        """运行所有检查"""
        print("\n" + "="*80)
        print("🔍 实盘启动前安全检查")
        print("="*80)
        
        checks = [
            ("环境变量检查", self.check_environment_variables),
            ("API连接检查", self.check_api_connections),
            ("账户余额检查", self.check_account_balances),
            ("交易对检查", self.check_trading_pair),
            ("配置参数检查", self.check_configuration),
            ("网络连接检查", self.check_network_connectivity)
        ]
        
        all_passed = True
        
        for check_name, check_func in checks:
            print(f"\n📋 {check_name}")
            print("-" * 60)
            try:
                result = await check_func()
                self.check_results[check_name] = result
                
                if result['success']:
                    print(f"✅ 通过: {result['message']}")
                    if result.get('details'):
                        for detail in result['details']:
                            print(f"   • {detail}")
                else:
                    print(f"❌ 失败: {result['message']}")
                    if result.get('details'):
                        for detail in result['details']:
                            print(f"   • {detail}")
                    all_passed = False
                    
            except Exception as e:
                print(f"❌ 异常: {e}")
                self.check_results[check_name] = {'success': False, 'message': str(e)}
                all_passed = False
        
        # 显示总结
        self.print_summary(all_passed)
        
        # 清理
        await self.cleanup()
        
        return all_passed
    
    async def check_environment_variables(self):
        """检查环境变量"""
        try:
            load_dotenv()
            
            required_vars = [
                'BINANCE_API_KEY_A', 'BINANCE_SECRET_KEY_A',
                'BINANCE_API_KEY_B', 'BINANCE_SECRET_KEY_B',
                'TRADING_PAIR', 'TARGET_PROFIT_RATE',
                'MAX_OPEN_ORDERS', 'ORDER_FREQUENCY'
            ]
            
            missing_vars = []
            present_vars = []
            
            for var in required_vars:
                value = os.getenv(var)
                if not value:
                    missing_vars.append(var)
                else:
                    present_vars.append(f"{var}: {'***' if 'KEY' in var else value}")
            
            success = len(missing_vars) == 0
            
            details = present_vars
            if missing_vars:
                details.append(f"缺少变量: {', '.join(missing_vars)}")
            
            return {
                'success': success,
                'message': f"环境变量检查{'通过' if success else '失败'}",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"环境变量检查失败: {e}"}
    
    async def check_api_connections(self):
        """检查API连接"""
        try:
            # 创建交易所连接
            self.exchange_a = ccxt.binance({
                'apiKey': os.getenv('BINANCE_API_KEY_A'),
                'secret': os.getenv('BINANCE_SECRET_KEY_A'),
                'sandbox': os.getenv('TESTNET_ENABLED', 'false').lower() == 'true',
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
            
            self.exchange_b = ccxt.binance({
                'apiKey': os.getenv('BINANCE_API_KEY_B'),
                'secret': os.getenv('BINANCE_SECRET_KEY_B'),
                'sandbox': os.getenv('TESTNET_ENABLED', 'false').lower() == 'true',
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
            
            # 测试连接
            await self.exchange_a.load_markets()
            await self.exchange_b.load_markets()
            
            # 测试API权限
            account_a = await self.exchange_a.fetch_balance()
            account_b = await self.exchange_b.fetch_balance()
            
            details = [
                f"账户A连接: 成功",
                f"账户B连接: 成功",
                f"测试网络: {'是' if os.getenv('TESTNET_ENABLED', 'false').lower() == 'true' else '否'}",
                f"API权限: 正常"
            ]
            
            return {
                'success': True,
                'message': "API连接检查通过",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"API连接失败: {e}"}
    
    async def check_account_balances(self):
        """检查账户余额"""
        try:
            if not self.exchange_a or not self.exchange_b:
                return {'success': False, 'message': "交易所连接未建立"}
            
            balance_a = await self.exchange_a.fetch_balance()
            balance_b = await self.exchange_b.fetch_balance()
            
            # 获取USDC余额
            usdc_a = balance_a.get('USDC', {}).get('free', 0)
            usdc_b = balance_b.get('USDC', {}).get('free', 0)
            
            # 最小余额要求
            min_balance = 100  # USDC
            
            details = [
                f"账户A余额: {usdc_a} USDC",
                f"账户B余额: {usdc_b} USDC",
                f"总余额: {usdc_a + usdc_b} USDC",
                f"最小要求: {min_balance} USDC"
            ]
            
            success = usdc_a >= min_balance and usdc_b >= min_balance
            
            if not success:
                details.append("⚠️ 余额不足，建议至少100 USDC每个账户")
            
            return {
                'success': success,
                'message': f"账户余额检查{'通过' if success else '失败'}",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"余额检查失败: {e}"}
    
    async def check_trading_pair(self):
        """检查交易对"""
        try:
            if not self.exchange_a:
                return {'success': False, 'message': "交易所连接未建立"}
            
            trading_pair = os.getenv('TRADING_PAIR')
            
            # 检查交易对是否存在
            markets = await self.exchange_a.load_markets()
            
            if trading_pair not in markets:
                return {
                    'success': False,
                    'message': f"交易对 {trading_pair} 不存在",
                    'details': [f"可用交易对数量: {len(markets)}"]
                }
            
            market = markets[trading_pair]
            
            # 获取当前价格
            ticker = await self.exchange_a.fetch_ticker(trading_pair)
            
            details = [
                f"交易对: {trading_pair}",
                f"当前价格: {ticker['last']}",
                f"24h涨跌: {ticker['percentage']:.2f}%",
                f"最小订单量: {market['limits']['amount']['min']}",
                f"价格精度: {market['precision']['price']}"
            ]
            
            return {
                'success': True,
                'message': "交易对检查通过",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"交易对检查失败: {e}"}
    
    async def check_configuration(self):
        """检查配置参数"""
        try:
            config = GridExecutorConfig.load_from_env()
            dual_config = DualAccountConfig.load_from_env()
            
            # 验证配置
            config_errors = config.validate_parameters()
            dual_config_valid = dual_config.validate_config()
            
            details = [
                f"交易对: {config.trading_pair}",
                f"最大挂单数: {config.max_open_orders}",
                f"订单频率: {config.order_frequency}秒",
                f"目标利润率: {config.target_profit_rate}",
                f"最大杠杆: {config.leverage}",
                f"配置验证: {'通过' if not config_errors and dual_config_valid else '失败'}"
            ]
            
            if config_errors:
                details.extend([f"配置错误: {error}" for error in config_errors])
            
            success = not config_errors and dual_config_valid
            
            return {
                'success': success,
                'message': f"配置参数检查{'通过' if success else '失败'}",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"配置检查失败: {e}"}
    
    async def check_network_connectivity(self):
        """检查网络连接"""
        try:
            if not self.exchange_a:
                return {'success': False, 'message': "交易所连接未建立"}
            
            # 测试网络延迟
            import time
            start_time = time.time()
            await self.exchange_a.fetch_status()
            latency = (time.time() - start_time) * 1000
            
            # 测试服务器时间
            server_time = await self.exchange_a.fetch_time()
            local_time = int(time.time() * 1000)
            time_diff = abs(server_time - local_time)
            
            details = [
                f"网络延迟: {latency:.0f}ms",
                f"时间差: {time_diff}ms",
                f"连接状态: 正常"
            ]
            
            # 检查延迟和时间差
            success = latency < 1000 and time_diff < 5000  # 1秒延迟，5秒时间差
            
            if not success:
                if latency >= 1000:
                    details.append("⚠️ 网络延迟过高")
                if time_diff >= 5000:
                    details.append("⚠️ 时间同步偏差过大")
            
            return {
                'success': success,
                'message': f"网络连接检查{'通过' if success else '失败'}",
                'details': details
            }
            
        except Exception as e:
            return {'success': False, 'message': f"网络检查失败: {e}"}
    
    def print_summary(self, all_passed: bool):
        """打印检查总结"""
        print("\n" + "="*80)
        print("📊 检查总结")
        print("="*80)
        
        total_checks = len(self.check_results)
        passed_checks = sum(1 for result in self.check_results.values() if result['success'])
        failed_checks = total_checks - passed_checks
        
        print(f"总检查项: {total_checks}")
        print(f"通过: {passed_checks}")
        print(f"失败: {failed_checks}")
        print(f"成功率: {(passed_checks/total_checks)*100:.1f}%")
        
        if all_passed:
            print("\n🎉 所有检查都通过了！可以安全启动实盘策略。")
        else:
            print("\n⚠️ 部分检查失败，请修复问题后再启动策略。")
            print("\n❌ 失败的检查:")
            for check_name, result in self.check_results.items():
                if not result['success']:
                    print(f"   • {check_name}: {result['message']}")
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.exchange_a:
                await self.exchange_a.close()
            if self.exchange_b:
                await self.exchange_b.close()
        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")


async def main():
    """主函数"""
    checker = PreLaunchChecker()
    success = await checker.run_all_checks()
    
    if success:
        print(f"\n✅ 启动前检查完成，可以运行: python3 run_live_strategy.py")
    else:
        print(f"\n❌ 启动前检查失败，请修复问题后重试")
    
    return success


if __name__ == "__main__":
    asyncio.run(main())
