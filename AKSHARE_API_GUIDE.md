# AKShare API 接口文档

> 本文档整理了AKShare中用于股票分析的核心接口
> 
> AKShare版本: 1.18.57
> 
> 官方文档: https://akshare.akfamily.xyz/

---

## 📚 目录

1. [股票基础数据](#1-股票基础数据)
2. [财务报表](#2-财务报表)
3. [财务指标](#3-财务指标)
4. [行情数据](#4-行情数据)
5. [分红数据](#5-分红数据)
6. [板块数据](#6-板块数据)
7. [个股信息](#7-个股信息)

---

## 1. 股票基础数据

### 1.1 A股实时行情

**函数**: `stock_zh_a_spot_em()`

**说明**: 获取沪深A股实时行情数据

**返回字段**:
- 代码、名称、最新价、涨跌幅、涨跌额
- 成交量、成交额、振幅、最高、最低
- 今开、昨收、换手率

**示例**:
```python
import akshare as ak

df = ak.stock_zh_a_spot_em()
print(df.head())
```

**用途**: 
- 获取所有A股的实时行情
- 筛选股票（涨幅榜、跌幅榜）
- 市场概况分析

---

### 1.2 历史行情数据

**函数**: `stock_zh_a_hist(symbol, period, start_date, end_date, adjust)`

**参数**:
- `symbol`: 股票代码 (如 "600519")
- `period`: 周期 ("daily", "weekly", "monthly")
- `start_date`: 开始日期 ("20200101")
- `end_date`: 结束日期 ("20240101")
- `adjust`: 复权类型 ("qfq"-前复权, "hfq"-后复权, ""-不复权)

**返回字段**:
- 日期、开盘、收盘、最高、最低
- 成交量、成交额、振幅、涨跌幅
- 涨跌额、换手率

**示例**:
```python
df = ak.stock_zh_a_hist(
    symbol="600519",
    period="daily",
    start_date="20230101",
    end_date="20240101",
    adjust="qfq"  # 前复权
)
```

**用途**:
- 技术分析
- 计算收益率
- 回测策略

---

## 2. 财务报表

### 2.1 资产负债表

**函数**: `stock_balance_sheet_by_report_em(symbol)`

**参数**:
- `symbol`: 股票代码

**返回字段**:
- REPORT_DATE: 报告日期
- MONETARYFUND: 货币资金
- ACCOUNTSRECE: 应收账款
- INVENTORY: 存货
- TOTALCURRENTASSETS: 流动资产合计
- FIXEDASSETS: 固定资产
- TOTALASSETS: 资产总计
- SHORTBORR: 短期借款
- LONGBORR: 长期借款
- TOTALLIABILITIES: 负债合计
- TOTALSE: 股东权益合计

**示例**:
```python
df = ak.stock_balance_sheet_by_report_em(symbol="600519")
latest = df.iloc[0]  # 最新一期
print(f"总资产: {latest['TOTALASSETS']}")
print(f"负债合计: {latest['TOTALLIABILITIES']}")
```

**用途**:
- 计算资产负债率
- 分析现金储备
- 评估偿债能力

---

### 2.2 利润表

**函数**: `stock_profit_sheet_by_report_em(symbol)`

**参数**:
- `symbol`: 股票代码

**返回字段**:
- REPORT_DATE: 报告日期
- TOTALOPERATEREVE: 营业总收入
- TOTALOPERATEEXP: 营业总成本
- OPERATEPROFIT: 营业利润
- TOTALPROFIT: 利润总额
- NETPROFIT: 净利润
- INTEXP: 利息费用

**示例**:
```python
df = ak.stock_profit_sheet_by_report_em(symbol="600519")
latest = df.iloc[0]
revenue = latest['TOTALOPERATEREVE']
net_profit = latest['NETPROFIT']
net_margin = net_profit / revenue
print(f"净利率: {net_margin:.2%}")
```

**用途**:
- 计算毛利率、净利率
- 分析盈利能力
- 计算EBIT

---

### 2.3 现金流量表

**函数**: `stock_cash_flow_sheet_by_report_em(symbol)`

**参数**:
- `symbol`: 股票代码

**返回字段**:
- REPORT_DATE: 报告日期
- NETOPERATECASHFLOW: 经营活动现金流净额
- NETINVCASHFLOW: 投资活动现金流净额
- NETFINACASHFLOW: 筹资活动现金流净额
- PURCHCONASSETPAY: 购建固定资产支付的现金

**示例**:
```python
df = ak.stock_cash_flow_sheet_by_report_em(symbol="600519")
latest = df.iloc[0]
operating_cf = latest['NETOPERATECASHFLOW']
capex = latest['PURCHCONASSETPAY']
fcf = operating_cf - capex  # 自由现金流
print(f"自由现金流: {fcf}")
```

**用途**:
- 计算自由现金流
- 评估现金创造能力
- 分析资本开支

---

## 3. 财务指标

### 3.1 主要财务指标

**函数**: `stock_financial_analysis_indicator(symbol)`

**参数**:
- `symbol`: 股票代码

**返回字段**:
- 截止日期
- 营业总收入、净利润
- 销售毛利率、销售净利率
- 净资产收益率 (ROE)
- 资产负债率
- 流动比率、速动比率
- 经营活动产生的现金流量净额

**示例**:
```python
df = ak.stock_financial_analysis_indicator(symbol="600519")
latest = df.iloc[0]
print(f"ROE: {latest['净资产收益率']}")
print(f"毛利率: {latest['销售毛利率']}")
print(f"净利率: {latest['销售净利率']}")
print(f"负债率: {latest['资产负债率']}")
```

**用途**:
- 快速获取关键指标
- 财务健康度评估
- 盈利能力分析

---

## 4. 行情数据

### 4.1 个股信息

**函数**: `stock_individual_info_em(symbol)`

**参数**:
- `symbol`: 股票代码

**返回字段**:
- item: 指标名称
- value: 指标值

**常用指标**:
- 股票简称
- 总市值、流通市值
- 市盈率-动态、市净率
- 总股本、流通股
- 每股收益、每股净资产

**示例**:
```python
df = ak.stock_individual_info_em(symbol="600519")
info = {}
for _, row in df.iterrows():
    info[row['item']] = row['value']

print(f"股票简称: {info['股票简称']}")
print(f"总市值: {info['总市值']}")
print(f"市盈率: {info['市盈率-动态']}")
print(f"市净率: {info['市净率']}")
```

**用途**:
- 获取股票基本信息
- 估值分析 (PE/PB)
- 市值规模判断

---

## 5. 分红数据

### 5.1 分红送配

**函数**: `stock_dividend_cninfo(symbol)`

**参数**:
- `symbol`: 股票代码

**返回字段**:
- 报告期
- 分红金额
- 分红率
- 送股比例
- 转增比例

**示例**:
```python
df = ak.stock_dividend_cninfo(symbol="600519")
print(df.head())

# 计算平均分红
avg_dividend = df['分红金额'].mean()
print(f"平均分红: {avg_dividend}")
```

**用途**:
- 分红历史分析
- 计算股息率
- 股东回报评估

---

## 6. 板块数据

### 6.1 行业板块列表

**函数**: `stock_board_industry_name_em()`

**说明**: 获取所有行业板块名称

**返回字段**:
- 板块名称
- 板块代码

**示例**:
```python
df = ak.stock_board_industry_name_em()
print(df)
```

---

### 6.2 行业板块成分股

**函数**: `stock_board_industry_cons_em(symbol)`

**参数**:
- `symbol`: 行业名称 (如 "光伏设备")

**返回字段**:
- 代码、名称
- 最新价、涨跌幅
- 总市值、流通市值

**示例**:
```python
# 获取光伏设备行业所有股票
df = ak.stock_board_industry_cons_em(symbol="光伏设备")
print(f"光伏设备行业共有 {len(df)} 只股票")
print(df.head())

# 按市值排序
df_sorted = df.sort_values('总市值', ascending=False)
print("行业龙头:", df_sorted.iloc[0]['名称'])
```

**用途**:
- 行业对比分析
- 识别行业龙头
- 计算行业平均指标

---

### 6.3 概念板块

**函数**: `stock_board_concept_name_em()`

**说明**: 获取所有概念板块

**示例**:
```python
df = ak.stock_board_concept_name_em()
print(df)
```

---

## 7. 使用示例

### 7.1 完整的股票分析流程

```python
import akshare as ak
import pandas as pd

def analyze_stock(stock_code: str):
    """分析一只股票"""
    
    # 1. 基本信息
    print("=" * 50)
    print(f"分析股票: {stock_code}")
    print("=" * 50)
    
    info_df = ak.stock_individual_info_em(symbol=stock_code)
    info = {row['item']: row['value'] for _, row in info_df.iterrows()}
    
    print(f"\n股票名称: {info['股票简称']}")
    print(f"所属行业: {info['行业']}")
    print(f"总市值: {info['总市值']}亿")
    print(f"PE: {info['市盈率-动态']}")
    print(f"PB: {info['市净率']}")
    
    # 2. 财务指标
    financial_df = ak.stock_financial_analysis_indicator(symbol=stock_code)
    latest = financial_df.iloc[0]
    
    print(f"\n财务指标 ({latest['截止日期']}):")
    print(f"ROE: {latest['净资产收益率']}%")
    print(f"毛利率: {latest['销售毛利率']}%")
    print(f"净利率: {latest['销售净利率']}%")
    print(f"负债率: {latest['资产负债率']}%")
    
    # 3. 资产负债表
    balance_df = ak.stock_balance_sheet_by_report_em(symbol=stock_code)
    if not balance_df.empty:
        latest_balance = balance_df.iloc[0]
        cash = latest_balance['MONETARYFUND'] / 100000000  # 转成亿
        total_debt = (latest_balance.get('SHORTBORR', 0) + 
                     latest_balance.get('LONGBORR', 0)) / 100000000
        net_cash = cash - total_debt
        
        print(f"\n资产负债 ({latest_balance['REPORT_DATE']}):")
        print(f"货币资金: {cash:.2f}亿")
        print(f"总债务: {total_debt:.2f}亿")
        print(f"净现金: {net_cash:.2f}亿")
    
    # 4. 现金流
    cashflow_df = ak.stock_cash_flow_sheet_by_report_em(symbol=stock_code)
    if not cashflow_df.empty:
        latest_cf = cashflow_df.iloc[0]
        operating_cf = latest_cf['NETOPERATECASHFLOW'] / 100000000
        capex = latest_cf.get('PURCHCONASSETPAY', 0) / 100000000
        fcf = operating_cf - capex
        
        print(f"\n现金流 ({latest_cf['REPORT_DATE']}):")
        print(f"经营现金流: {operating_cf:.2f}亿")
        print(f"资本开支: {capex:.2f}亿")
        print(f"自由现金流: {fcf:.2f}亿")
    
    # 5. 分红
    dividend_df = ak.stock_dividend_cninfo(symbol=stock_code)
    if not dividend_df.empty:
        print(f"\n分红历史:")
        for _, row in dividend_df.head(3).iterrows():
            print(f"  {row['报告期']}: {row['分红金额']}元/股")

# 使用示例
analyze_stock("600519")  # 贵州茅台
```

---

### 7.2 行业对比分析

```python
def compare_industry(industry: str, top_n: int = 5):
    """行业对比分析"""
    
    # 1. 获取行业所有股票
    stocks_df = ak.stock_board_industry_cons_em(symbol=industry)
    
    print(f"\n{industry}行业分析")
    print(f"共有 {len(stocks_df)} 家公司")
    
    # 2. 按市值排序
    top_stocks = stocks_df.nlargest(top_n, '总市值')
    
    print(f"\n市值TOP{top_n}:")
    for idx, row in top_stocks.iterrows():
        print(f"{row['名称']} - {row['总市值']:.0f}亿")
    
    # 3. 获取财务指标对比
    result = []
    for _, stock in top_stocks.iterrows():
        code = stock['代码']
        try:
            financial_df = ak.stock_financial_analysis_indicator(symbol=code)
            if not financial_df.empty:
                latest = financial_df.iloc[0]
                result.append({
                    '名称': stock['名称'],
                    '市值': stock['总市值'],
                    'ROE': latest['净资产收益率'],
                    '毛利率': latest['销售毛利率'],
                    '净利率': latest['销售净利率'],
                })
        except:
            pass
    
    # 4. 显示对比
    df_compare = pd.DataFrame(result)
    print(f"\n财务指标对比:")
    print(df_compare.to_string(index=False))
    
    print(f"\n行业平均:")
    print(f"ROE: {df_compare['ROE'].mean():.2f}%")
    print(f"毛利率: {df_compare['毛利率'].mean():.2f}%")
    print(f"净利率: {df_compare['净利率'].mean():.2f}%")

# 使用示例
compare_industry("光伏设备", top_n=5)
```

---

## 8. 注意事项

### 8.1 数据更新频率

- **实时行情**: 交易时间实时更新
- **财务报表**: 季度更新（季报、半年报、年报）
- **财务指标**: 跟随财报更新
- **分红数据**: 年度更新

### 8.2 常见问题

**Q1: 为什么获取不到数据？**
- 检查股票代码是否正确（6位数字）
- 检查网络连接
- 某些API可能有访问限制

**Q2: 如何处理空数据？**
```python
df = ak.stock_balance_sheet_by_report_em(symbol="600519")
if df is None or df.empty:
    print("数据为空")
    return

latest = df.iloc[0]
```

**Q3: 字段名称不一致？**
- 不同API返回的字段名可能不同
- 建议先打印查看实际字段名
- 使用 `.get()` 方法避免KeyError

### 8.3 最佳实践

1. **添加异常处理**
```python
try:
    df = ak.stock_zh_a_spot_em()
except Exception as e:
    print(f"获取失败: {e}")
    return None
```

2. **检查返回值**
```python
df = ak.stock_financial_analysis_indicator(symbol=code)
if df is None or df.empty:
    return {}
```

3. **使用缓存**
```python
# 避免频繁调用API
cache = {}
if code in cache:
    return cache[code]

data = ak.stock_individual_info_em(symbol=code)
cache[code] = data
return data
```

---

## 9. 快速参考

### 9.1 常用接口速查

| 功能 | 函数 | 参数 |
|------|------|------|
| A股实时行情 | `stock_zh_a_spot_em()` | 无 |
| 历史行情 | `stock_zh_a_hist()` | symbol, period, start_date, end_date, adjust |
| 个股信息 | `stock_individual_info_em()` | symbol |
| 财务指标 | `stock_financial_analysis_indicator()` | symbol |
| 资产负债表 | `stock_balance_sheet_by_report_em()` | symbol |
| 利润表 | `stock_profit_sheet_by_report_em()` | symbol |
| 现金流量表 | `stock_cash_flow_sheet_by_report_em()` | symbol |
| 分红数据 | `stock_dividend_cninfo()` | symbol |
| 行业板块 | `stock_board_industry_name_em()` | 无 |
| 行业成分股 | `stock_board_industry_cons_em()` | symbol |

---

## 10. 更多资源

- **官方文档**: https://akshare.akfamily.xyz/
- **GitHub**: https://github.com/akfamily/akshare
- **示例代码**: https://akshare.akfamily.xyz/example.html

---

**整理日期**: 2026-08-12  
**AKShare版本**: 1.18.57  
**维护者**: 投研系统开发组
