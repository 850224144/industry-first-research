# 新会话快速启动指南

## 🚀 立即开始

在新会话的第一句话说：

```
请阅读以下文档，然后开始开发投研系统：

1. FINAL_REQUIREMENTS.md（最重要的需求文档）
2. HANDOVER_TO_NEW_SESSION.md（项目背景）
3. outputs/投研分析系统-设计文档.md（理解原始理念）

项目路径：
/Users/kaixindelaoliu/PycharmProjects/industry-first-research-main/

从数据采集模块开始实现。
```

---

## 📋 核心需求速览

### 目标
分析上市公司，判断是否值得投资

### 核心输出
```
📊 通威股份投资分析

1. 产品分析
   • 产品：高纯硅料
   • 重要性：⭐⭐⭐⭐⭐（A级-核心原料）
   • 类比：西红柿炒鸡蛋里的"西红柿"
   • 可替代性：无

2. 市场地位
   • 排名：全球第2
   • 份额：18%
   • 结论：龙头企业

3. 竞争力
   • 成本：40元 vs 行业50元（低20%）
   • 优势：规模、技术、一体化

4. 行业周期
   • 当前：底部区域
   • 信号：2/5个反转信号

5. 生存能力
   • 现金：100亿
   • 能撑：20年（极端情况）
   • 结论：能熬过底部

6. 回本周期 ⭐
   • 买入价：15元
   • 悲观(20%)：不回本
   • 基准(60%)：3年，年化16.5%
   • 乐观(20%)：2年，年化30%
   • 期望：2.5年，年化15.3%

7. 投资建议
   💡 可以买，分批建仓
```

---

## 🏗️ 技术架构

### 数据策略
- ✅ 实时API获取（AKShare）
- ✅ 不存原始数据
- ✅ 存研究结论（版本化）
- ✅ Web界面展示

### 核心模块
1. **数据获取** - AKShare API
2. **产品分析** - 产业链定位、重要性评级
3. **市场分析** - 份额、排名、龙头判断
4. **周期分析** - 底部/顶部/反转信号
5. **生存分析** - 现金、债务、压力测试
6. **回本计算** - 三种情景、概率加权
7. **报告生成** - Web展示、版本管理

---

## ✅ 开发优先级

### Phase 1: 数据采集（第一步）
```python
# 实现AKShare数据获取
- 股票基本信息
- 实时行情
- 财务数据
- 行业数据
```

### Phase 2: 产品分析
```python
# 实现产业链分析
- 识别产品在产业链位置
- 评估产品重要性（A/B/C/D）
- 计算可替代性
```

### Phase 3: 市场地位
```python
# 实现市场地位判断
- 计算市场份额
- 判断是否龙头
- 分析竞争格局
```

### Phase 4: 回本周期
```python
# 实现回本周期计算
- 三种情景建模
- 概率加权计算
- 生成投资建议
```

### Phase 5: Web界面
```python
# 实现Web展示
- 输入股票代码
- 展示完整分析
- 清晰的投资建议
```

---

## 🎯 关键算法

### 产品重要性评分
```python
def rate_product_importance(product):
    score = 0
    score += value_ratio * 30        # 价值占比
    score += (1-substitutability) * 30  # 不可替代性
    score += market_concentration * 20  # 市场集中度
    score += tech_barrier * 20       # 技术壁垒
    
    if score >= 80: return "A级-核心原料"
    if score >= 60: return "B级-关键部件"
    if score >= 40: return "C级-重要辅料"
    return "D级-加分项"
```

### 回本周期计算
```python
def calculate_payback(buy_price, scenarios):
    results = []
    for s in scenarios:
        dividend = sum(s['dividends'])
        price_gain = s['exit_price'] - buy_price
        total = dividend + price_gain
        years = s['years']
        annual = total / buy_price / years
        results.append({
            'scenario': s['name'],
            'prob': s['probability'],
            'years': years,
            'return': total / buy_price * 100,
            'annual': annual * 100
        })
    
    expected = sum(r['return'] * r['prob'] for r in results)
    return results, expected
```

---

## 📖 示例对话

**新会话开始时**：
```
User: 请阅读FINAL_REQUIREMENTS.md，然后开始开发

AI: 已阅读需求文档。我理解了"西红柿炒鸡蛋"的分析理念。
    
    系统需要：
    1. 分析产品在产业链的位置和重要性
    2. 判断公司是否龙头
    3. 预测回本周期
    4. 给出明确投资建议
    
    现在开始实现Phase 1：数据采集模块
    
    首先创建data_fetcher.py...
```

---

## ⚠️ 重要提醒

### 不要做的事
- ❌ 不要参考旧代码（src/目录下89个模块）
- ❌ 不要使用静态JSON数据
- ❌ 不要过度设计
- ❌ 不要忘记"西红柿炒鸡蛋"的核心理念

### 必须做的事
- ✅ 实时API获取数据（AKShare）
- ✅ 实现产品重要性分级
- ✅ 实现回本周期计算（三种情景）
- ✅ 清晰的投资建议
- ✅ 保持简单实用

---

## 🎓 核心理念

**一句话总结**：
用"西红柿炒鸡蛋"的逻辑，看清公司产品在产业链的位置、市场地位、生存能力，预测回本周期，给出明确投资建议。

**关键问题**：
1. 这公司干啥的？
2. 是不是龙头？
3. 能不能活？
4. 会不会更好？
5. 多久回本？

---

**准备好了，开新会话吧！** 🚀
