#!/bin/bash
# 投研系统 v2.0 - 快速开始脚本

echo "========================================"
echo "  投研系统 v2.0 - 快速开始"
echo "========================================"
echo ""

# 检查Python
echo "1️⃣  检查Python环境..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "   ✓ $PYTHON_VERSION"
else
    echo "   ✗ 未找到Python，请先安装Python 3.8+"
    exit 1
fi

# 检查依赖
echo ""
echo "2️⃣  检查依赖..."
if python3 -c "import akshare" 2>/dev/null; then
    echo "   ✓ akshare 已安装"
else
    echo "   ⚠ akshare 未安装"
    echo "   安装中: pip install akshare pandas"
    pip install akshare pandas
fi

if python3 -c "import pandas" 2>/dev/null; then
    echo "   ✓ pandas 已安装"
else
    echo "   ⚠ pandas 未安装"
    echo "   安装中: pip install pandas"
    pip install pandas
fi

# 创建报告目录
echo ""
echo "3️⃣  准备环境..."
mkdir -p reports
mkdir -p cache
echo "   ✓ 目录已创建"

# 运行演示
echo ""
echo "4️⃣  运行演示程序..."
echo ""
python3 demo.py

echo ""
echo "========================================"
echo "  ✅ 系统已就绪！"
echo "========================================"
echo ""
echo "📚 下一步："
echo ""
echo "  查看文档：cat README_v2.md"
echo ""
echo "  分析股票："
echo "    python3 -m research_system.main analyze 600438"
echo ""
echo "  保存报告："
echo "    python3 -m research_system.main analyze 600438 -o report.md"
echo ""
echo "  批量分析："
echo "    python3 -m research_system.main analyze 600438 601012 002594"
echo ""
