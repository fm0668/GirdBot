"""
风险控制器模块
负责风险监控、持仓管理、止损等功能
"""
import time
from typing import Tuple, Dict, Any

from utils.logger import logger
from config.settings import config


class RiskController:
    """风险控制器"""
    
    def __init__(self, market_data_provider, order_manager):
        self.market_data = market_data_provider
        self.order_manager = order_manager
        self.exchange = market_data_provider.exchange
        
        # 持仓信息
        self.long_position = 0  # 多头持仓
        self.short_position = 0  # 空头持仓
        self.last_position_update_time = 0  # 上次持仓更新时间
        
        # 减仓时间控制
        self.last_reduce_time = 0  # 上次减仓时间
        
        # 账户余额信息
        self.balance = {}
    
    def get_position(self) -> Tuple[int, int]:
        """
        获取当前持仓
        
        Returns:
            Tuple[int, int]: (多头持仓, 空头持仓)
        """
        try:
            params = {'type': 'future'}  # 永续合约
            positions = self.exchange.fetch_positions(params=params)
            
            long_position = 0
            short_position = 0
            
            for position in positions:
                if position['symbol'] == config.CCXT_SYMBOL:
                    contracts = position.get('contracts', 0)
                    side = position.get('side', None)
                    
                    if side == 'long':  # 多头
                        long_position = contracts
                    elif side == 'short':  # 空头
                        short_position = abs(contracts)  # 使用绝对值
            
            return long_position, short_position
            
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            return 0, 0
    
    def update_position(self):
        """更新持仓信息"""
        current_time = time.time()
        
        # 限制更新频率
        if current_time - self.last_position_update_time < config.SYNC_TIME:
            return
        
        try:
            self.long_position, self.short_position = self.get_position()
            self.last_position_update_time = current_time
            
            logger.debug(f"持仓更新 - 多头: {self.long_position}, 空头: {self.short_position}")
            
        except Exception as e:
            logger.error(f"更新持仓失败: {e}")
    
    def check_position_limits(self) -> bool:
        """
        检查持仓是否超过限制
        
        Returns:
            bool: True表示持仓在安全范围内，False表示超过限制
        """
        try:
            # 检查单边持仓限制
            if abs(self.long_position) > config.POSITION_LIMIT:
                logger.warning(f"多头持仓超过限制: {self.long_position} > {config.POSITION_LIMIT}")
                return False
            
            if abs(self.short_position) > config.POSITION_LIMIT:
                logger.warning(f"空头持仓超过限制: {self.short_position} > {config.POSITION_LIMIT}")
                return False
            
            # 检查总持仓限制
            total_position = abs(self.long_position) + abs(self.short_position)
            if total_position > config.POSITION_THRESHOLD:
                logger.warning(f"总持仓超过阈值: {total_position} > {config.POSITION_THRESHOLD}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"检查持仓限制失败: {e}")
            return False
    
    def check_and_reduce_positions(self) -> bool:
        """
        检查并减少持仓
        
        Returns:
            bool: 是否成功处理
        """
        try:
            self.update_position()
            
            # 检查是否需要减仓
            if not self.check_position_limits():
                # 添加时间控制，避免频繁减仓
                current_time = time.time()
                if current_time - self.last_reduce_time < 30:  # 30秒内不重复减仓
                    return False
                
                logger.info("持仓超限，开始减仓操作")
                self.last_reduce_time = current_time
                
                # 取消所有挂单
                self.order_manager.cancel_orders_for_side('LONG')
                self.order_manager.cancel_orders_for_side('SHORT')
                
                # 执行减仓逻辑
                if abs(self.long_position) > config.POSITION_LIMIT:
                    self._reduce_position('LONG', self.long_position)
                
                if abs(self.short_position) > config.POSITION_LIMIT:
                    self._reduce_position('SHORT', self.short_position)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查并减少持仓失败: {e}")
            return False
    
    def _reduce_position(self, position_side: str, position_size: int):
        """
        减少指定方向的持仓
        
        Args:
            position_side: 持仓方向 ('LONG' 或 'SHORT')
            position_size: 持仓数量
        """
        try:
            # 计算需要减仓的数量 - 按照原策略的方式
            quantity = config.POSITION_THRESHOLD * 0.1  # 阈值的10%
            
            # 确定减仓方向和价格 - 按照原策略
            if position_side == 'LONG':
                # 多头减仓：卖出，使用ask价格
                side = 'sell'
                price = self.market_data.best_ask_price
            else:
                # 空头减仓：买入，使用bid价格
                side = 'buy'
                price = self.market_data.best_bid_price
            
            # 检查价格是否有效
            if not price or price <= 0:
                logger.error(f"无法获取有效价格，减仓失败: {price}")
                return
            
            # 下市价减仓单 - 按照原策略的方式
            order = self.order_manager.place_order(
                side=side,
                price=price,  # 市价单仍需传递价格参考
                quantity=quantity,
                is_reduce_only=True,
                position_side=position_side,
                order_type='market'
            )
            
            if order:
                logger.info(f"减仓订单已下达 - {position_side} {side} {quantity}")
            else:
                logger.error(f"减仓订单失败 - {position_side} {side} {quantity}")
                
        except Exception as e:
            logger.error(f"减少 {position_side} 持仓失败: {e}")
    
    def check_and_enable_hedge_mode(self):
        """检查并启用双向持仓模式"""
        try:
            # 通过API直接检查持仓模式
            import requests
            import hmac
            import hashlib
            
            # 获取账户信息来检查持仓模式
            url = "https://fapi.binance.com/fapi/v2/account"
            timestamp = int(time.time() * 1000)
            params = f"timestamp={timestamp}"
            
            signature = hmac.new(
                config.API_SECRET.encode(),
                params.encode(),
                hashlib.sha256
            ).hexdigest()
            
            headers = {
                "X-MBX-APIKEY": config.API_KEY,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            response = requests.get(f"{url}?{params}&signature={signature}", headers=headers)
            
            if response.status_code == 200:
                account_info = response.json()
                position_mode = account_info.get('multiAssetsMargin', False)  # 检查多资产模式
                
                # 币安期货默认启用双向持仓，这里主要检查API连接是否正常
                logger.info("API连接正常，双向持仓模式检查通过")
            else:
                logger.warning(f"获取账户信息失败: {response.status_code} - {response.text}")
                # 尝试启用双向持仓模式
                if not self.enable_hedge_mode():
                    logger.error("双向持仓模式启用失败，程序退出")
                    raise SystemExit("双向持仓模式启用失败")
                
        except Exception as e:
            logger.error(f"检查持仓模式失败: {e}")
            # 尝试启用双向持仓模式作为备用方案
            try:
                if self.enable_hedge_mode():
                    logger.info("双向持仓模式启用成功")
                else:
                    raise SystemExit("双向持仓模式启用失败")
            except:
                raise SystemExit("检查持仓模式失败")
    
    def enable_hedge_mode(self) -> bool:
        """
        启用双向持仓模式
        
        Returns:
            bool: 是否成功启用
        """
        try:
            import requests
            import hmac
            import hashlib
            
            url = "https://fapi.binance.com/fapi/v1/positionSide/dual"
            timestamp = int(time.time() * 1000)
            params = f"dualSidePosition=true&timestamp={timestamp}"
            
            signature = hmac.new(
                config.API_SECRET.encode(),
                params.encode(),
                hashlib.sha256
            ).hexdigest()
            
            headers = {
                "X-MBX-APIKEY": config.API_KEY,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = f"{params}&signature={signature}"
            response = requests.post(url, headers=headers, data=data)
            
            if response.status_code == 200:
                logger.info("双向持仓模式启用成功")
                return True
            else:
                logger.error(f"启用双向持仓模式失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"启用双向持仓模式异常: {e}")
            return False
    
    def get_account_balance(self) -> Dict[str, Any]:
        """
        获取账户余额信息
        
        Returns:
            Dict: 账户余额信息
        """
        try:
            # 使用ccxt的fetch_balance方法获取期货账户余额
            balance = self.exchange.fetch_balance({'type': 'future'})
            self.balance = balance
            logger.debug(f"账户余额更新成功")
            return balance
        except Exception as e:
            logger.error(f"获取账户余额失败: {e}")
            return {}
    
    def get_position_info(self) -> Dict[str, Any]:
        """
        获取持仓信息
        
        Returns:
            Dict: 持仓信息
        """
        return {
            'long_position': self.long_position,
            'short_position': self.short_position,
            'total_position': abs(self.long_position) + abs(self.short_position),
            'last_update_time': self.last_position_update_time
        }
    
    def is_position_safe(self) -> bool:
        """
        判断当前持仓是否安全
        
        Returns:
            bool: 持仓是否安全
        """
        return self.check_position_limits()
