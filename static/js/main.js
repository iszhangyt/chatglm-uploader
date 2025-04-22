// DOM元素
const dropArea = document.getElementById('drop-area');
const fileInput = document.getElementById('file-input');
const uploadForm = document.getElementById('upload-form');
const channelSelect = document.getElementById('channel-select');
const uploadProgress = document.getElementById('upload-progress');
const progressBarInner = document.getElementById('progress-bar-inner');
const progressPercentage = document.getElementById('progress-percentage');
const resultSection = document.getElementById('result-section');
const resultImg = document.getElementById('result-img');
const imageUrl = document.getElementById('image-url');
const htmlCode = document.getElementById('html-code');
const markdownCode = document.getElementById('markdown-code');
const fileName = document.getElementById('file-name');
const imageSize = document.getElementById('image-size');
const uploadChannel = document.getElementById('upload-channel');
const copyUrlBtn = document.getElementById('copy-url-btn');
const copyHtmlBtn = document.getElementById('copy-html-btn');
const copyMdBtn = document.getElementById('copy-md-btn');
const uploadAnotherBtn = document.getElementById('upload-another-btn');
const historyList = document.getElementById('history-list');
const refreshHistoryBtn = document.getElementById('refresh-history-btn');
const clearHistoryBtn = document.getElementById('clear-history-btn');
const toast = document.getElementById('toast');

// 上传状态标记
let isUploading = false;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 检查验证状态
    checkVerification();
});

// 检查验证状态
function checkVerification() {
    const token = localStorage.getItem('verificationToken');
    
    // 验证令牌存在，验证其有效性
    if (token) {
        fetch('/api/check_verification', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ token: token })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 0) {
                // 验证有效，初始化应用
                initializeApp();
            } else {
                // 验证无效，跳转到验证页
                redirectToVerify();
            }
        })
        .catch(error => {
            console.error('验证检查失败:', error);
            redirectToVerify();
        });
    } else {
        // 没有验证令牌，跳转到验证页
        redirectToVerify();
    }
}

// 跳转到验证页
function redirectToVerify() {
    window.location.href = '/verify';
}

// 初始化应用
function initializeApp() {
    loadHistory();
    setupEventListeners();
    // 恢复用户选择的渠道
    restoreSelectedChannel();
}

// 设置事件监听器
function setupEventListeners() {
    // 文件选择事件
    fileInput.addEventListener('change', handleFileSelect);
    
    // 防止表单默认提交行为
    uploadForm.addEventListener('submit', (e) => {
        e.preventDefault();
        return false;
    });
    
    // 渠道选择事件 - 保存用户选择
    channelSelect.addEventListener('change', (e) => {
        saveSelectedChannel(e.target.value);
    });
    
    // 拖放区域事件
    dropArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropArea.classList.add('dragover');
    });
    
    dropArea.addEventListener('dragleave', () => {
        dropArea.classList.remove('dragover');
    });
    
    dropArea.addEventListener('drop', (e) => {
        e.preventDefault();
        dropArea.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFiles(e.dataTransfer.files);
        }
    });
    
    // 阻止渠道选择器事件冒泡
    document.querySelector('.channel-selector').addEventListener('click', (e) => {
        e.stopPropagation();
    });
    
    // 点击上传区域选择文件 - 改为只在标签上触发
    document.querySelector('.file-label').addEventListener('click', (e) => {
        // 阻止事件冒泡，防止触发dropArea的点击事件
        e.stopPropagation();
    });
    
    // 点击整个区域也可以选择文件，但通过标记防止重复触发
    let isSelecting = false;
    dropArea.addEventListener('click', (e) => {
        // 防止重复打开文件选择器
        if (!isSelecting) {
            isSelecting = true;
            fileInput.click();
            // 短暂延迟后重置标记
            setTimeout(() => {
                isSelecting = false;
            }, 500);
        }
    });
    
    // 复制按钮事件
    copyUrlBtn.addEventListener('click', () => copyText(imageUrl, '图片链接已复制'));
    copyHtmlBtn.addEventListener('click', () => copyText(htmlCode, 'HTML代码已复制'));
    copyMdBtn.addEventListener('click', () => copyText(markdownCode, 'Markdown代码已复制'));
    
    // 继续上传按钮
    uploadAnotherBtn.addEventListener('click', resetUploadForm);
    
    // 历史记录按钮
    refreshHistoryBtn.addEventListener('click', loadHistory);
    clearHistoryBtn.addEventListener('click', clearHistory);
}

// 处理选择的文件
function handleFileSelect(e) {
    if (e.target.files && e.target.files.length) {
        handleFiles(e.target.files);
        // 重置文件输入框，以便能够重新选择相同的文件
        // e.target.value = '';  // 注释掉此行，避免在处理过程中清空
    }
}

// 处理文件上传
function handleFiles(files) {
    // 防止重复上传
    if (isUploading) {
        return;
    }
    
    const file = files[0]; // 只处理第一个文件
    if (!file) {
        return;
    }
    
    // 验证文件类型
    const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp'];
    if (!validTypes.includes(file.type)) {
        showToast('请选择图片文件（JPG, PNG, GIF, BMP, WEBP）');
        return;
    }
    
    // 标记上传状态
    isUploading = true;
    
    // 显示进度条
    uploadProgress.hidden = false;
    progressBarInner.style.width = '0%';
    progressPercentage.textContent = '0%';
    
    // 获取选择的渠道
    const selectedChannel = channelSelect.value;
    
    // 创建FormData
    const formData = new FormData();
    formData.append('file', file);
    formData.append('channel', selectedChannel);
    
    // 发送上传请求
    const xhr = new XMLHttpRequest();
    
    // 上传进度事件
    xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
            const percentComplete = Math.round((e.loaded / e.total) * 100);
            progressBarInner.style.width = `${percentComplete}%`;
            progressPercentage.textContent = `${percentComplete}%`;
        }
    });
    
    // 上传完成事件
    xhr.addEventListener('load', () => {
        // 重置上传状态
        isUploading = false;
        
        if (xhr.status === 200) {
            try {
                const response = JSON.parse(xhr.responseText);
                if (response.status === 0) {
                    handleUploadSuccess(response.result, file.name);
                    loadHistory(); // 刷新历史记录
                } else {
                    showToast(`上传失败: ${response.message}`);
                }
            } catch (e) {
                showToast('解析响应失败');
            }
        } else if (xhr.status === 401) {
            // 验证已过期，重新验证
            localStorage.removeItem('verificationToken');
            redirectToVerify();
            showToast('验证已过期，请重新验证');
        } else {
            showToast(`上传失败: ${xhr.statusText}`);
        }
        uploadProgress.hidden = true;
        
        // 重置文件输入框，以便能够重新选择相同的文件
        fileInput.value = '';
    });
    
    // 上传错误事件
    xhr.addEventListener('error', () => {
        isUploading = false;
        showToast('上传失败，请检查网络连接');
        uploadProgress.hidden = true;
        fileInput.value = '';
    });
    
    // 上传中断事件
    xhr.addEventListener('abort', () => {
        isUploading = false;
        showToast('上传已取消');
        uploadProgress.hidden = true;
        fileInput.value = '';
    });
    
    // 发送请求
    xhr.open('POST', '/upload');
    
    // 添加验证令牌
    const token = localStorage.getItem('verificationToken');
    if (token) {
        xhr.setRequestHeader('X-Verification-Token', token);
    }
    
    xhr.send(formData);
}

// 处理上传成功
function handleUploadSuccess(result, originalFileName) {
    // 隐藏上传区域，显示结果区域
    dropArea.hidden = true;
    resultSection.hidden = false;
    
    // 设置图片和信息
    resultImg.src = result.file_url;
    imageUrl.value = result.file_url;
    htmlCode.value = `<img src="${result.file_url}" alt="${originalFileName}">`;
    markdownCode.value = `![${originalFileName}](${result.file_url})`;
    fileName.textContent = originalFileName;
    
    // 处理图片尺寸显示
    if (result.width && result.height) {
        imageSize.textContent = `${result.width} × ${result.height}`;
    } else {
        imageSize.textContent = '尺寸未知';
    }
    
    // 显示上传渠道
    const channelMap = {
        'chatglm': 'ChatGLM',
        'jd': '京东'
    };
    uploadChannel.textContent = channelMap[channelSelect.value] || channelSelect.value;
}

// 重置上传表单
function resetUploadForm() {
    dropArea.hidden = false;
    resultSection.hidden = true;
    fileInput.value = '';
}

// 加载历史记录
function loadHistory() {
    const token = localStorage.getItem('verificationToken');
    
    fetch('/history', {
        headers: {
            'X-Verification-Token': token
        }
    })
    .then(response => {
        if (response.status === 401) {
            // 验证已过期，重新验证
            localStorage.removeItem('verificationToken');
            redirectToVerify();
            throw new Error('验证已过期');
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 0) {
            renderHistoryList(data.result);
        } else {
            showToast(`获取历史记录失败: ${data.message}`);
        }
    })
    .catch(error => {
        if (error.message !== '验证已过期') {
            showToast('获取历史记录失败');
            console.error('Error loading history:', error);
        }
    });
}

// 渲染历史记录列表
function renderHistoryList(history) {
    historyList.innerHTML = '';
    
    if (history.length === 0) {
        historyList.innerHTML = '<div class="no-history">暂无上传记录</div>';
        return;
    }
    
    // 渠道名称映射
    const channelMap = {
        'chatglm': 'ChatGLM',
        'jd': '京东'
    };
    
    history.forEach(item => {
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';
        historyItem.innerHTML = `
            <img class="history-item-img" src="${item.file_url}" alt="${item.file_name}">
            <div class="history-item-info">
                <div class="history-item-name" title="${item.file_name}">${item.file_name}</div>
                <div class="history-item-time">${item.upload_time}</div>
                <div class="history-item-channel">${channelMap[item.channel] || item.channel || '未知'}</div>
            </div>
            <div class="history-item-actions">
                <button class="btn copy-url-btn" data-url="${item.file_url}">复制链接</button>
                <button class="btn delete-btn" data-id="${item.id}">删除</button>
            </div>
        `;
        
        // 获取复制和删除按钮
        const copyUrlButton = historyItem.querySelector('.copy-url-btn');
        const deleteButton = historyItem.querySelector('.delete-btn');
        
        // 添加事件监听器
        copyUrlButton.addEventListener('click', () => {
            copyToClipboard(item.file_url, '图片链接已复制');
        });
        
        deleteButton.addEventListener('click', () => {
            deleteHistoryItem(item.id);
        });
        
        historyList.appendChild(historyItem);
    });
}

// 删除历史记录项
function deleteHistoryItem(id) {
    const token = localStorage.getItem('verificationToken');
    
    fetch(`/delete_history/${id}`, { 
        method: 'DELETE',
        headers: {
            'X-Verification-Token': token
        }
    })
    .then(response => {
        if (response.status === 401) {
            // 验证已过期，重新验证
            localStorage.removeItem('verificationToken');
            redirectToVerify();
            throw new Error('验证已过期');
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 0) {
            loadHistory(); // 刷新历史记录
            showToast('删除成功');
        } else {
            showToast(`删除失败: ${data.message}`);
        }
    })
    .catch(error => {
        if (error.message !== '验证已过期') {
            showToast('删除失败');
            console.error('Error deleting history item:', error);
        }
    });
}

// 清空历史记录
function clearHistory() {
    if (!confirm('确定要清空所有上传历史吗？')) {
        return;
    }
    
    const token = localStorage.getItem('verificationToken');
    
    fetch('/clear_history', { 
        method: 'DELETE',
        headers: {
            'X-Verification-Token': token
        }
    })
    .then(response => {
        if (response.status === 401) {
            // 验证已过期，重新验证
            localStorage.removeItem('verificationToken');
            redirectToVerify();
            throw new Error('验证已过期');
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 0) {
            loadHistory(); // 刷新历史记录
            showToast('历史记录已清空');
        } else {
            showToast(`清空失败: ${data.message}`);
        }
    })
    .catch(error => {
        if (error.message !== '验证已过期') {
            showToast('清空失败');
            console.error('Error clearing history:', error);
        }
    });
}

// 复制文本到剪贴板
function copyToClipboard(text, successMessage) {
    navigator.clipboard.writeText(text)
        .then(() => showToast(successMessage || '复制成功'))
        .catch(() => showToast('复制失败'));
}

// 复制文本
function copyText(input, successMessage) {
    input.select();
    copyToClipboard(input.value, successMessage);
}

// 显示提示消息
function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            toast.hidden = true;
            toast.style.opacity = '1';
        }, 300);
    }, 2000);
}

// 保存用户选择的渠道到localStorage
function saveSelectedChannel(channel) {
    localStorage.setItem('preferredUploadChannel', channel);
}

// 从localStorage恢复用户选择的渠道
function restoreSelectedChannel() {
    const savedChannel = localStorage.getItem('preferredUploadChannel');
    if (savedChannel) {
        channelSelect.value = savedChannel;
    }
} 