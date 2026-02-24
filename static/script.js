// Регистрируем плагины
Chart.register(ChartDataLabels);
document.getElementById('download-db-btn').addEventListener('click', downloadDatabase);
document.getElementById('upload-db-btn').addEventListener('click', () => {
    document.getElementById('db-upload').click();
});
document.getElementById('db-upload').addEventListener('change', uploadDatabase);

function downloadDatabase() {
    fetch('/api/download_db')
        .then(response => {
            if (!response.ok) {
                throw new Error('Ошибка при скачивании базы данных');
            }
            return response.blob();
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'database_backup.sql';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        })
        .catch(error => {
            console.error('Ошибка:', error);
            alert('Не удалось скачать базу данных: ' + error.message);
        });
}

function uploadDatabase(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    if (!confirm('ВНИМАНИЕ! Это полностью перезапишет всю базу данных. Продолжить?')) {
        event.target.value = '';
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    // Показать индикатор загрузки
    const btn = document.getElementById('upload-db-btn');
    btn.disabled = true;
    btn.textContent = 'Загрузка...';
    
    fetch('/api/upload_db', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.message || 'Ошибка сервера'); });
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            alert('База данных успешно перезаписана!');
            // Обновляем данные на странице
            const activeBtn = document.querySelector('.time-range-btn.active');
            const hours = activeBtn ? parseInt(activeBtn.dataset.hours) : 24;
            updateData(hours);
        } else {
            throw new Error(data.message || 'Неизвестная ошибка');
        }
    })
    .catch(error => {
        console.error('Ошибка:', error);
        alert('Ошибка при загрузке базы данных: ' + error.message);
    })
    .finally(() => {
        event.target.value = '';
        btn.disabled = false;
        btn.textContent = 'Загрузить базу данных';
    });
}

let eventChart, mineChart, historyChart;

// Определяем мобильное устройство
const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
if (isMobile) {
    document.documentElement.classList.add('mobile');
}

function generateColorSpectrum(numColors, saturation = 100, lightness = 50) {
    const colors = [];
    for (let i = 0; i < numColors; i++) {
        const hue = (i * 360 / numColors) % 360;
        colors.push(`hsl(${hue}, ${saturation}%, ${lightness}%)`);
    }
    return colors;
}

function updateData(hours = 24) {
    fetch(`/api/stats?hours=${hours}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'error') {
                console.error('Server error:', data.message);
                return;
            }
            
            document.getElementById('total-count').textContent = data.data.total_users;
            document.getElementById('active-count').textContent = data.data.active_users;
            
            const percentage = data.data.total_users > 0 
                ? Math.round((data.data.active_users / data.data.total_users) * 100) 
                : 0;
            document.getElementById('percentage').textContent = `${percentage}%`;
            
            const now = new Date();
            document.getElementById('last-update').textContent = 
                `Последнее обновление: ${now.toISOString().substr(0, 19).replace('T', ' ')} UTC`;
            
            updateEventChart(data.data.event, data.data.total_active_subs);
            updateMineChart(data.data.mine, data.data.total_active_subs);
            updateHistoryChart(data.data.history, hours);
        })
        .catch(error => {
            console.error('Ошибка при получении данных:', error);
            // Можно добавить отображение ошибки пользователю
            document.getElementById('last-update').textContent = 
                'Ошибка при загрузке данных. Попробуйте обновить страницу.';
        });
}

function updateHistoryChart(history, hours) {
    const ctx = document.getElementById('history-chart').getContext('2d');
    
    // Format labels based on time range
    let labels = [];
    if (hours === 1) {  // 1 hour
        labels = history.map(item => item.time);
    } else if (hours === 24) {  // 1 day
        labels = history.map(item => item.time);
    } else if (hours === 168) {  // 7 days
        labels = history.map(item => item.date);
    } else {  // 30 days
        labels = history.map(item => item.date);
    }
    
    const totalData = history.map(item => item.total_users);
    const activeData = history.map(item => item.active_users);
    const uniqueData = history.map(item => item.unique_users);

    // Find the maximum value in both datasets
    const maxTotal = Math.max(...totalData);
    const maxActive = Math.max(...activeData);
    const maxValue = Math.max(maxTotal, maxActive);
    
    // Calculate max scale value (20% higher than max data point)
    const maxScale = Math.ceil(maxValue * 1.2);
    
    const fontSize = isMobile ? 14 : 12;
    const borderWidth = isMobile ? 4 : 3;
    
    if (historyChart) {
        historyChart.data.labels = labels;
        historyChart.data.datasets[0].data = totalData;
        historyChart.data.datasets[1].data = activeData;
        historyChart.data.datasets[2].data = uniqueData;
        historyChart.options.scales.y.max = maxScale;
        historyChart.options.scales.x.ticks.font.size = fontSize;
        historyChart.options.scales.y.ticks.font.size = fontSize;
        historyChart.options.plugins.legend.labels.font.size = isMobile ? 16 : 14;
        historyChart.update();
    } else {
        historyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Всего пользователей',
                        data: totalData,
                        borderColor: '#8a2be2',
                        backgroundColor: 'rgba(138, 43, 226, 0.1)',
                        tension: 0.1,
                        fill: true,
                        borderWidth: borderWidth,
                        pointRadius: 0
                    },
                    {
                        label: 'Активных пользователей',
                        data: activeData,
                        borderColor: '#ba55d3',
                        backgroundColor: 'rgba(186, 85, 211, 0.1)',
                        tension: 0.1,
                        fill: true,
                        borderWidth: borderWidth,
                        pointRadius: 0
                    },
                    {
                        label: 'Уникальных пользователей',
                        data: uniqueData,
                        borderColor: '#f297e1',
                        backgroundColor: 'rgba(186, 85, 211, 0.1)',
                        tension: 0.1,
                        fill: true,
                        borderWidth: borderWidth,
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#e0e0e0',
                            font: {
                                size: fontSize
                            },
                            maxRotation: 45,
                            autoSkip: true,
                            maxTicksLimit: 12
                        }
                    },
                    y: {
                        beginAtZero: true,
                        max: maxScale,  // Set the max scale value
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#e0e0e0',
                            font: {
                                size: fontSize
                            },
                            precision: 0,
                            stepSize: Math.ceil(maxScale / 5)  // Nice step size
                        }
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#e0e0e0',
                            font: {
                                size: isMobile ? 16 : 14
                            }
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        bodyFont: {
                            size: isMobile ? 14 : 12
                        },
                        titleFont: {
                            size: isMobile ? 16 : 14
                        }
                    },
                    datalabels: {
                        display: false
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                }
            }
        });
    }
}

function updateEventChart(event, totalActive) {
    const ctx = document.getElementById('event-chart').getContext('2d');
    const labels = Object.keys(event);
    const data = Object.values(event);
    
    // Получаем распределенные цвета
    const distributedColors = generateColorSpectrum(labels.length,85,45);
    
    let percentages = calculatePercentages(data, totalActive);
    const fontSize = isMobile ? 14 : 12;
    const legendFontSize = isMobile ? 18 : 16;
    const datalabelsSize = isMobile ? 16 : 14;
    
    if (eventChart) {
        eventChart.data.labels = labels;
        eventChart.data.datasets[0].data = data;
        eventChart.data.datasets[0].backgroundColor = distributedColors;
        eventChart.options.plugins.datalabels.formatter = (value, context) => {
            return `${percentages[context.dataIndex]}%`;
        };
        eventChart.options.plugins.legend.labels.font.size = legendFontSize;
        eventChart.options.plugins.datalabels.font.size = datalabelsSize;
        eventChart.update();
    } else {
        eventChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: distributedColors,
                    borderColor: '#333',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: '#e0e0e0',
                            font: {
                                size: legendFontSize
                            },
                            padding: 20
                        }
                    },
                    tooltip: {
                        bodyFont: {
                            size: fontSize
                        },
                        titleFont: {
                            size: fontSize + 2
                        },
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.raw || 0;
                                const percent = percentages[context.dataIndex];
                                return `${label}: ${value} (${percent}%)`;
                            }
                        }
                    },
                    datalabels: {
                        color: '#ffffff',
                        font: {
                            size: datalabelsSize,
                            weight: 'bold'
                        },
                        formatter: (value, context) => {
                            return `${percentages[context.dataIndex]}%`;
                        },
                        anchor: 'center',
                        align: 'center',
                        offset: 0
                    }
                },
                cutout: '65%'
            },
            plugins: [ChartDataLabels]
        });
    }
}

function updateMineChart(mine, totalActive) {
    const ctx = document.getElementById('mine-chart').getContext('2d');
    const labels = Object.keys(mine);
    const data = Object.values(mine);
    
    // Получаем распределенные цвета
    const distributedColors = generateColorSpectrum(labels.length,85,45);
    
    let percentages = calculatePercentages(data, totalActive);
    const fontSize = isMobile ? 14 : 12;
    const legendFontSize = isMobile ? 18 : 16;
    const datalabelsSize = isMobile ? 16 : 14;
    
    if (mineChart) {
        mineChart.data.labels = labels;
        mineChart.data.datasets[0].data = data;
        mineChart.data.datasets[0].backgroundColor = distributedColors;
        mineChart.options.plugins.datalabels.formatter = (value, context) => {
            return `${percentages[context.dataIndex]}%`;
        };
        mineChart.options.plugins.legend.labels.font.size = legendFontSize;
        mineChart.options.plugins.datalabels.font.size = datalabelsSize;
        mineChart.update();
    } else {
        mineChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: distributedColors,
                    borderColor: '#333',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: '#e0e0e0',
                            font: {
                                size: legendFontSize
                            },
                            padding: 20
                        }
                    },
                    tooltip: {
                        bodyFont: {
                            size: fontSize
                        },
                        titleFont: {
                            size: fontSize + 2
                        },
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.raw || 0;
                                const percent = percentages[context.dataIndex];
                                return `${label}: ${value} (${percent}%)`;
                            }
                        }
                    },
                    datalabels: {
                        color: '#ffffff',
                        font: {
                            size: datalabelsSize,
                            weight: 'bold'
                        },
                        formatter: (value, context) => {
                            return `${percentages[context.dataIndex]}%`;
                        },
                        anchor: 'center',
                        align: 'center',
                        offset: 0
                    }
                },
                cutout: '65%'
            },
            plugins: [ChartDataLabels]
        });
    }
}

function calculatePercentages(values, total) {
    if (total === 0) return values.map(() => 0);
    
    // Просто вычисляем проценты без округления и выравнивания
    return values.map(value => Math.round((value / total) * 100 * 10) / 10); // Округляем до 1 знака после запятой
}

// Обработчики для кнопок выбора временного диапазона
document.querySelectorAll('.time-range-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.time-range-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        const hours = parseInt(this.dataset.hours);
        updateData(hours);
    });
});

window.addEventListener('load', () => updateData(24));
window.addEventListener('resize', function() {
    if (historyChart) {
        historyChart.resize();
    }
    if (mineChart) {
        mineChart.resize();
    }
    if (eventChart) {
        eventChart.resize();
    }
});
setInterval(() => {
    const activeBtn = document.querySelector('.time-range-btn.active');
    const hours = activeBtn ? parseInt(activeBtn.dataset.hours) : 24;
    updateData(hours);
}, 60000);