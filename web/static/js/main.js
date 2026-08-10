// 加载系统状态
async function loadSystemStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        document.getElementById('commodity-count').textContent = data.statistics.commodity_varieties;
        document.getElementById('company-count').textContent = data.statistics.company_configs;
        document.getElementById('test-count').textContent = data.statistics.total_tests;
        document.getElementById('status').textContent = data.status === 'online' ? '在线' : '离线';
        document.getElementById('status').style.color = data.status === 'online' ? '#27ae60' : '#e74c3c';
    } catch (error) {
        console.error('加载系统状态失败:', error);
    }
}

// 页面加载时执行
if (document.getElementById('stats')) {
    loadSystemStatus();
}

// 通用工具函数
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

function formatNumber(num) {
    return num.toLocaleString('zh-CN');
}
