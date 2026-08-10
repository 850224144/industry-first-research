# Web界面使用说明

## 启动Web服务

```bash
cd /Users/kaixindelaoliu/PycharmProjects/industry-first-research-main
python web/app.py
```

## 访问地址

打开浏览器访问：**http://127.0.0.1:5001**

## 功能页面

1. **首页** (/) 
   - 系统概览
   - 统计数据
   - 核心功能入口

2. **行业雷达** (/radar)
   - 查看3个行业的实时信号
   - 拐点候选识别（光伏）
   - 稳定行业（电力）
   - 观察行业（煤炭）

3. **商品品种** (/commodities)
   - 6个商品品种列表
   - 配置详情查看

4. **公司列表** (/companies)
   - 已配置公司
   - 上海电力、通威股份等

5. **演示** (/demo)
   - 天然橡胶期货分析
   - 上海电力股票分析
   - 完整分析流程展示

## API接口

- `GET /api/status` - 系统状态
- `GET /api/radar/latest` - 最新行业雷达
- `GET /api/commodities` - 商品品种列表
- `GET /api/companies` - 公司列表
- `GET /api/commodity/<id>` - 商品详情
- `GET /api/company/<id>` - 公司详情

## 技术栈

- 后端: Flask (Python)
- 前端: HTML + CSS + JavaScript
- 数据: JSON文件
- 样式: 响应式设计

## 下一步

现在可以在浏览器中验证Web界面功能！
