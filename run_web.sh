#!/bin/bash
# Web应用启动脚本

echo "🚀 启动投研系统Web界面..."
echo ""

# 检查streamlit
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "⚠️  streamlit未安装，正在安装..."
    pip install streamlit
    echo ""
fi

# 启动应用
echo "✓ 启动中..."
echo ""
echo "📱 Web界面将在浏览器中打开"
echo "🔗 地址：http://localhost:8501"
echo ""
echo "💡 提示：按 Ctrl+C 停止服务"
echo ""

streamlit run web_app.py
