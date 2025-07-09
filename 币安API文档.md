# 币安API文档



# 下单 (TRADE)

## 接口描述

下单

## 方式

```
order.place
```

## 请求

```
order.place
{
    "id": "3f7df6e3-2df4-44b9-9919-d2f38f90a99a",
    "method": "order.place",
    "params": {
        "apiKey": "HMOchcfii9ZRZnhjp2XjGXhsOBd6msAhKz9joQaWwZ7arcJTlD2hGPHQj1lGdTjR",
        "positionSide": "BOTH",
        "price": 43187.00,
        "quantity": 0.1,
        "side": "BUY",
        "symbol": "BTCUSDT",
        "timeInForce": "GTC",
        "timestamp": 1702555533821,
        "type": "LIMIT",
        "signature": "0f04368b2d22aafd0ggc8809ea34297eff602272917b5f01267db4efbc1c9422"
    }
}
```



## 请求权重

**0**

## 请求参数

| 名称                    | 类型    | 是否必需 | 描述                                                         |
| ----------------------- | ------- | -------- | ------------------------------------------------------------ |
| symbol                  | STRING  | YES      | 交易对                                                       |
| side                    | ENUM    | YES      | 买卖方向 `SELL`, `BUY`                                       |
| positionSide            | ENUM    | NO       | 持仓方向，单向持仓模式下非必填，默认且仅可填`BOTH`;在双向持仓模式下必填,且仅可选择 `LONG` 或 `SHORT` |
| type                    | ENUM    | YES      | 订单类型 `LIMIT`, `MARKET`, `STOP`, `TAKE_PROFIT`, `STOP_MARKET`, `TAKE_PROFIT_MARKET`, `TRAILING_STOP_MARKET` |
| reduceOnly              | STRING  | NO       | `true`, `false`; 非双开模式下默认`false`；双开模式下不接受此参数； 使用`closePosition`不支持此参数。 |
| quantity                | DECIMAL | NO       | 下单数量,使用`closePosition`不支持此参数。                   |
| price                   | DECIMAL | NO       | 委托价格                                                     |
| newClientOrderId        | STRING  | NO       | 用户自定义的订单号，不可以重复出现在挂单中。如空缺系统会自动赋值。必须满足正则规则 `^[\.A-Z\:/a-z0-9_-]{1,36}$` |
| stopPrice               | DECIMAL | NO       | 触发价, 仅 `STOP`, `STOP_MARKET`, `TAKE_PROFIT`, `TAKE_PROFIT_MARKET` 需要此参数 |
| closePosition           | STRING  | NO       | `true`, `false`；触发后全部平仓，仅支持`STOP_MARKET`和`TAKE_PROFIT_MARKET`；不与`quantity`合用；自带只平仓效果，不与`reduceOnly` 合用 |
| activationPrice         | DECIMAL | NO       | 追踪止损激活价格，仅`TRAILING_STOP_MARKET` 需要此参数, 默认为下单当前市场价格(支持不同`workingType`) |
| callbackRate            | DECIMAL | NO       | 追踪止损回调比例，可取值范围[0.1, 10],其中 1代表1% ,仅`TRAILING_STOP_MARKET` 需要此参数 |
| timeInForce             | ENUM    | NO       | 有效方法                                                     |
| workingType             | ENUM    | NO       | stopPrice 触发类型: `MARK_PRICE`(标记价格), `CONTRACT_PRICE`(合约最新价). 默认 `CONTRACT_PRICE` |
| priceProtect            | STRING  | NO       | 条件单触发保护："TRUE","FALSE", 默认"FALSE". 仅 `STOP`, `STOP_MARKET`, `TAKE_PROFIT`, `TAKE_PROFIT_MARKET` 需要此参数 |
| newOrderRespType        | ENUM    | NO       | "ACK", "RESULT", 默认 "ACK"                                  |
| priceMatch              | ENUM    | NO       | `OPPONENT`/ `OPPONENT_5`/ `OPPONENT_10`/ `OPPONENT_20`/`QUEUE`/ `QUEUE_5`/ `QUEUE_10`/ `QUEUE_20`；不能与price同时传 |
| selfTradePreventionMode | ENUM    | NO       | `NONE` / `EXPIRE_TAKER`/ `EXPIRE_MAKER`/ `EXPIRE_BOTH`； 默认`NONE` |
| goodTillDate            | LONG    | NO       | TIF为GTD时订单的自动取消时间， 当`timeInforce`为`GTD`时必传；传入的时间戳仅保留秒级精度，毫秒级部分会被自动忽略，时间戳需大于当前时间+600s且小于253402300799000 |
| recvWindow              | LONG    | NO       |                                                              |
| timestamp               | LONG    | YES      |                                                              |

根据 order `type`的不同，某些参数强制要求，具体如下:

| Type                                | 强制要求的参数                                   |
| ----------------------------------- | ------------------------------------------------ |
| `LIMIT`                             | `timeInForce`, `quantity`, `price`或`priceMatch` |
| `MARKET`                            | `quantity`                                       |
| `STOP`, `TAKE_PROFIT`               | `quantity`, `stopPrice`                          |
| `STOP_MARKET`, `TAKE_PROFIT_MARKET` | `stopPrice`, `price`或`priceMatch`               |
| `TRAILING_STOP_MARKET`              | `callbackRate`                                   |

> - 条件单的触发必须:
>
>   - 如果订单参数
>
>     ```
>     priceProtect
>     ```
>
>     为true:
>
>     - 达到触发价时，`MARK_PRICE`(标记价格)与`CONTRACT_PRICE`(合约最新价)之间的价差不能超过改symbol触发保护阈值
>     - 触发保护阈值请参考接口`GET /fapi/v1/exchangeInfo` 返回内容相应symbol中"triggerProtect"字段
>
>   - ```
>     STOP
>     ```
>
>     ,
>
>      
>
>     ```
>     STOP_MARKET
>     ```
>
>      
>
>     止损单:
>
>     - 买入: 最新合约价格/标记价格高于等于触发价`stopPrice`
>     - 卖出: 最新合约价格/标记价格低于等于触发价`stopPrice`
>
>   - ```
>     TAKE_PROFIT
>     ```
>
>     ,
>
>      
>
>     ```
>     TAKE_PROFIT_MARKET
>     ```
>
>      
>
>     止盈单:
>
>     - 买入: 最新合约价格/标记价格低于等于触发价`stopPrice`
>     - 卖出: 最新合约价格/标记价格高于等于触发价`stopPrice`
>
>   - ```
>     TRAILING_STOP_MARKET
>     ```
>
>      
>
>     跟踪止损单:
>
>     - 买入: 当合约价格/标记价格区间最低价格低于激活价格`activationPrice`,且最新合约价格/标记价高于等于最低价设定回调幅度。
>     - 卖出: 当合约价格/标记价格区间最高价格高于激活价格`activationPrice`,且最新合约价格/标记价低于等于最高价设定回调幅度。
>
> - `TRAILING_STOP_MARKET` 跟踪止损单如果遇到报错 `{"code": -2021, "msg": "Order would immediately trigger."}`
>   表示订单不满足以下条件:
>
>   - 买入: 指定的`activationPrice` 必须小于 latest price
>   - 卖出: 指定的`activationPrice` 必须大于 latest price
>
> - `newOrderRespType` 如果传 `RESULT`:
>
>   - `MARKET` 订单将直接返回成交结果；
>   - 配合使用特殊 `timeInForce` 的 `LIMIT` 订单将直接返回成交或过期拒绝结果。
>
> - `STOP_MARKET`, `TAKE_PROFIT_MARKET` 配合 `closePosition`=`true`:
>
>   - 条件单触发依照上述条件单触发逻辑
>   - 条件触发后，平掉当时持有所有多头仓位(若为卖单)或当时持有所有空头仓位(若为买单)
>   - 不支持 `quantity` 参数
>   - 自带只平仓属性，不支持`reduceOnly`参数
>   - 双开模式下,`LONG`方向上不支持`BUY`; `SHORT` 方向上不支持`SELL`

## 响应示例

```javascript
{
    "id": "3f7df6e3-2df4-44b9-9919-d2f38f90a99a",
    "status": 200,
    "result": {
        "orderId": 325078477,
        "symbol": "BTCUSDT",
        "status": "NEW",
        "clientOrderId": "iCXL1BywlBaf2sesNUrVl3",
        "price": "43187.00",
        "avgPrice": "0.00",
        "origQty": "0.100",
        "executedQty": "0.000",
        "cumQty": "0.000",
        "cumQuote": "0.00000",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "reduceOnly": false,
        "closePosition": false,
        "side": "BUY",
        "positionSide": "BOTH",
        "stopPrice": "0.00",
        "workingType": "CONTRACT_PRICE",
        "priceProtect": false,
        "origType": "LIMIT",
        "priceMatch": "NONE",
        "selfTradePreventionMode": "NONE",
        "goodTillDate": 0,
        "updateTime": 1702555534435
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 300,
            "count": 1
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 1200,
            "count": 1
        },
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 2400,
            "count": 1
        }
    ]
}
```



# 撤销订单 (TRADE)

## 接口描述

撤销订单

## 方式

```
order.cancel
```

## 请求

```javascript
{
   	"id": "5633b6a2-90a9-4192-83e7-925c90b6a2fd",
    "method": "order.cancel", 
    "params": { 
        "apiKey": "HsOehcfih8ZRxnhjp2XjGXhsOBd6msAhKz9joQaWwZ7arcJTlD2hGOGQj1lGdTjR", 
        "orderId": 283194212, 
        "symbol": "BTCUSDT", 
        "timestamp": 1703439070722, 
        "signature": "b09c49815b4e3f1f6098cd9fbe26a933a9af79803deaaaae03c29f719c08a8a8" 
    }
}
```



## 请求权重

**1**

## 请求参数

| 名称              | 类型   | 是否必需 | 描述               |
| ----------------- | ------ | -------- | ------------------ |
| symbol            | STRING | YES      | 交易对             |
| orderId           | LONG   | NO       | 系统订单号         |
| origClientOrderId | STRING | NO       | 用户自定义的订单号 |
| recvWindow        | LONG   | NO       |                    |
| timestamp         | LONG   | YES      |                    |

> - `orderId` 与 `origClientOrderId` 必须至少发送一个

## 响应示例

```javascript
{
  "id": "5633b6a2-90a9-4192-83e7-925c90b6a2fd",
  "status": 200,
  "result": {
    "clientOrderId": "myOrder1",
    "cumQty": "0",
    "cumQuote": "0",
    "executedQty": "0",
    "orderId": 283194212,
    "origQty": "11",
    "origType": "TRAILING_STOP_MARKET",
    "price": "0",
    "reduceOnly": false,
    "side": "BUY",
    "positionSide": "SHORT",
    "status": "CANCELED",
    "stopPrice": "9300",                
    "closePosition": false,  
    "symbol": "BTCUSDT",
    "timeInForce": "GTC",
    "type": "TRAILING_STOP_MARKET",
    "activatePrice": "9020",            
    "priceRate": "0.3",                
    "updateTime": 1571110484038,
    "workingType": "CONTRACT_PRICE",
    "priceProtect": false,           
    "priceMatch": "NONE",              
    "selfTradePreventionMode": "NONE",
    "goodTillDate": 0                 
  },
  "rateLimits": [
    {
      "rateLimitType": "REQUEST_WEIGHT",
      "interval": "MINUTE",
      "intervalNum": 1,
      "limit": 2400,
      "count": 1
    }
  ]
}
```



# 下单 (TRADE)

## 接口描述

下单

## HTTP请求

POST `/fapi/v1/order`

## 请求权重

10s order rate limit(X-MBX-ORDER-COUNT-10S)为1; 1min order rate limit(X-MBX-ORDER-COUNT-1M)为1; IP rate limit(x-mbx-used-weight-1m)为0

## 请求参数

| 名称                    | 类型    | 是否必需 | 描述                                                         |
| ----------------------- | ------- | -------- | ------------------------------------------------------------ |
| symbol                  | STRING  | YES      | 交易对                                                       |
| side                    | ENUM    | YES      | 买卖方向 `SELL`, `BUY`                                       |
| positionSide            | ENUM    | NO       | 持仓方向，单向持仓模式下非必填，默认且仅可填`BOTH`;在双向持仓模式下必填,且仅可选择 `LONG` 或 `SHORT` |
| type                    | ENUM    | YES      | 订单类型 `LIMIT`, `MARKET`, `STOP`, `TAKE_PROFIT`, `STOP_MARKET`, `TAKE_PROFIT_MARKET`, `TRAILING_STOP_MARKET` |
| reduceOnly              | STRING  | NO       | `true`, `false`; 非双开模式下默认`false`；双开模式下不接受此参数； 使用`closePosition`不支持此参数。 |
| quantity                | DECIMAL | NO       | 下单数量,使用`closePosition`不支持此参数。                   |
| price                   | DECIMAL | NO       | 委托价格                                                     |
| newClientOrderId        | STRING  | NO       | 用户自定义的订单号，不可以重复出现在挂单中。如空缺系统会自动赋值。必须满足正则规则 `^[\.A-Z\:/a-z0-9_-]{1,36}$` |
| stopPrice               | DECIMAL | NO       | 触发价, 仅 `STOP`, `STOP_MARKET`, `TAKE_PROFIT`, `TAKE_PROFIT_MARKET` 需要此参数 |
| closePosition           | STRING  | NO       | `true`, `false`；触发后全部平仓，仅支持`STOP_MARKET`和`TAKE_PROFIT_MARKET`；不与`quantity`合用；自带只平仓效果，不与`reduceOnly` 合用 |
| activationPrice         | DECIMAL | NO       | 追踪止损激活价格，仅`TRAILING_STOP_MARKET` 需要此参数, 默认为下单当前市场价格(支持不同`workingType`) |
| callbackRate            | DECIMAL | NO       | 追踪止损回调比例，可取值范围[0.1, 10],其中 1代表1% ,仅`TRAILING_STOP_MARKET` 需要此参数 |
| timeInForce             | ENUM    | NO       | 有效方法                                                     |
| workingType             | ENUM    | NO       | stopPrice 触发类型: `MARK_PRICE`(标记价格), `CONTRACT_PRICE`(合约最新价). 默认 `CONTRACT_PRICE` |
| priceProtect            | STRING  | NO       | 条件单触发保护："TRUE","FALSE", 默认"FALSE". 仅 `STOP`, `STOP_MARKET`, `TAKE_PROFIT`, `TAKE_PROFIT_MARKET` 需要此参数 |
| newOrderRespType        | ENUM    | NO       | "ACK", "RESULT", 默认 "ACK"                                  |
| priceMatch              | ENUM    | NO       | `OPPONENT`/ `OPPONENT_5`/ `OPPONENT_10`/ `OPPONENT_20`/`QUEUE`/ `QUEUE_5`/ `QUEUE_10`/ `QUEUE_20`；不能与price同时传 |
| selfTradePreventionMode | ENUM    | NO       | `EXPIRE_TAKER`/ `EXPIRE_MAKER`/ `EXPIRE_BOTH`； 默认`NONE`   |
| goodTillDate            | LONG    | NO       | TIF为GTD时订单的自动取消时间， 当`timeInforce`为`GTD`时必传；传入的时间戳仅保留秒级精度，毫秒级部分会被自动忽略，时间戳需大于当前时间+600s且小于253402300799000 |
| recvWindow              | LONG    | NO       |                                                              |
| timestamp               | LONG    | YES      |                                                              |

根据 order `type`的不同，某些参数强制要求，具体如下:

| Type                                | 强制要求的参数                     |
| ----------------------------------- | ---------------------------------- |
| `LIMIT`                             | `timeInForce`, `quantity`, `price` |
| `MARKET`                            | `quantity`                         |
| `STOP`, `TAKE_PROFIT`               | `quantity`, `price`, `stopPrice`   |
| `STOP_MARKET`, `TAKE_PROFIT_MARKET` | `stopPrice`                        |
| `TRAILING_STOP_MARKET`              | `callbackRate`                     |

> - 条件单的触发必须:
>
>   - 如果订单参数
>
>     ```
>     priceProtect
>     ```
>
>     为true:
>
>     - 达到触发价时，`MARK_PRICE`(标记价格)与`CONTRACT_PRICE`(合约最新价)之间的价差不能超过改symbol触发保护阈值
>     - 触发保护阈值请参考接口`GET /fapi/v1/exchangeInfo` 返回内容相应symbol中"triggerProtect"字段
>
>   - ```
>     STOP
>     ```
>
>     ,
>
>      
>
>     ```
>     STOP_MARKET
>     ```
>
>      
>
>     止损单:
>
>     - 买入: 最新合约价格/标记价格高于等于触发价`stopPrice`
>     - 卖出: 最新合约价格/标记价格低于等于触发价`stopPrice`
>
>   - ```
>     TAKE_PROFIT
>     ```
>
>     ,
>
>      
>
>     ```
>     TAKE_PROFIT_MARKET
>     ```
>
>      
>
>     止盈单:
>
>     - 买入: 最新合约价格/标记价格低于等于触发价`stopPrice`
>     - 卖出: 最新合约价格/标记价格高于等于触发价`stopPrice`
>
>   - ```
>     TRAILING_STOP_MARKET
>     ```
>
>      
>
>     跟踪止损单:
>
>     - 买入: 当合约价格/标记价格区间最低价格低于激活价格`activationPrice`,且最新合约价格/标记价高于等于最低价设定回调幅度。
>     - 卖出: 当合约价格/标记价格区间最高价格高于激活价格`activationPrice`,且最新合约价格/标记价低于等于最高价设定回调幅度。
>
> - `TRAILING_STOP_MARKET` 跟踪止损单如果遇到报错 `{"code": -2021, "msg": "Order would immediately trigger."}`
>   表示订单不满足以下条件:
>
>   - 买入: 指定的`activationPrice` 必须小于 latest price
>   - 卖出: 指定的`activationPrice` 必须大于 latest price
>
> - `newOrderRespType` 如果传 `RESULT`:
>
>   - `MARKET` 订单将直接返回成交结果；
>   - 配合使用特殊 `timeInForce` 的 `LIMIT` 订单将直接返回成交或过期拒绝结果。
>
> - `STOP_MARKET`, `TAKE_PROFIT_MARKET` 配合 `closePosition`=`true`:
>
>   - 条件单触发依照上述条件单触发逻辑
>   - 条件触发后，平掉当时持有所有多头仓位(若为卖单)或当时持有所有空头仓位(若为买单)
>   - 不支持 `quantity` 参数
>   - 自带只平仓属性，不支持`reduceOnly`参数
>   - 双开模式下,`LONG`方向上不支持`BUY`; `SHORT` 方向上不支持`SELL`
>
> - `selfTradePreventionMode` 仅在 `timeInForce`为`IOC`或`GTC`或`GTD`时生效.
>
> - 极端行情时，`timeInForce`为`GTD`的订单自动取消可能有一定延迟

## 响应示例

```javascript
{
 	"clientOrderId": "testOrder", // 用户自定义的订单号
 	"cumQty": "0",
 	"cumQuote": "0", // 成交金额
 	"executedQty": "0", // 成交量
 	"orderId": 22542179, // 系统订单号
 	"avgPrice": "0.00000",	// 平均成交价
 	"origQty": "10", // 原始委托数量
 	"price": "0", // 委托价格
 	"reduceOnly": false, // 仅减仓
 	"side": "SELL", // 买卖方向
 	"positionSide": "SHORT", // 持仓方向
 	"status": "NEW", // 订单状态
 	"stopPrice": "0", // 触发价，对`TRAILING_STOP_MARKET`无效
 	"closePosition": false,   // 是否条件全平仓
 	"symbol": "BTCUSDT", // 交易对
 	"timeInForce": "GTD", // 有效方法
 	"type": "TRAILING_STOP_MARKET", // 订单类型
 	"origType": "TRAILING_STOP_MARKET",  // 触发前订单类型
 	"activatePrice": "9020", // 跟踪止损激活价格, 仅`TRAILING_STOP_MARKET` 订单返回此字段
  	"priceRate": "0.3",	// 跟踪止损回调比例, 仅`TRAILING_STOP_MARKET` 订单返回此字段
 	"updateTime": 1566818724722, // 更新时间
 	"workingType": "CONTRACT_PRICE", // 条件价格触发类型
 	"priceProtect": false,            // 是否开启条件单触发保护
 	"priceMatch": "NONE",              //盘口价格下单模式
 	"selfTradePreventionMode": "NONE", //订单自成交保护模式
 	"goodTillDate": 1693207680000      //订单TIF为GTD时的自动取消时间
}
```



# 批量下单(TRADE)

## 接口描述

批量下单

## HTTP请求

POST `/fapi/v1/batchOrders`

## 请求权重

10s order rate limit(X-MBX-ORDER-COUNT-10S)为5; 1min order rate limit(X-MBX-ORDER-COUNT-1M)为1; IP rate limit(x-mbx-used-weight-1m)为5;

## 请求参数

| 名称        | 类型       | 是否必需 | 描述                      |
| ----------- | ---------- | -------- | ------------------------- |
| batchOrders | list<JSON> | YES      | 订单列表，最多支持5个订单 |
| recvWindow  | LONG       | NO       |                           |
| timestamp   | LONG       | YES      |                           |

**其中`batchOrders`应以list of JSON格式填写订单参数**

- **例子:** /fapi/v1/batchOrders?batchOrders=[{"type":"LIMIT","timeInForce":"GTC",
  "symbol":"BTCUSDT","side":"BUY","price":"10001","quantity":"0.001"}]

| 名称                    | 类型    | 是否必需 | 描述                                                         |
| ----------------------- | ------- | -------- | ------------------------------------------------------------ |
| symbol                  | STRING  | YES      | 交易对                                                       |
| side                    | ENUM    | YES      | 买卖方向 `SELL`, `BUY`                                       |
| positionSide            | ENUM    | NO       | 持仓方向，单向持仓模式下非必填，默认且仅可填`BOTH`;在双向持仓模式下必填,且仅可选择 `LONG` 或 `SHORT` |
| type                    | ENUM    | YES      | 订单类型 `LIMIT`, `MARKET`, `STOP`, `TAKE_PROFIT`, `STOP_MARKET`, `TAKE_PROFIT_MARKET`, `TRAILING_STOP_MARKET` |
| reduceOnly              | STRING  | NO       | `true`, `false`; 非双开模式下默认`false`；双开模式下不接受此参数。 |
| quantity                | DECIMAL | YES      | 下单数量                                                     |
| price                   | DECIMAL | NO       | 委托价格                                                     |
| newClientOrderId        | STRING  | NO       | 用户自定义的订单号，不可以重复出现在挂单中。如空缺系统会自动赋值. 必须满足正则规则 `^[\.A-Z\:/a-z0-9_-]{1,36}$` |
| stopPrice               | DECIMAL | NO       | 触发价, 仅 `STOP`, `STOP_MARKET`, `TAKE_PROFIT`, `TAKE_PROFIT_MARKET` 需要此参数 |
| activationPrice         | DECIMAL | NO       | 追踪止损激活价格，仅`TRAILING_STOP_MARKET` 需要此参数, 默认为下单当前市场价格(支持不同`workingType`) |
| callbackRate            | DECIMAL | NO       | 追踪止损回调比例，可取值范围[0.1, 4],其中 1代表1% ,仅`TRAILING_STOP_MARKET` 需要此参数 |
| timeInForce             | ENUM    | NO       | 有效方法                                                     |
| workingType             | ENUM    | NO       | stopPrice 触发类型: `MARK_PRICE`(标记价格), `CONTRACT_PRICE`(合约最新价). 默认 `CONTRACT_PRICE` |
| priceProtect            | STRING  | NO       | 条件单触发保护："TRUE","FALSE", 默认"FALSE". 仅 `STOP`, `STOP_MARKET`, `TAKE_PROFIT`, `TAKE_PROFIT_MARKET` 需要此参数 |
| newOrderRespType        | ENUM    | NO       | "ACK", "RESULT", 默认 "ACK"                                  |
| priceMatch              | ENUM    | NO       | `OPPONENT`/ `OPPONENT_5`/ `OPPONENT_10`/ `OPPONENT_20`/`QUEUE`/ `QUEUE_5`/ `QUEUE_10`/ `QUEUE_20`；不能与price同时传 |
| selfTradePreventionMode | ENUM    | NO       | `EXPIRE_TAKER`/ `EXPIRE_MAKER`/ `EXPIRE_BOTH`； 默认`NONE`   |
| goodTillDate            | LONG    | NO       | TIF为GTD时订单的自动取消时间， 当`timeInforce`为`GTD`时必传；传入的时间戳仅保留秒级精度，毫秒级部分会被自动忽略，时间戳需大于当前时间+600s且小于253402300799000 |

> - 具体订单条件规则，与普通下单一致
> - 批量下单采取并发处理，不保证订单撮合顺序
> - 批量下单的返回内容顺序，与订单列表顺序一致

## 响应示例

```javascript
[
	{
	 	"clientOrderId": "testOrder", // 用户自定义的订单号
	 	"cumQty": "0",
	 	"cumQuote": "0", // 成交金额
	 	"executedQty": "0", // 成交量
	 	"orderId": 22542179, // 系统订单号
	 	"avgPrice": "0.00000",	// 平均成交价
	 	"origQty": "10", // 原始委托数量
	 	"price": "0", // 委托价格
	 	"reduceOnly": false, // 仅减仓
	 	"side": "SELL", // 买卖方向
	 	"positionSide": "SHORT", // 持仓方向
	 	"status": "NEW", // 订单状态
	 	"stopPrice": "0", // 触发价，对`TRAILING_STOP_MARKET`无效
	 	"closePosition": false,   // 是否条件全平仓
	 	"symbol": "BTCUSDT", // 交易对
	 	"timeInForce": "GTC", // 有效方法
	 	"type": "TRAILING_STOP_MARKET", // 订单类型
	 	"origType": "TRAILING_STOP_MARKET",  // 触发前订单类型
	 	"activatePrice": "9020", // 跟踪止损激活价格, 仅`TRAILING_STOP_MARKET` 订单返回此字段
	  	"priceRate": "0.3",	// 跟踪止损回调比例, 仅`TRAILING_STOP_MARKET` 订单返回此字段
	 	"updateTime": 1566818724722, // 更新时间
	 	"workingType": "CONTRACT_PRICE", // 条件价格触发类型
	 	"priceProtect": false,            // 是否开启条件单触发保护
 		"priceMatch": "NONE",              //盘口价格下单模式
 		"selfTradePreventionMode": "NONE", //订单自成交保护模式
 		"goodTillDate": 1693207680000      //订单TIF为GTD时的自动取消时间
	},
	{
		"code": -2022, 
		"msg": "ReduceOnly Order is rejected."
	}
]
```



# 撤销订单 (TRADE)

## 接口描述

撤销订单

## HTTP请求

DELETE `/fapi/v1/order`

## 请求权重

**1**

## 请求参数

| 名称              | 类型   | 是否必需 | 描述               |
| ----------------- | ------ | -------- | ------------------ |
| symbol            | STRING | YES      | 交易对             |
| orderId           | LONG   | NO       | 系统订单号         |
| origClientOrderId | STRING | NO       | 用户自定义的订单号 |
| recvWindow        | LONG   | NO       |                    |
| timestamp         | LONG   | YES      |                    |

> - `orderId` 与 `origClientOrderId` 必须至少发送一个

## 响应示例

```javascript
{
 	"clientOrderId": "myOrder1", // 用户自定义的订单号
 	"cumQty": "0",
 	"cumQuote": "0", // 成交金额
 	"executedQty": "0", // 成交量
 	"orderId": 283194212, // 系统订单号
 	"origQty": "11", // 原始委托数量
 	"price": "0", // 委托价格
	"reduceOnly": false, // 仅减仓
	"side": "BUY", // 买卖方向
	"positionSide": "SHORT", // 持仓方向
 	"status": "CANCELED", // 订单状态
 	"stopPrice": "9300", // 触发价，对`TRAILING_STOP_MARKET`无效
 	"closePosition": false,   // 是否条件全平仓
 	"symbol": "BTCUSDT", // 交易对
 	"timeInForce": "GTC", // 有效方法
 	"origType": "TRAILING_STOP_MARKET",	// 触发前订单类型
 	"type": "TRAILING_STOP_MARKET", // 订单类型
 	"activatePrice": "9020", // 跟踪止损激活价格, 仅`TRAILING_STOP_MARKET` 订单返回此字段
  	"priceRate": "0.3",	// 跟踪止损回调比例, 仅`TRAILING_STOP_MARKET` 订单返回此字段
 	"updateTime": 1571110484038, // 更新时间
 	"workingType": "CONTRACT_PRICE", // 条件价格触发类型
 	"priceProtect": false,            // 是否开启条件单触发保护
  	"priceMatch": "NONE",              //盘口价格下单模式
  	"selfTradePreventionMode": "NONE", //订单自成交保护模式
  	"goodTillDate": 0      //订单TIF为GTD时的自动取消时间
}
```



# 批量撤销订单(TRADE)

## 接口描述

批量撤销订单 (TRADE)

## HTTP Request

DELETE `/fapi/v1/batchOrders`

## 请求权重

**1**

## 请求参数

| 名称                  | 类型         | 是否必需 | 描述                                                         |
| --------------------- | ------------ | -------- | ------------------------------------------------------------ |
| symbol                | STRING       | YES      | 交易对                                                       |
| orderIdList           | LIST<LONG>   | NO       | 系统订单号, 最多支持10个订单  比如`[1234567,2345678]`        |
| origClientOrderIdList | LIST<STRING> | NO       | 用户自定义的订单号, 最多支持10个订单  比如`["my_id_1","my_id_2"]` 需要encode双引号。逗号后面没有空格。 |
| recvWindow            | LONG         | NO       |                                                              |
| timestamp             | LONG         | YES      |                                                              |

> - `orderIdList` 与 `origClientOrderIdList` 必须至少发送一个，不可同时发送

## Response Example

```javascript
[
	{
	 	"clientOrderId": "myOrder1", // 用户自定义的订单号
	 	"cumQty": "0",
	 	"cumQuote": "0", // 成交金额
	 	"executedQty": "0", // 成交量
	 	"orderId": 283194212, // 系统订单号
	 	"origQty": "11", // 原始委托数量
	 	"price": "0", // 委托价格
		"reduceOnly": false, // 仅减仓
		"side": "BUY", // 买卖方向
		"positionSide": "SHORT", // 持仓方向
	 	"status": "CANCELED", // 订单状态
	 	"stopPrice": "9300", // 触发价，对`TRAILING_STOP_MARKET`无效
	 	"closePosition": false,   // 是否条件全平仓
	 	"symbol": "BTCUSDT", // 交易对
	 	"timeInForce": "GTC", // 有效方法
	 	"origType": "TRAILING_STOP_MARKET", // 触发前订单类型
 		"type": "TRAILING_STOP_MARKET", // 订单类型
	 	"activatePrice": "9020", // 跟踪止损激活价格, 仅`TRAILING_STOP_MARKET` 订单返回此字段
  		"priceRate": "0.3",	// 跟踪止损回调比例, 仅`TRAILING_STOP_MARKET` 订单返回此字段
	 	"updateTime": 1571110484038, // 更新时间
	 	"workingType": "CONTRACT_PRICE", // 条件价格触发类型
	 	"priceProtect": false            // 是否开启条件单触发保护
	 	"priceMatch": "NONE",              //盘口价格下单模式
	 	"selfTradePreventionMode": "NONE", //订单自成交保护模式
 		"goodTillDate": 0      //订单TIF为GTD时的自动取消时间
	},
	{
		"code": -2011,
		"msg": "Unknown order sent."
	}
]
```



# 撤销全部订单(TRADE)

## 接口描述

撤销全部订单 (TRADE)

## HTTP请求

DELETE `/fapi/v1/allOpenOrders`

## 请求权重

**1**

## 请求参数

| 名称       | 类型   | 是否必需 | 描述   |
| ---------- | ------ | -------- | ------ |
| symbol     | STRING | YES      | 交易对 |
| recvWindow | LONG   | NO       |        |
| timestamp  | LONG   | YES      |        |

## 响应示例

```javascript
{
	"code": 200, 
	"msg": "The operation of cancel all open order is done."
}
```



# 查询订单 (USER_DATA)

## 接口描述

查询订单状态

- 请注意，如果订单满足如下条件，不会被查询到：
  - 订单的最终状态为 `CANCELED` 或者 `EXPIRED` **并且** 订单没有任何的成交记录 **并且** 订单生成时间 + 3天 < 当前时间
  - 订单创建时间 + 90天 < 当前时间

## HTTP请求

GET `/fapi/v1/order`

## 请求权重

**1**

## 请求参数

| 名称              | 类型   | 是否必需 | 描述               |
| ----------------- | ------ | -------- | ------------------ |
| symbol            | STRING | YES      | 交易对             |
| orderId           | LONG   | NO       | 系统订单号         |
| origClientOrderId | STRING | NO       | 用户自定义的订单号 |
| recvWindow        | LONG   | NO       |                    |
| timestamp         | LONG   | YES      |                    |

注意:

> - 至少需要发送 `orderId` 与 `origClientOrderId`中的一个
> - `orderId`在`symbol`维度是自增的

## 响应示例

```javascript
{
  	"avgPrice": "0.00000",				// 平均成交价
  	"clientOrderId": "abc",				// 用户自定义的订单号
  	"cumQuote": "0",					// 成交金额
  	"executedQty": "0",					// 成交量
  	"orderId": 1573346959,				// 系统订单号
  	"origQty": "0.40",					// 原始委托数量
  	"origType": "TRAILING_STOP_MARKET",	// 触发前订单类型
  	"price": "0",						// 委托价格
  	"reduceOnly": false,				// 是否仅减仓
  	"side": "BUY",						// 买卖方向
  	"positionSide": "SHORT", 			// 持仓方向
  	"status": "NEW",					// 订单状态
  	"stopPrice": "9300",			    // 触发价，对`TRAILING_STOP_MARKET`无效
  	"closePosition": false,             // 是否条件全平仓
  	"symbol": "BTCUSDT",				// 交易对
  	"time": 1579276756075,				// 订单时间
  	"timeInForce": "GTC",				// 有效方法
  	"type": "TRAILING_STOP_MARKET",		// 订单类型
  	"activatePrice": "9020",			// 跟踪止损激活价格, 仅`TRAILING_STOP_MARKET` 订单返回此字段
  	"priceRate": "0.3",					// 跟踪止损回调比例, 仅`TRAILING_STOP_MARKET` 订单返回此字段
  	"updateTime": 1579276756075,		// 更新时间
  	"workingType": "CONTRACT_PRICE",    // 条件价格触发类型
 	"priceProtect": false,              // 是否开启条件单触发保护
    "priceMatch": "NONE",               //盘口价格下单模式
    "selfTradePreventionMode": "NONE",  //订单自成交保护模式
    "goodTillDate": 0                   //订单TIF为GTD时的自动取消时间
}
```



# 查看当前全部挂单 (USER_DATA)

## 接口描述

查看当前全部挂单

## HTTP请求

GET `/fapi/v1/openOrders`

## 请求权重

- 带symbol ***1***
- 不带 ***40*** 请小心使用不带symbol参数的调用

## 请求参数

| 名称       | 类型   | 是否必需 | 描述   |
| ---------- | ------ | -------- | ------ |
| symbol     | STRING | NO       | 交易对 |
| recvWindow | LONG   | NO       |        |
| timestamp  | LONG   | YES      |        |

> - 不带symbol参数，会返回所有交易对的挂单

## 响应示例

```javascript
[
  {
  	"avgPrice": "0.00000",				// 平均成交价
  	"clientOrderId": "abc",				// 用户自定义的订单号
  	"cumQuote": "0",						// 成交金额
  	"executedQty": "0",					// 成交量
  	"orderId": 1917641,					// 系统订单号
  	"origQty": "0.40",					// 原始委托数量
  	"origType": "TRAILING_STOP_MARKET",	// 触发前订单类型
  	"price": "0",					// 委托价格
  	"reduceOnly": false,				// 是否仅减仓
  	"side": "BUY",						// 买卖方向
  	"positionSide": "SHORT", // 持仓方向
  	"status": "NEW",					// 订单状态
  	"stopPrice": "9300",					// 触发价，对`TRAILING_STOP_MARKET`无效
  	"closePosition": false,   // 是否条件全平仓
  	"symbol": "BTCUSDT",				// 交易对
  	"time": 1579276756075,				// 订单时间
  	"timeInForce": "GTC",				// 有效方法
  	"type": "TRAILING_STOP_MARKET",		// 订单类型
  	"activatePrice": "9020", // 跟踪止损激活价格, 仅`TRAILING_STOP_MARKET` 订单返回此字段
  	"priceRate": "0.3",	// 跟踪止损回调比例, 仅`TRAILING_STOP_MARKET` 订单返回此字段
  	"updateTime": 1579276756075,		// 更新时间
  	"workingType": "CONTRACT_PRICE", // 条件价格触发类型
 	"priceProtect": false,           // 是否开启条件单触发保护
	"priceMatch": "NONE",              //price match mode
    "selfTradePreventionMode": "NONE", //self trading preventation mode
    "goodTillDate": 0      //order pre-set auot cancel time for TIF GTD order
  }
]
```