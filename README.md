# 📊 投研分析系统 v3.0

> 用"西红柿炒鸡蛋"的逻辑分析上市公司投资价值

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🚀 快速开始

### Web界面（推荐）

```bash
bash run_web.sh
# 浏览器自动打开 http://localhost:8501
```

### 命令行

```bash
# 演示
python demo.py

# 分析股票
python -m research_system.main analyze 600438
```

---

## 🎯 核心功能

- 📊 **8维度分析** - 财务、行业、估值、趋势
- 💰 **回本周期** - 三种情景预测，概率加权
- 🎯 **明确建议** - 买入/观望/不买
- 📈 **行业对比** - 排名、对比、看清位置
- 💎 **估值分析** - PE/PB/PEG，判断贵不贵
- 🌐 **Web界面** - 美观易用，零学习成本

---

## 💡 核心理念

### "西红柿炒鸡蛋"逻辑

| 级别 | 类比 | 特征 | 议价能力 |
|------|------|------|----------|
| A级 | 西红柿 | 核心原料 | ⭐⭐⭐⭐⭐ |
| B级 | 鸡蛋 | 关键部件 | ⭐⭐⭐⭐ |
| C级 | 食用油 | 重要辅料 | ⭐⭐⭐ |
| D级 | 葱花 | 加分项 | ⭐⭐ |

---

## 📊 输出示例

```
📊 通威股份（600438）

✅ 可以买入（75分）

【市场地位】行业排名第3 | 市值1050亿
【财务健康】B-良好 | ROE 7.5%
【估值水平】相对低估 | PE 18.5 vs 行业25.3
【回本周期】预期2.8年 | 年化15.3%

操作策略：分3批建仓，设-20%止损
```

---

## 📖 文档

- [Web使用指南](WEB_GUIDE.md)
- [CLI使用指南](README_v2.md)
- [实现报告](IMPLEMENTATION_REPORT.md)
- [完整总结](FINAL_COMPLETION_SUMMARY.md)

---

## 🔧 技术特点

- ✅ **100%基于API** - AKShare实时数据
- ✅ **极简架构** - 5个核心模块，3000行代码
- ✅ **零维护** - 无需手动更新数据

---

## ⚠️ 声明

本系统仅供参考，不构成投资建议。投资有风险，决策需谨慎。

---

**立即开始：`bash run_web.sh`** 🚀
