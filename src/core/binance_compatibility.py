"""
币安API兼容性优化模块
针对杠杆分层、持仓模式、下单回报等兼容性问题的优化处理
"""
import asyncio
from decimal import Decimal
from typing import Dict, List, Any, Optional, Union
from loguru import logger

class BinanceAPICompatibilityHandler:
    """币安API兼容性处理器"""
    
    def __init__(self, connector):
        self.connector = connector
        self._leverage_brackets_cache = {}
        self._position_mode_cache = None
        self._symbol_info_cache = {}
        
    async def get_leverage_brackets_safe(self, symbol: str) -> List[Dict[str, Any]]:
        """
        安全获取杠杆分层信息
        
        兼容性处理：
        1. 缓存机制避免重复请求
        2. 数据格式兼容性处理
        3. 异常情况的兜底处理
        
        Args:
            symbol: 交易对
            
        Returns:
            杠杆分层列表，格式兼容处理后的数据
        """
        try:
            # 从缓存获取
            if symbol in self._leverage_brackets_cache:
                logger.debug(f"从缓存获取杠杆分层: {symbol}")
                return self._leverage_brackets_cache[symbol]
            
            # 从API获取
            raw_data = await self.connector.get_leverage_brackets(symbol)
            
            # 兼容性处理：数据格式标准化
            brackets = []
            if raw_data:
                if isinstance(raw_data, list) and len(raw_data) > 0:
                    # 处理币安API返回的数据结构
                    for item in raw_data:
                        if isinstance(item, dict) and item.get('symbol') == symbol:
                            raw_brackets = item.get('brackets', [])
                            # 标准化分层数据格式
                            for bracket in raw_brackets:
                                standard_bracket = {
                                    'bracket': bracket.get('bracket', 0),
                                    'initialLeverage': bracket.get('initialLeverage', 1),
                                    'notionalCap': bracket.get('notionalCap', 0),
                                    'notionalFloor': bracket.get('notionalFloor', 0),
                                    'maintMarginRatio': bracket.get('maintMarginRatio', 0.05),
                                    'cum': bracket.get('cum', 0.0)
                                }
                                brackets.append(standard_bracket)
                            break
            
            # 如果没有获取到数据，提供默认分层
            if not brackets:
                logger.warning(f"未获取到{symbol}的杠杆分层，使用默认分层")
                brackets = self._get_default_leverage_brackets()
            
            # 缓存结果
            self._leverage_brackets_cache[symbol] = brackets
            
            logger.info(f"成功获取杠杆分层: {symbol}, 共{len(brackets)}层")
            return brackets
            
        except Exception as e:
            logger.error(f"获取杠杆分层失败: {e}")
            # 返回默认分层作为兜底
            return self._get_default_leverage_brackets()
    
    def _get_default_leverage_brackets(self) -> List[Dict[str, Any]]:
        """
        获取默认杠杆分层（兜底方案）
        
        Returns:
            默认杠杆分层列表
        """
        return [
            {'bracket': 1, 'initialLeverage': 75, 'notionalCap': 10000, 'notionalFloor': 0, 'maintMarginRatio': 0.005, 'cum': 0.0},
            {'bracket': 2, 'initialLeverage': 50, 'notionalCap': 50000, 'notionalFloor': 10000, 'maintMarginRatio': 0.007, 'cum': 20.0},
            {'bracket': 3, 'initialLeverage': 40, 'notionalCap': 750000, 'notionalFloor': 50000, 'maintMarginRatio': 0.01, 'cum': 170.0},
            {'bracket': 4, 'initialLeverage': 25, 'notionalCap': 1000000, 'notionalFloor': 750000, 'maintMarginRatio': 0.02, 'cum': 7670.0},
            {'bracket': 5, 'initialLeverage': 20, 'notionalCap': 2000000, 'notionalFloor': 1000000, 'maintMarginRatio': 0.025, 'cum': 12670.0},
            {'bracket': 6, 'initialLeverage': 10, 'notionalCap': 5000000, 'notionalFloor': 2000000, 'maintMarginRatio': 0.05, 'cum': 62670.0},
            {'bracket': 7, 'initialLeverage': 5, 'notionalCap': 10000000, 'notionalFloor': 5000000, 'maintMarginRatio': 0.1, 'cum': 312670.0},
            {'bracket': 8, 'initialLeverage': 4, 'notionalCap': 20000000, 'notionalFloor': 10000000, 'maintMarginRatio': 0.125, 'cum': 562670.0},
            {'bracket': 9, 'initialLeverage': 2, 'notionalCap': 50000000, 'notionalFloor': 20000000, 'maintMarginRatio': 0.25, 'cum': 3062670.0},
            {'bracket': 10, 'initialLeverage': 1, 'notionalCap': 9223372036854775807, 'notionalFloor': 50000000, 'maintMarginRatio': 0.5, 'cum': 15562670.0}
        ]
    
    async def ensure_position_mode_safe(self, dual_side: bool = True) -> bool:
        """
        安全确保持仓模式
        
        兼容性处理：
        1. 检查当前模式，避免不必要的切换
        2. 异常处理和重试机制
        3. 缓存机制
        
        Args:
            dual_side: 是否双向持仓
            
        Returns:
            True表示设置成功
        """
        try:
            # 检查缓存
            if self._position_mode_cache is not None:
                if self._position_mode_cache == dual_side:
                    logger.debug(f"持仓模式已是目标模式: {'双向' if dual_side else '单向'}")
                    return True
            
            # 获取当前模式
            current_mode = await self.connector.get_position_mode()
            
            # 如果已是目标模式，无需切换
            if current_mode == dual_side:
                logger.info(f"持仓模式已是目标模式: {'双向' if dual_side else '单向'}")
                self._position_mode_cache = dual_side
                return True
            
            # 切换模式
            logger.info(f"切换持仓模式: {'单向' if current_mode else '双向'} -> {'双向' if dual_side else '单向'}")
            await self.connector.set_position_mode(dual_side)
            
            # 验证切换结果
            new_mode = await self.connector.get_position_mode()
            if new_mode == dual_side:
                logger.info(f"持仓模式切换成功: {'双向' if dual_side else '单向'}")
                self._position_mode_cache = dual_side
                return True
            else:
                logger.error(f"持仓模式切换失败: 期望{'双向' if dual_side else '单向'}, 实际{'双向' if new_mode else '单向'}")
                return False
                
        except Exception as e:
            logger.error(f"设置持仓模式失败: {e}")
            return False
    
    async def set_leverage_safe(self, symbol: str, leverage: int, max_retries: int = 3) -> bool:
        """
        安全设置杠杆
        
        兼容性处理：
        1. 杠杆范围验证
        2. 重试机制
        3. 错误码兼容性处理
        
        Args:
            symbol: 交易对
            leverage: 杠杆倍数
            max_retries: 最大重试次数
            
        Returns:
            True表示设置成功
        """
        try:
            # 杠杆范围验证
            if leverage < 1 or leverage > 125:  # 币安合约最大杠杆一般为125
                logger.error(f"杠杆倍数超出范围: {leverage}, 有效范围: 1-125")
                return False
            
            # 获取杠杆分层信息验证
            brackets = await self.get_leverage_brackets_safe(symbol)
            max_allowed_leverage = max(bracket['initialLeverage'] for bracket in brackets)
            
            if leverage > max_allowed_leverage:
                logger.warning(f"杠杆倍数超出交易对最大限制: {leverage} > {max_allowed_leverage}, 调整为{max_allowed_leverage}")
                leverage = max_allowed_leverage
            
            # 重试机制
            for attempt in range(max_retries):
                try:
                    result = await self.connector.set_leverage(symbol, leverage)
                    logger.info(f"杠杆设置成功: {symbol} = {leverage}x")
                    return True
                    
                except Exception as e:
                    error_msg = str(e)
                    
                    # 兼容性处理：特定错误码的处理
                    if "Leverage" in error_msg and "not valid" in error_msg:
                        logger.warning(f"杠杆{leverage}不被支持，尝试降低杠杆")
                        leverage = max(1, leverage - 5)  # 降低杠杆后重试
                        continue
                    elif "No need to change leverage" in error_msg:
                        logger.info(f"杠杆已是目标值: {leverage}x")
                        return True
                    elif attempt < max_retries - 1:
                        logger.warning(f"设置杠杆失败，第{attempt + 1}次重试: {e}")
                        await asyncio.sleep(1)  # 等待1秒后重试
                        continue
                    else:
                        raise
            
            return False
            
        except Exception as e:
            logger.error(f"设置杠杆失败: {e}")
            return False
    
    async def get_symbol_info_safe(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        安全获取交易对信息
        
        兼容性处理：
        1. 缓存机制
        2. 数据格式标准化
        3. 异常处理
        
        Args:
            symbol: 交易对
            
        Returns:
            交易对信息字典或None
        """
        try:
            # 从缓存获取
            if symbol in self._symbol_info_cache:
                logger.debug(f"从缓存获取交易对信息: {symbol}")
                return self._symbol_info_cache[symbol]
            
            # 从API获取
            symbol_info = await self.connector.get_symbol_info(symbol)
            
            if symbol_info:
                # 标准化数据格式
                standard_info = {
                    'symbol': symbol_info.get('symbol'),
                    'status': symbol_info.get('status'),
                    'baseAsset': symbol_info.get('baseAsset'),
                    'quoteAsset': symbol_info.get('quoteAsset'),
                    'pricePrecision': symbol_info.get('pricePrecision', 8),
                    'quantityPrecision': symbol_info.get('quantityPrecision', 8),
                    'filters': symbol_info.get('filters', [])
                }
                
                # 解析过滤器信息
                filters_info = {}
                for filt in standard_info['filters']:
                    filter_type = filt.get('filterType')
                    if filter_type == 'PRICE_FILTER':
                        filters_info['price'] = {
                            'min': Decimal(filt.get('minPrice', '0')),
                            'max': Decimal(filt.get('maxPrice', '0'))
                        }
                    elif filter_type == 'LOT_SIZE':
                        filters_info['quantity'] = {
                            'min': Decimal(filt.get('minQty', '0')),
                            'max': Decimal(filt.get('maxQty', '0'))
                        }
                    elif filter_type == 'MIN_NOTIONAL':
                        filters_info['notional'] = {
                            'min': Decimal(filt.get('notional', '5'))  # 从API获取真实值
                        }
                
                standard_info['filters_info'] = filters_info
                
                # 缓存结果
                self._symbol_info_cache[symbol] = standard_info
                
                logger.info(f"成功获取交易对信息: {symbol}")
                return standard_info
            else:
                logger.warning(f"未找到交易对信息: {symbol}")
                return None
                
        except Exception as e:
            logger.error(f"获取交易对信息失败: {e}")
            return None
    
    async def place_order_safe(self, symbol: str, side: str, order_type: str, 
                              quantity: Decimal, price: Decimal = None,
                              position_side: str = None, **kwargs) -> Optional[Dict[str, Any]]:
        """
        安全下单
        
        兼容性处理：
        1. 参数验证和格式化
        2. 下单回报标准化
        3. 错误处理和重试
        
        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            quantity: 数量
            price: 价格
            position_side: 持仓方向
            **kwargs: 其他参数
            
        Returns:
            标准化的下单回报或None
        """
        try:
            # 获取交易对信息进行验证
            symbol_info = await self.get_symbol_info_safe(symbol)
            if not symbol_info:
                logger.error(f"获取交易对信息失败，无法下单: {symbol}")
                return None
            
            # 参数验证
            if order_type.upper() == 'LIMIT' and price is None:
                logger.error("限价单必须提供价格")
                return None
            
            # 格式化参数
            formatted_params = {
                'symbol': symbol,
                'side': side.upper(),
                'type': order_type.upper(),
                'quantity': str(quantity)
            }
            
            if price:
                formatted_params['price'] = str(price)
            
            if position_side:
                formatted_params['positionSide'] = position_side.upper()
            
            # 添加其他参数
            formatted_params.update(kwargs)
            
            # 下单
            result = await self.connector.place_order(**formatted_params)
            
            # 标准化下单回报
            standard_result = {
                'orderId': result.get('orderId'),
                'symbol': result.get('symbol'),
                'side': result.get('side'),
                'type': result.get('type'),
                'status': result.get('status'),
                'quantity': Decimal(result.get('origQty', '0')),
                'price': Decimal(result.get('price', '0')) if result.get('price') else None,
                'executedQty': Decimal(result.get('executedQty', '0')),
                'timestamp': result.get('transactTime'),
                'raw': result  # 保留原始数据
            }
            
            logger.info(f"下单成功: {symbol} {side} {quantity} @ {price}")
            return standard_result
            
        except Exception as e:
            logger.error(f"下单失败: {e}")
            return None
    
    def clear_cache(self):
        """清空缓存"""
        self._leverage_brackets_cache.clear()
        self._position_mode_cache = None
        self._symbol_info_cache.clear()
        logger.info("缓存已清空")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康检查结果
        """
        result = {
            'connectivity': False,
            'position_mode': None,
            'leverage_brackets': False,
            'symbol_info': False,
            'timestamp': None
        }
        
        try:
            # 连接性检查
            result['connectivity'] = await self.connector.test_connectivity()
            
            # 持仓模式检查
            try:
                result['position_mode'] = await self.connector.get_position_mode()
            except:
                pass
            
            # 杠杆分层检查
            try:
                brackets = await self.get_leverage_brackets_safe("DOGEUSDC")
                result['leverage_brackets'] = len(brackets) > 0
            except:
                pass
            
            # 交易对信息检查
            try:
                symbol_info = await self.get_symbol_info_safe("DOGEUSDC")
                result['symbol_info'] = symbol_info is not None
            except:
                pass
            
            # 时间戳
            try:
                result['timestamp'] = await self.connector.get_server_time()
            except:
                pass
            
            logger.info(f"健康检查完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return result
