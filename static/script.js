// static/script.js
document.addEventListener('DOMContentLoaded', () => {
    const temperatureElement = document.getElementById('temperature');
    const humidityElement = document.getElementById('humidity');
    const weightElement = document.getElementById('weight');
    const catDetectedElement = document.getElementById('cat-detected');
    const modeSwitch = document.getElementById('mode-switch');
    const modeLabel = document.getElementById('mode-label');
    const feedButton = document.getElementById('feed-button');
    const controlMessage = document.getElementById('control-message');
    const feedAmount = document.getElementById('feed-amount');
    const defaultFeedAmount = document.getElementById('default-feed-amount');
    const minFoodLevel = document.getElementById('min-food-level');
    const saveSettingsButton = document.getElementById('save-settings');
    const addScheduleButton = document.getElementById('add-schedule-btn');
    const scheduleModal = document.getElementById('schedule-modal');
    const scheduleForm = document.getElementById('schedule-form');
    const closeModalButton = scheduleModal.querySelector('.close');
    const cancelScheduleButton = document.getElementById('cancel-schedule');
    const scheduleContainer = document.getElementById('schedule-container');

    // 检查关键元素是否存在
    console.log("关键元素检查:");
    console.log("- 模式开关存在:", modeSwitch !== null);
    console.log("- 模式标签存在:", modeLabel !== null);
    console.log("- 喂食按钮存在:", feedButton !== null);

    if (!modeSwitch) {
        console.error("错误: 找不到ID为'mode-switch'的元素!");
        alert("界面初始化错误: 找不到模式切换开关");
        return;  // 终止进一步执行
    }

    let currentMode = 'manual'; // Default to manual, will be updated from server
    let lastFeedingTime = 0; // Timestamp of the last feeding action
    let catDetectionState = false; // Current cat detection status
    let currentWeight = null; // Current food weight in kg
    let isSwitchingMode = false; // Flag to prevent state override during switch

    // 健康监测元素
    const heartRateElement = document.getElementById('heart-rate');
    const bloodOxygenElement = document.getElementById('blood-oxygen');
    const heartRateFill = document.querySelector('.heart-rate-fill');
    const oxygenFill = document.querySelector('.oxygen-fill');

    // 猫粮状态元素
    const foodLevelFill = document.getElementById('food-level-fill');

    // 模拟健康数据更新
    function simulateHealthData() {
        const newHeartRate = Math.floor(Math.random() * 40) + 60;
        heartRateElement.textContent = newHeartRate;
        const heartRatePercentage = (newHeartRate - 40) / 100;
        heartRateFill.style.width = `${Math.min(100, Math.max(0, heartRatePercentage * 100))}%`;

        const newOxygen = Math.floor(Math.random() * 5) + 95;
        bloodOxygenElement.textContent = newOxygen;
        const oxygenPercentage = (newOxygen - 90) / 10;
        oxygenFill.style.width = `${Math.min(100, Math.max(0, oxygenPercentage * 100))}%`;
    }

    // 更新猫粮水平显示
    function updateFoodLevel(weight) {
        currentWeight = (weight !== null && !isNaN(weight)) ? weight : null;
        let percentage = 0;
        if (currentWeight !== null) {
            const maxWeight = 2.0;
            percentage = Math.min(100, Math.max(0, (currentWeight / maxWeight) * 100));
        }

        if (foodLevelFill) {
            foodLevelFill.style.height = `${percentage}%`;
            if (percentage < 20) {
                foodLevelFill.style.background = 'linear-gradient(to bottom, #ff6b6b, #e74c3c)';
            } else if (percentage < 40) {
                foodLevelFill.style.background = 'linear-gradient(to bottom, #f39c12, #e67e22)';
            } else {
                foodLevelFill.style.background = 'linear-gradient(to bottom, var(--secondary-light), var(--secondary-color))';
            }
        }
    }

    // 检查自动喂食条件
    function checkAutoFeedCondition() {
        if (currentMode !== 'auto' || isSwitchingMode) return; // Don't auto-feed while switching mode

        const currentTime = Date.now();
        const timeSinceLastFeed = currentTime - lastFeedingTime;

        // 获取最小食物水平设置
        const minLevel = parseFloat(minFoodLevel.value) || 0.5;

        if (catDetectionState && currentWeight !== null && currentWeight < minLevel && timeSinceLastFeed > 10000) {
            console.log('满足自动喂食条件，执行喂食...');
            autoFeed();
        }
    }

    // 自动喂食函数
    async function autoFeed() {
        const currentTime = Date.now();
        if ((currentTime - lastFeedingTime) <= 10000) {
            console.log('自动喂食冷却中，取消本次触发。');
            return;
        }
        lastFeedingTime = currentTime;

        try {
            // 获取默认喂食量
            const feedAmountValue = parseFloat(defaultFeedAmount.value) || 30;

            showMessage('检测到猫咪且食物不足，自动喂食中...', 'info');
            const response = await fetch('/api/feed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: feedAmountValue })
            });
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                showMessage(result.message || '自动喂食成功!', 'success');
            } else {
                showMessage(result.message || '自动喂食失败', 'error');
                lastFeedingTime = Date.now() - 8000;
            }
        } catch (error) {
            console.error("自动喂食请求失败:", error);
            showMessage('自动喂食请求失败，请检查网络连接', 'error');
            lastFeedingTime = Date.now() - 8000;
        }
    }

    // --- Function to update sensor data and check conditions ---
    async function updateSensorData() {
        // If a mode switch is in progress, skip this update to avoid conflicts
        if (isSwitchingMode) {
            console.log("模式切换进行中，跳过本次传感器数据更新");
            return;
        }

        try {
            const response = await fetch('/api/sensor_data');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            // Update UI elements
            temperatureElement.textContent = data.temperature !== null ? data.temperature.toFixed(1) : '--';
            humidityElement.textContent = data.humidity !== null ? data.humidity.toFixed(1) : '--';
            const weight = data.weight !== null ? data.weight : null;
            weightElement.textContent = weight !== null ? weight.toFixed(3) : '--';
            updateFoodLevel(weight);

            catDetectionState = data.cat_detected === true;
            if (data.cat_detected !== null) {
                catDetectedElement.textContent = catDetectionState ? '检测到' : '未检测到';
                catDetectedElement.className = catDetectionState ? 'detected' : 'not-detected';
            } else {
                catDetectedElement.textContent = '未知';
                catDetectedElement.className = '';
            }

            // Update mode from server data ONLY if it exists AND differs from local state
            // AND a mode switch isn't currently in progress
            if (data.mode && data.mode !== currentMode) {
                console.log(`服务器模式 (${data.mode}) 与本地模式 (${currentMode}) 不同，进行更新`);
                currentMode = data.mode;
                updateModeUI(); // Update UI based on server state
            } else {
                // Ensure UI reflects current local state even if server matches
                updateModeUI();
            }

            // 更新喂食计划列表（如果存在）
            if (data.schedules) {
                updateSchedulesList(data.schedules);
            }

            // 检查是否有定时喂食需要执行
            if (data.scheduled_feed && currentMode === 'auto') {
                if (data.feed_success) {
                    // 喂食成功
                    showMessage(data.feed_message || `定时喂食计划触发，正在喂食 ${data.feed_amount}g 猫粮...`, 'success');
                    lastFeedingTime = Date.now();
                } else if (data.feed_cooldown) {
                    // 喂食冷却中
                    showMessage(data.feed_message || `喂食冷却中，还需等待 ${data.cooldown_time} 秒`, 'info');
                } else if (data.feed_message) {
                    // 其他喂食相关消息
                    showMessage(data.feed_message, data.feed_success ? 'success' : 'error');
                } else {
                    // 兜底消息
                    showMessage(`定时喂食计划触发，正在喂食 ${data.feed_amount}g 猫粮...`, 'info');
                }
            }

            // Check auto feed condition AFTER all state is potentially updated
            checkAutoFeedCondition();

        } catch (error) {
            console.error("无法获取传感器数据:", error);
            temperatureElement.textContent = '错误';
            humidityElement.textContent = '错误';
            weightElement.textContent = '错误';
            catDetectedElement.textContent = '错误';
        }
    }

    // Function to update the mode switch UI based on currentMode variable
    function updateModeUI() {
        const isAuto = currentMode === 'auto';
        console.log(`更新UI: 当前模式=${currentMode}, 开关应设为${isAuto ? '开启' : '关闭'}`);

        try {
            // 只有在当前状态与目标状态不同时才更新
            if (modeSwitch.checked !== isAuto) {
                console.log(`更新开关状态: ${modeSwitch.checked} -> ${isAuto}`);
                modeSwitch.checked = isAuto;
            }

            modeLabel.textContent = isAuto ? '自动模式' : '手动模式';
            feedButton.disabled = isAuto;
        } catch (error) {
            console.error("更新模式UI时出错:", error);
        }
    }

    // --- Function to display control messages ---
    function showMessage(message, type = 'info') {
        controlMessage.textContent = message;
        controlMessage.className = `message ${type}`;
        setTimeout(() => {
            controlMessage.textContent = '';
            controlMessage.className = 'message';
        }, 5000);
    }

    // --- Event Listener for Manual Feed Button ---
    feedButton.addEventListener('click', async () => {
        if (currentMode === 'auto') {
            showMessage('请先切换到手动模式', 'error');
            return;
        }

        const currentTime = Date.now();
        if ((currentTime - lastFeedingTime) <= 5000) {
            showMessage('喂食操作过于频繁，请稍候...', 'warning');
            return;
        }

        feedButton.disabled = true;
        showMessage('正在发送喂食指令...', 'info');

        try {
            // 获取自定义喂食量
            const feedAmountValue = parseFloat(feedAmount.value) || 30;

            const response = await fetch('/api/feed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: feedAmountValue })
            });
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                showMessage(result.message || '喂食成功!', 'success');
                lastFeedingTime = Date.now();
            } else {
                showMessage(result.message || '喂食失败', 'error');
            }
        } catch (error) {
            console.error("喂食请求失败:", error);
            showMessage('喂食请求失败，请检查网络连接', 'error');
        } finally {
            setTimeout(() => {
                if (currentMode === 'manual') {
                    feedButton.disabled = false;
                }
            }, 1000);
        }
    });

    // --- Event Listener for Mode Switch --- 
    console.log("正在为模式开关绑定事件监听器...");

    // 先移除可能存在的旧监听器，防止重复绑定
    modeSwitch.removeEventListener('change', handleModeSwitch);

    // 将事件处理函数声明为命名函数，便于调试和移除
    async function handleModeSwitch(event) {
        console.log("模式开关被点击!");
        console.log("开关当前状态:", modeSwitch.checked);

        // 防止快速点击
        if (isSwitchingMode) {
            console.log("模式切换进行中，忽略本次点击");
            return;
        }

        // 设置切换状态标志
        isSwitchingMode = true;
        const newMode = modeSwitch.checked ? 'auto' : 'manual';
        console.log(`尝试切换模式到: ${newMode}`);

        try {
            showMessage(`正在切换到${newMode === 'auto' ? '自动' : '手动'}模式...`, 'info');

            const response = await fetch('/api/mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: newMode })
            });

            console.log("API响应状态:", response.status);
            const result = await response.json();
            console.log("模式切换API响应:", result);

            if (response.ok && result.status === 'success') {
                currentMode = result.current_mode;
                console.log(`模式成功切换为: ${currentMode}`);
                updateModeUI();
                showMessage(result.message || `成功切换到${currentMode === 'auto' ? '自动' : '手动'}模式`, 'success');

                if (currentMode === 'auto') {
                    checkAutoFeedCondition();
                }
            } else {
                console.error('模式切换失败，服务器返回:', result);
                showMessage(result.message || '模式切换失败，请重试', 'error');

                // 恢复到之前的状态
                currentMode = (newMode === 'auto') ? 'manual' : 'auto';
                updateModeUI();
            }
        } catch (error) {
            console.error("模式切换请求失败:", error);
            showMessage('模式切换请求失败，请检查网络连接', 'error');

            // 恢复到之前的状态
            currentMode = (newMode === 'auto') ? 'manual' : 'auto';
            updateModeUI();
        } finally {
            console.log("切换操作完成，重置状态标志");
            setTimeout(() => {
                isSwitchingMode = false;
            }, 500); // 增加短暂延迟，避免过快重置
        }
    }

    // 绑定事件处理函数
    modeSwitch.addEventListener('change', handleModeSwitch);

    // 同时添加click监听器作为备份
    modeSwitch.addEventListener('click', function (event) {
        console.log("检测到模式开关Click事件");
    });

    // 添加父元素点击事件监听
    if (modeSwitch.parentElement) {
        console.log("为开关父元素添加点击监听器");
        modeSwitch.parentElement.addEventListener('click', function (event) {
            console.log("检测到开关父元素点击");
            // 直接触发开关状态改变
            modeSwitch.checked = !modeSwitch.checked;
            // 手动触发change事件
            modeSwitch.dispatchEvent(new Event('change'));
        });
    }

    // 添加全局键盘快捷键（用于测试）
    document.addEventListener('keydown', function (event) {
        // 按M键切换模式
        if (event.key === 'm' || event.key === 'M') {
            console.log("检测到键盘快捷键切换模式");
            modeSwitch.checked = !modeSwitch.checked;
            modeSwitch.dispatchEvent(new Event('change'));
        }
    });

    console.log("模式开关事件监听器已绑定");

    // --- 设置保存功能 ---
    saveSettingsButton.addEventListener('click', async () => {
        const newDefaultAmount = parseFloat(defaultFeedAmount.value);
        const newMinFoodLevel = parseFloat(minFoodLevel.value);

        if (isNaN(newDefaultAmount) || isNaN(newMinFoodLevel)) {
            showMessage('请输入有效的数字', 'error');
            return;
        }

        try {
            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    default_feed_amount: newDefaultAmount,
                    min_food_level: newMinFoodLevel,
                    auto_feed_enabled: modeSwitch.checked
                })
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                showMessage('设置已保存', 'success');
                // 更新喂食量输入框默认值
                feedAmount.value = newDefaultAmount;
            } else {
                showMessage(result.message || '保存设置失败', 'error');
            }
        } catch (error) {
            console.error("保存设置失败:", error);
            showMessage('保存设置失败，请检查网络连接', 'error');
        }
    });

    // --- 喂食计划管理 ---
    function updateSchedulesList(schedules) {
        if (!scheduleContainer) return;

        // 清空现有内容
        scheduleContainer.innerHTML = '';

        if (schedules.length === 0) {
            const emptyMessage = document.createElement('p');
            emptyMessage.className = 'empty-message';
            emptyMessage.textContent = '暂无喂食计划，请添加';
            scheduleContainer.appendChild(emptyMessage);
            return;
        }

        // 添加每个计划项
        schedules.forEach(schedule => {
            const item = document.createElement('div');
            item.className = 'schedule-item';
            item.dataset.id = schedule.id;

            const timeSpan = document.createElement('span');
            timeSpan.className = 'time';
            timeSpan.textContent = schedule.time;

            const amountSpan = document.createElement('span');
            amountSpan.className = 'amount';
            amountSpan.textContent = `${schedule.amount}g`;

            const actions = document.createElement('div');
            actions.className = 'schedule-actions';

            // 删除按钮
            const deleteButton = document.createElement('button');
            deleteButton.className = 'delete-schedule mini-button';
            deleteButton.innerHTML = '<i class="fa-solid fa-trash"></i>';

            deleteButton.addEventListener('click', async () => {
                if (confirm('确定要删除这个喂食计划吗？')) {
                    try {
                        const response = await fetch(`/api/schedule/${schedule.id}`, {
                            method: 'DELETE'
                        });

                        const result = await response.json();

                        if (response.ok && result.status === 'success') {
                            item.remove();
                            showMessage('喂食计划删除成功', 'success');

                            // 如果删除后没有计划，显示空消息
                            if (scheduleContainer.children.length === 0) {
                                const emptyMessage = document.createElement('p');
                                emptyMessage.className = 'empty-message';
                                emptyMessage.textContent = '暂无喂食计划，请添加';
                                scheduleContainer.appendChild(emptyMessage);
                            }
                        } else {
                            showMessage(result.message || '删除计划失败', 'error');
                        }
                    } catch (error) {
                        console.error("删除计划失败:", error);
                        showMessage('删除失败，请检查网络连接', 'error');
                    }
                }
            });

            actions.appendChild(deleteButton);

            item.appendChild(timeSpan);
            item.appendChild(amountSpan);
            item.appendChild(actions);

            scheduleContainer.appendChild(item);
        });
    }

    // 添加计划按钮点击事件
    if (addScheduleButton) {
        addScheduleButton.addEventListener('click', () => {
            scheduleModal.style.display = 'block';
        });
    }

    // 关闭模态框事件
    if (closeModalButton) {
        closeModalButton.addEventListener('click', () => {
            scheduleModal.style.display = 'none';
        });
    }

    if (cancelScheduleButton) {
        cancelScheduleButton.addEventListener('click', () => {
            scheduleModal.style.display = 'none';
        });
    }

    // 点击模态框外部关闭
    window.addEventListener('click', (event) => {
        if (event.target === scheduleModal) {
            scheduleModal.style.display = 'none';
        }
    });

    // 表单提交事件
    if (scheduleForm) {
        scheduleForm.addEventListener('submit', async (event) => {
            event.preventDefault();

            const timeInput = document.getElementById('schedule-time');
            const amountInput = document.getElementById('schedule-amount');

            if (!timeInput.value) {
                showMessage('请选择喂食时间', 'error');
                return;
            }

            const amount = parseFloat(amountInput.value);
            if (isNaN(amount) || amount <= 0) {
                showMessage('请输入有效的喂食量', 'error');
                return;
            }

            try {
                const response = await fetch('/api/schedule', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        time: timeInput.value,
                        amount: amount
                    })
                });

                const result = await response.json();

                if (response.ok && result.status === 'success') {
                    showMessage('喂食计划添加成功', 'success');
                    scheduleModal.style.display = 'none';

                    // 刷新计划列表
                    await updateSensorData();
                } else {
                    showMessage(result.message || '添加计划失败', 'error');
                }
            } catch (error) {
                console.error("添加计划失败:", error);
                showMessage('添加失败，请检查网络连接', 'error');
            }
        });
    }

    // --- Initial data load and periodic update ---
    console.log('页面加载完成，正在初始化数据...');

    // Function to fetch initial state and start intervals
    async function initializeApp() {
        try {
            // 手动检查开关初始状态
            console.log("初始化前开关状态:", modeSwitch.checked);

            await updateSensorData(); // Load initial data including mode
            console.log(`初始化模式设置为: ${currentMode}`);
            console.log("初始化后开关状态:", modeSwitch.checked);

            // Start periodic updates AFTER initial load
            setInterval(updateSensorData, 3000);

            // Initialize health data simulation
            simulateHealthData();
            setInterval(simulateHealthData, 5000);

            // Initialize last feeding time
            lastFeedingTime = Date.now() - 15000;
            console.log('初始化完成，定时器已启动');
        } catch (error) {
            console.error("初始化过程出错:", error);
            alert("系统初始化失败，请刷新页面重试");
        }
    }

    initializeApp(); // Start the initialization process

    // 暴露一些函数到全局范围，便于调试
    window.catFeederDebug = {
        getCurrentMode: () => currentMode,
        toggleMode: async () => {
            const newMode = currentMode === 'auto' ? 'manual' : 'auto';
            try {
                const response = await fetch('/api/mode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode: newMode })
                });
                const result = await response.json();
                console.log("手动切换结果:", result);
                return result;
            } catch (error) {
                console.error("手动切换出错:", error);
                return { status: 'error', message: error.toString() };
            }
        },
        checkSwitchElement: () => ({
            exists: modeSwitch !== null,
            type: modeSwitch ? modeSwitch.type : null,
            checked: modeSwitch ? modeSwitch.checked : null
        })
    };
}); 