/* ================================================================
   MCP Travel Agent — Leaflet + 高德瓦片 CDN
   地图底图: 高德最新瓦片（GCJ-02 坐标系）
   数据来源: 高德 REST API（后端代理）
   ================================================================ */

// ========== 全局配置 ==========
// markdown-it 初始化 (支持代码高亮和表格)
// 注意: markdown-it 原生支持 Markdown 表格 (pipes syntax)
var md = window.markdownit({
    html: true,
    linkify: true,
    typographer: true,
    breaks: true,
    highlight: function (str, lang) {
        if (lang && hljs && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(str, { language: lang, ignoreIllegals: true }).value;
            } catch (__) {}
        }
        return '';
    }
});

// 如果 table 插件可用，则使用表格插件
if (window.markdownitTable) {
    md.use(window.markdownitTable);
}

// ========== 全局 ==========
var map = null;
var markerGroups = { attraction: [], restaurant: [], hotel: [] }; // [{marker, data}]
var markerLayerGroups = { attraction: null, restaurant: null, hotel: null };
var routePolylines = [];
var routeLabels = [];
var routeSegments = [];
var routeLayerGroup = null;
var waypoints = [];
var itineraryDays = [];   // 每天景点列表（TSP排序），来自后端 itinerary_days
var currentWpDay = 0;     // 当前途经点显示的天序号（0-indexed）
var journalEntries = [];
var targetCity = '';
var dragSrcIdx = null;

var COLORS = {
    attraction: '#4F6AF6', restaurant: '#F97316', hotel: '#10B981',
    route: ['#6366F1', '#EC4899', '#14B8A6', '#F59E0B', '#EF4444', '#8B5CF6'],
};

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', function () {
    // 高德瓦片 CDN（GCJ-02，无需 JS API Key）
    var gaodeTiles = L.tileLayer(
        'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
        {
            subdomains: '1234',
            maxZoom: 18,
            attribution: ''
        }
    );

    map = L.map('mapContainer', {
        center: [30.53, 117.05],  // Leaflet: [lat, lng]
        zoom: 12,
        layers: [gaodeTiles],
        zoomControl: false,
    });

    // 缩放控件右上角
    L.control.zoom({ position: 'topright' }).addTo(map);
    // 比例尺
    L.control.scale({ metric: true, imperial: false, position: 'bottomleft' }).addTo(map);

    // 图层组
    markerLayerGroups.attraction = L.layerGroup().addTo(map);
    markerLayerGroups.restaurant = L.layerGroup().addTo(map);
    markerLayerGroups.hotel = L.layerGroup().addTo(map);
    routeLayerGroup = L.layerGroup().addTo(map);

    // 右键添加途经点
    map.on('contextmenu', function (e) {
        var name = prompt('输入地点名称:');
        if (name) {
            addWaypoint({
                name: name, lng: e.latlng.lng, lat: e.latlng.lat,
                type: 'attraction', order: waypoints.length + 1, address: ''
            });
        }
    });

    // 聊天自动初始化：进入页面就触发小满打招呼
    initChat();

    // Enter 键从顶栏聊天框发送
    document.getElementById('chatInput').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') sendChatMessage();
    });
});

// ========== 自定义图标 ==========
function makeIcon(type, index) {
    var color = COLORS[type];
    var html;
    if (type === 'attraction') {
        html = '<div class="map-marker" style="background:' + color + ';">' + (index + 1) + '</div>';
    } else if (type === 'restaurant') {
        html = '<div class="map-marker map-marker-sm" style="background:' + color + ';"><i class="fas fa-utensils"></i></div>';
    } else {
        html = '<div class="map-marker map-marker-sm" style="background:' + color + ';"><i class="fas fa-bed"></i></div>';
    }
    return L.divIcon({
        html: html,
        className: 'custom-div-icon',
        iconSize: [30, 30],
        iconAnchor: [15, 15],
        popupAnchor: [0, -18],
    });
}

// ========== Tab ==========
function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.toggle('active', b.dataset.tab === tab); });
    document.querySelectorAll('.tab-content').forEach(function (c) {
        c.classList.toggle('active', c.id === 'tab' + tab.charAt(0).toUpperCase() + tab.slice(1));
    });
    if (tab === 'map') setTimeout(function () { map && map.invalidateSize(); }, 100);
}
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('collapsed');
    setTimeout(function () { map && map.invalidateSize(); }, 350);
}

// ========== Agent 规划 ==========
function startPlan() {
    var baseQuery = document.getElementById('chatInput').value.trim();
    var query = buildQueryWithChips(baseQuery);
    if (!query) { alert('请在对话框输入旅行需求或选择上方选项'); return; }
    var btn = document.getElementById('chatSendBtn');
    btn.disabled = true;
    showLoading('Agent 正在调用 12 项高德 MCP 服务...');
    fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query })
    }).then(function (resp) {
        if (!resp.ok) return resp.json().then(function (e) {
            var msg = e.error || 'error';
            // 400 = 用户输入问题，直接显示消息；500 = 系统错误
            var err = new Error(msg);
            err.isUserError = (resp.status === 400);
            throw err;
        });
        return resp.json();
    }).then(function (data) {
        applyPlanResult(data);
    }).catch(function (e) {
        if (e.isUserError) {
            alert('⚠️ ' + e.message);
        } else {
            alert('规划出错: ' + e.message);
        }
    }).finally(function () {
        btn.disabled = false;
        hideLoading();
    });
}

function applyPlanResult(data) {
    console.log('[PLAN DEBUG] applyPlanResult called with data:', data);
    targetCity = (data.demands && data.demands.destination_city) || '';

    // 行程文本 — 使用 markdown-it 渲染为 HTML
    var planHtml = md.render(data.plan_text || '');
    var planEl = document.getElementById('planContent');
    planEl.innerHTML = planHtml;

    // 多城市提示横幅
    var noticeEl = document.getElementById('planNotice');
    if (data.notice) {
        noticeEl.innerHTML =
            '<span class="notice-icon">ℹ️</span>' +
            '<span class="notice-text">' + esc(data.notice) + '</span>' +
            '<span class="notice-close" onclick="this.parentNode.style.display=\'none\'">✕</span>';
        noticeEl.style.display = 'flex';
    } else {
        noticeEl.style.display = 'none';
    }
    
    // 为Markdown渲染后的内容添加样式类
    planEl.classList.add('markdown-body');

    // 天气
    if (data.weather && data.weather.forecasts && data.weather.forecasts.length) {
        document.getElementById('panelWeather').style.display = '';
        renderWeather(data.weather);
    }

    // 清空
    clearAllMarkers();
    clearRoutes();

    // 标记
    var attrs = data.attraction_markers || [];
    var rests = data.restaurant_markers || [];
    var hotels = data.hotel_markers || [];
    placeMarkers(attrs, 'attraction');
    placeMarkers(rests, 'restaurant');
    placeMarkers(hotels, 'hotel');
    updateCounts(attrs.length, rests.length, hotels.length);

    // 途经点：用行程规划的分天数据，默认加载第1天
    itineraryDays = data.itinerary_days || [];
    currentWpDay = 0;
    waypoints = (itineraryDays[0] || []).map(function(w, i) {
        return { name: w.name, lat: w.lat, lng: w.lng, address: w.address || '', order: i + 1, type: 'attraction' };
    });
    renderWaypoints();

    // 路线
    if (data.routes && data.routes.length) {
        routeSegments = data.routes;
        drawRoutes(data.routes);
    }

    // 自适应
    fitView();

    // 游记
    journalEntries = data.journal || [];
    renderJournal();
    
    // 【新功能】解析规划文本并重新编号景点
    reorderAttractionsBasedOnPlan(data.plan_text || '', data.attraction_markers || []);

    // 填充"地点"侧边栏 Tab
    renderPoiList(data);
}

// =========== 【新功能】根据规划文本重新编号景点 ===========
function reorderAttractionsBasedOnPlan(planText, attrMarkers) {
    // 从规划文本中提取"地图编号: N"的模式
    // 例如: "📍 天柱山 (✓ 地图编号: 1)"
    var numberMap = {};
    var regex = /📍\s*([^()]+)\s*\(.*?地图编号:\s*(\d+)/g;
    var match;
    
    while ((match = regex.exec(planText)) !== null) {
        var poiName = match[1].trim();
        var orderNum = parseInt(match[2]);
        numberMap[poiName] = orderNum;
    }
    
    // 如果提取到了编号信息，更新地图标记
    if (Object.keys(numberMap).length > 0) {
        attrMarkers.forEach(function(marker, idx) {
            // 根据名称查找编号
            for (var name in numberMap) {
                if (marker.name.includes(name) || name.includes(marker.name)) {
                    marker.order = numberMap[name];
                    break;
                }
            }
        });
        
        // 重新排序
        attrMarkers.sort(function(a, b) { return (a.order || 999) - (b.order || 999); });
        
        // 清除旧标记并重新绘制
        clearAllMarkers();
        placeMarkers(attrMarkers, 'attraction');
        updateCounts(attrMarkers.length, markerGroups.restaurant.length, markerGroups.hotel.length);
    }
    
    // 解析每日行程清单
    renderItineraryFromPlan(planText, attrMarkers);
}

// =========== 【新功能】从规划文本解析并显示每日行程清单 ===========
function renderItineraryFromPlan(planText, attrMarkers) {
    // 提取每日章节：第1天、第2天等
    var dayRegex = /#+\s*第(\d+)天\s*[-–—]\s*(.+?)(?=#+\s*第|\Z)/gs;
    var days = [];
    var dayMatch;
    
    while ((dayMatch = dayRegex.exec(planText)) !== null) {
        var dayNum = parseInt(dayMatch[1]);
        var dayContent = dayMatch[2];
        
        // 从该天的内容中提取所有景点
        var attractions = [];
        var poiRegex = /📍\s*([^()]+)\s*\(.*?地图编号:\s*(\d+)/g;
        var poiMatch;
        
        while ((poiMatch = poiRegex.exec(dayContent)) !== null) {
            attractions.push({
                name: poiMatch[1].trim(),
                order: parseInt(poiMatch[2])
            });
        }
        
        days.push({
            day: dayNum,
            attractions: attractions,
            content: dayContent
        });
    }
    
    // 渲染到面板
    if (days.length > 0) {
        document.getElementById('panelItinerary').style.display = '';
        var html = '';
        
        days.forEach(function(day) {
            html += '<div class="itinerary-day">';
            html += '<div class="itinerary-day-title">Day ' + day.day + '</div>';
            
            if (day.attractions.length > 0) {
                html += '<div class="itinerary-pois">';
                day.attractions.forEach(function(poi) {
                    var isFullDay = allPoiData.attraction.some(function(a) {
                        return a.is_full_day && (a.name === poi.name || a.name.includes(poi.name) || poi.name.includes(a.name));
                    });
                    // Look up lat/lng from attrMarkers so clicking opens the map popup
                    var markerData = null;
                    for (var j = 0; j < attrMarkers.length; j++) {
                        var m = attrMarkers[j];
                        if (m.name === poi.name || m.name.includes(poi.name) || poi.name.includes(m.name)) {
                            markerData = m;
                            break;
                        }
                    }
                    var clickAttr = markerData
                        ? ' onclick="flyToPoi(' + markerData.lat + ',' + markerData.lng + ',' + JSON.stringify(markerData.name) + ',\'attraction\')"'
                        : '';
                    html += '<div class="itinerary-poi-item"' + clickAttr + '>';
                    html += '<span class="poi-order">📍 ' + poi.order + '</span>';
                    html += '<span class="poi-name">' + esc(poi.name) + '</span>';
                    if (isFullDay) html += '<span class="poi-fullday-badge">🎪 整天</span>';
                    html += '</div>';
                });
                html += '</div>';
            }
            
            html += '</div>';
        });
        
        document.getElementById('itineraryContent').innerHTML = html;
    }
}

// =========== 原有代码 ===========
function showLoading(t) {
    document.getElementById('loadingText').innerText = t;
    document.getElementById('loadingSteps').innerHTML = '';
    document.getElementById('loadingOverlay').style.display = '';
}
function hideLoading() { document.getElementById('loadingOverlay').style.display = 'none'; }

// ========== 天气 ==========
function renderWeather(w) {
    var el = document.getElementById('weatherContent');
    var forecasts = w.forecasts || [];
    var days = forecasts.length;

    // 标题注释：几天预报 / 仅今日
    var note = '';
    if (days === 0) {
        note = '<div class="weather-note">暂无天气数据</div>';
    } else if (days === 1 && !forecasts[0].date) {
        note = '<div class="weather-note"><i class="fas fa-info-circle"></i> 仅显示今日实况，预报数据暂不可用</div>';
    } else {
        note = '<div class="weather-note"><i class="fas fa-cloud-sun"></i> 未来 ' + days + ' 天预报</div>';
    }

    var cards = forecasts.map(function (f) {
        var dateLabel = f.date ? f.date.slice(5) : '今日';
        var tempRange = (f.nighttemp || f.nighttemp_float || '') + '~' + (f.daytemp || f.daytemp_float || '') + '\u2103';
        return '<div class="weather-day">' +
            '<div class="wd-date">' + dateLabel + '</div>' +
            '<div>' + (f.dayweather || f.weather || '') + '</div>' +
            '<div class="wd-temp">' + tempRange + '</div>' +
            '</div>';
    }).join('');

    el.innerHTML = note + '<div class="weather-card">' + cards + '</div>';
}

// ========== 标记 ==========
function clearAllMarkers() {
    ['attraction', 'restaurant', 'hotel'].forEach(function (t) {
        if (markerLayerGroups[t]) markerLayerGroups[t].clearLayers();
        markerGroups[t] = [];
    });
}

function placeMarkers(items, type) {
    items.forEach(function (w, i) {
        if (!w.lng || !w.lat) return;
        var icon = makeIcon(type, i);
        var marker = L.marker([w.lat, w.lng], {  // Leaflet: [lat, lng]
            icon: icon,
            draggable: (type === 'attraction'),
        });

        // 点击弹窗
        marker.on('click', function () { showPopup(marker, w, type); });

        // 拖拽更新
        if (type === 'attraction') {
            marker.on('dragend', function () {
                var pos = marker.getLatLng();
                w.lng = pos.lng; w.lat = pos.lat;
                if (i < waypoints.length) { waypoints[i].lng = w.lng; waypoints[i].lat = w.lat; }
                saveWaypoints();
            });
        }

        markerLayerGroups[type].addLayer(marker);
        markerGroups[type].push({ marker: marker, data: w });
    });
}

function showPopup(marker, w, type) {
    var labels = { attraction: '景点', restaurant: '餐厅', hotel: '酒店' };
    var color = COLORS[type];
    var h = '<div class="popup-content">';
    // 顶部图片（有图时展示，无图时不占位）
    if (w.photo_url) {
        h += '<div class="popup-photo" style="background-image:url(' + esc(w.photo_url) + ')"></div>';
    }
    h += '<div class="popup-type" style="color:' + color + ';">' + labels[type] + '</div>';
    h += '<div class="popup-name">' + esc(w.name) + '</div>';
    if (w.address) h += '<div class="popup-row"><i class="fas fa-map-pin"></i> ' + esc(w.address) + '</div>';
    if (w.rating && w.rating !== 'None') h += '<div class="popup-row"><i class="fas fa-star" style="color:#F59E0B;"></i> ' + w.rating + '</div>';
    if (w.price && w.price !== 'None') h += '<div class="popup-row"><i class="fas fa-yen-sign" style="color:#10B981;"></i> 人均 ¥' + w.price + '</div>';
    if (w.tel) h += '<div class="popup-row"><i class="fas fa-phone"></i> ' + esc(w.tel) + '</div>';
    if (w.opening_hours) h += '<div class="popup-row"><i class="fas fa-clock"></i> ' + esc(w.opening_hours) + '</div>';
    if (w.distance) h += '<div class="popup-row"><i class="fas fa-ruler"></i> ' + w.distance + 'm</div>';
    h += '</div>';

    L.popup({ maxWidth: 280, minWidth: 200, className: 'custom-popup' })
        .setLatLng(marker.getLatLng())
        .setContent(h)
        .openOn(map);
}

function toggleLayer(type) {
    var id = 'toggle' + type.charAt(0).toUpperCase() + type.slice(1) + 's';
    var checked = document.getElementById(id).checked;
    if (checked) {
        map.addLayer(markerLayerGroups[type]);
    } else {
        map.removeLayer(markerLayerGroups[type]);
    }
}
function toggleRouteLayer() {
    var checked = document.getElementById('toggleRoutes').checked;
    if (checked) {
        map.addLayer(routeLayerGroup);
    } else {
        map.removeLayer(routeLayerGroup);
    }
}
function updateCounts(a, r, h) {
    document.getElementById('countAttractions').textContent = a;
    document.getElementById('countRestaurants').textContent = r;
    document.getElementById('countHotels').textContent = h;
}
function fitView() {
    var bounds = L.latLngBounds([]);
    ['attraction', 'restaurant', 'hotel'].forEach(function (t) {
        markerGroups[t].forEach(function (item) {
            bounds.extend(item.marker.getLatLng());
        });
    });
    if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [60, 60] });
    }
}

// ========== 路线 ==========
function clearRoutes() {
    if (routeLayerGroup) routeLayerGroup.clearLayers();
    routePolylines = [];
    routeLabels = [];
    routeSegments = [];
    document.getElementById('routeInfoPanel').style.display = 'none';
}

function drawRoutes(routes) {
    clearRoutes();
    routeSegments = routes;
    var colors = COLORS.route;
    var hasReal = false;

    console.log('[ROUTE DEBUG] drawRoutes called with', routes.length, 'segments');

    routes.forEach(function (r, i) {
        var pl = r.polyline || [];
        console.log('[ROUTE DEBUG] Segment', i, '(' + (r.from || '?') + ' → ' + (r.to || '?') + '):', 
                    'polyline points =', pl.length, 'distance =', r.distance, 'duration =', r.duration);
        
        if (pl.length < 2) {
            console.warn('[ROUTE WARN] Segment', i, 'skipped: polyline has < 2 points');
            return;
        }
        
        hasReal = true;
        var color = colors[i % colors.length];
        // pl 格式 [[lng, lat], ...], Leaflet 需要 [[lat, lng], ...]
        var latlngs = pl.map(function (p) { return [p[1], p[0]]; });
        console.log('[ROUTE DEBUG] Drawing polyline with', latlngs.length, 'coordinates');
        
        var line = L.polyline(latlngs, {
            color: color, weight: 5, opacity: 0.85,
            lineJoin: 'round',
        });
        routeLayerGroup.addLayer(line);
        routePolylines.push(line);

        // 中间距离标注
        var mid = pl[Math.floor(pl.length / 2)];
        if (mid) {
            var km = r.walking_km || (r.distance ? (r.distance / 1000).toFixed(1) : '?');
            var min = r.walking_min || (r.duration ? (r.duration / 60).toFixed(0) : '?');
            var labelIcon = L.divIcon({
                html: '<div class="route-label" style="border-color:' + color + ';color:' + color + ';">' + km + 'km / ' + min + 'min</div>',
                className: 'route-label-icon',
                iconSize: [0, 0],
            });
            var labelMarker = L.marker([mid[1], mid[0]], { icon: labelIcon, interactive: false });
            routeLayerGroup.addLayer(labelMarker);
            routeLabels.push(labelMarker);
        }
    });

    console.log('[ROUTE DEBUG] drawRoutes complete: hasReal =', hasReal, 'polylines drawn =', routePolylines.length);
    if (routes.length) showRouteInfo(routes);
    if (!hasReal && waypoints.length >= 2) drawDashed();
}

function drawDashed() {
    var colors = COLORS.route;
    for (var i = 0; i < waypoints.length - 1; i++) {
        var a = waypoints[i], b = waypoints[i + 1], c = colors[i % colors.length];
        var line = L.polyline(
            [[a.lat, a.lng], [b.lat, b.lng]],
            { color: c, weight: 3, opacity: 0.6, dashArray: '8 6' }
        );
        routeLayerGroup.addLayer(line);
        routePolylines.push(line);
    }
}

function showRouteInfo(routes) {
    var el = document.getElementById('routeInfoPanel');
    var colors = COLORS.route;
    var html = '<div class="route-info-title">路线详情</div>';
    routes.forEach(function (r, i) {
        var c = colors[i % colors.length];
        var km = r.walking_km || (r.distance ? (r.distance / 1000).toFixed(1) : '?');
        var min = r.walking_min || (r.duration ? (r.duration / 60).toFixed(0) : '?');
        var det = km + 'km / ' + min + 'min';
        if (r.driving_km) det += ' | 驾车' + r.driving_km + 'km ' + r.driving_min + 'min';
        if (r.taxi_cost) det += ' | 打车约' + r.taxi_cost + '元';
        html += '<div class="route-info-item" style="border-left:3px solid ' + c + ';">' +
            '<div class="ri-header">' + esc(r.from || '') + ' → ' + esc(r.to || '') + '</div>' +
            '<div class="ri-detail">' + det + '</div>' +
            (r.recommended ? '<div class="ri-rec">建议: ' + r.recommended + '</div>' : '') + '</div>';
    });
    el.innerHTML = html; el.style.display = '';
}

// ========== 规划路线 (按钮) ==========
function planRoutes() {
    if (waypoints.length < 2) { alert('至少需要 2 个途经点'); return; }
    var mode = document.getElementById('routeMode').value;
    var btn = document.getElementById('routePlanBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 规划中...';
    var points = waypoints.map(function (w) { return { name: w.name, lng: w.lng, lat: w.lat }; });
    fetch('/api/route_plan_multi', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ points: points, mode: mode, city: targetCity })
    }).then(function (r) { return r.json(); }).then(function (data) {
        if (!data.segments) return;
        clearRoutes();
        routeSegments = data.segments;
        var colors = COLORS.route;
        data.segments.forEach(function (seg, i) {
            var pl = seg.polyline || [];
            var c = colors[i % colors.length];
            if (pl.length >= 2) {
                var latlngs = pl.map(function (p) { return [p[1], p[0]]; });
                var line = L.polyline(latlngs, { color: c, weight: 5, opacity: 0.85, lineJoin: 'round' });
                routeLayerGroup.addLayer(line);
                routePolylines.push(line);
                var mid = pl[Math.floor(pl.length / 2)];
                if (mid) {
                    var labelIcon = L.divIcon({
                        html: '<div class="route-label" style="border-color:' + c + ';color:' + c + ';">' +
                            (seg.distance / 1000).toFixed(1) + 'km / ' + (seg.duration / 60).toFixed(0) + 'min</div>',
                        className: 'route-label-icon',
                        iconSize: [0, 0],
                    });
                    var labelMarker = L.marker([mid[1], mid[0]], { icon: labelIcon, interactive: false });
                    routeLayerGroup.addLayer(labelMarker);
                    routeLabels.push(labelMarker);
                }
            }
        });
        showRouteInfo(data.segments.map(function (s) {
            return {
                from: s.from, to: s.to, walking_km: (s.distance / 1000).toFixed(1),
                walking_min: (s.duration / 60).toFixed(0), taxi_cost: s.taxi_cost, recommended: mode
            };
        }));
        if (!routePolylines.length) drawDashed();
    }).catch(function (e) { alert('路线规划出错: ' + e.message); })
        .finally(function () { btn.disabled = false; btn.innerHTML = '<i class="fas fa-directions"></i> 规划路线'; });
}

// ========== 途经点 ==========
function switchWpDay(dayIdx) {
    if (!itineraryDays[dayIdx]) return;
    currentWpDay = dayIdx;
    waypoints = itineraryDays[dayIdx].map(function(w, i) {
        return { name: w.name, lat: w.lat, lng: w.lng, address: w.address || '', order: i + 1, type: 'attraction' };
    });
    clearRoutes();
    renderWaypoints();
    saveWaypoints();
}

function renderWaypoints() {
    var el = document.getElementById('waypointList');
    var html = '';

    // 天数切换按钮（有多天且来自行程规划时显示）
    if (itineraryDays.length > 1) {
        html += '<div class="wp-day-tabs">';
        for (var d = 0; d < itineraryDays.length; d++) {
            var active = d === currentWpDay ? ' active' : '';
            html += '<button class="wp-day-btn' + active + '" onclick="switchWpDay(' + d + ')">第' + (d + 1) + '天</button>';
        }
        html += '</div>';
    }

    if (!waypoints.length) {
        el.innerHTML = html + '<p class="empty-hint">暂无途经点</p>';
        return;
    }
    html += waypoints.map(function (w, i) {
        return '<div class="wp-item" draggable="true" ondragstart="wpDragStart(event,' + i + ')" ondragover="wpDragOver(event)" ondrop="wpDrop(event,' + i + ')">' +
            '<span class="wp-order">' + (i + 1) + '</span>' +
            '<span class="wp-name" title="' + esc(w.address || '') + '">' + esc(w.name) + '</span>' +
            '<span class="wp-actions">' +
            '<button title="定位" onclick="locateWp(' + i + ')"><i class="fas fa-crosshairs"></i></button>' +
            '<button title="删除" onclick="removeWp(' + i + ')"><i class="fas fa-trash"></i></button>' +
            '</span></div>';
    }).join('');
    el.innerHTML = html;
}
function addWaypoint(wp) {
    waypoints.push(wp);
    renderWaypoints();
    var m = L.marker([wp.lat, wp.lng], { icon: makeIcon('attraction', waypoints.length - 1), draggable: true });
    m.on('click', function () { showPopup(m, wp, 'attraction'); });
    markerLayerGroups.attraction.addLayer(m);
    markerGroups.attraction.push({ marker: m, data: wp });
    saveWaypoints();
}
function removeWp(i) { waypoints.splice(i, 1); waypoints.forEach(function (w, j) { w.order = j + 1; }); renderWaypoints(); saveWaypoints(); }
function locateWp(i) { map.setView([waypoints[i].lat, waypoints[i].lng], 15); }
function wpDragStart(e, i) { dragSrcIdx = i; e.dataTransfer.effectAllowed = 'move'; }
function wpDragOver(e) { e.preventDefault(); }
function wpDrop(e, i) {
    e.preventDefault(); if (dragSrcIdx === null || dragSrcIdx === i) return;
    var item = waypoints.splice(dragSrcIdx, 1)[0]; waypoints.splice(i, 0, item);
    waypoints.forEach(function (w, j) { w.order = j + 1; }); dragSrcIdx = null;
    renderWaypoints(); saveWaypoints();
}
function saveWaypoints() { fetch('/api/waypoints', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(waypoints) }); }

// ========== 添加途经点对话框 ==========
var searchTimer = null;
function addWaypointDialog() {
    document.getElementById('addWpDialog').style.display = '';
    var input = document.getElementById('wpSearchInput'); input.value = '';
    document.getElementById('wpSearchResults').innerHTML = ''; input.focus();
    input.oninput = function () { clearTimeout(searchTimer); searchTimer = setTimeout(doWpSearch, 500); };
}
function doWpSearch() {
    var kw = document.getElementById('wpSearchInput').value.trim();
    if (!kw) return;
    fetch('/api/search_place?keyword=' + encodeURIComponent(kw) + '&city=' + encodeURIComponent(targetCity))
        .then(function (r) { return r.json(); }).then(function (pois) {
            document.getElementById('wpSearchResults').innerHTML = pois.map(function (p) {
                return '<div class="sr-item" onclick="pickWp(\'' + esc(p.name) + '\',' + p.longitude + ',' + p.latitude + ',\'' + esc(p.address || '') + '\')">' +
                    '<strong>' + esc(p.name) + '</strong><div class="sr-addr">' + esc(p.address || '') + '</div></div>';
            }).join('');
        });
}
function pickWp(name, lng, lat, addr) {
    addWaypoint({ name: name, lng: lng, lat: lat, type: 'attraction', order: waypoints.length + 1, address: addr });
    closeWpDialog(); map.setView([lat, lng], 14);
}
function closeWpDialog() { document.getElementById('addWpDialog').style.display = 'none'; }

// ========== 游记 ==========
function renderJournal() {
    var el = document.getElementById('journalTimeline');
    if (!journalEntries.length) { el.innerHTML = '<p class="empty-hint">AI 规划后将自动生成游记框架，你也可以手动添加</p>'; return; }
    var groups = {};
    journalEntries.forEach(function (e) { var d = e.day || 1; if (!groups[d]) groups[d] = []; groups[d].push(e); });
    var html = '';
    Object.keys(groups).sort(function (a, b) { return a - b; }).forEach(function (day) {
        html += '<div class="journal-day-label">Day ' + day + '</div>';
        groups[day].sort(function (a, b) { return (a.time || '').localeCompare(b.time || ''); }).forEach(function (e) {
            html += '<div class="j-entry" onclick="editJEntry(' + e.id + ')">' +
                '<div class="j-entry-actions">' +
                '<button class="btn-sm" onclick="event.stopPropagation();locJEntry(' + e.id + ')" title="地图定位"><i class="fas fa-map-pin"></i></button>' +
                '<button class="btn-sm btn-danger" onclick="event.stopPropagation();delJEntry(' + e.id + ')" title="删除"><i class="fas fa-trash"></i></button></div>' +
                '<div class="j-entry-time">' + esc(e.time || '') + '</div>' +
                '<div class="j-entry-title">' + esc(e.title || '') + '</div>' +
                '<div class="j-entry-content">' + esc(e.content || '') + '</div></div>';
        });
    });
    el.innerHTML = html;
}
function editJEntry(id) {
    var e = journalEntries.find(function (x) { return x.id === id; }); if (!e) return;
    document.getElementById('editEntryId').value = id;
    document.getElementById('editEntryTime').value = e.time || '';
    document.getElementById('editEntryTitle').value = e.title || '';
    document.getElementById('editEntryContent').value = e.content || '';
    document.getElementById('editEntryDialog').style.display = '';
}
function closeEditEntry() { document.getElementById('editEntryDialog').style.display = 'none'; }
function saveEditEntry() {
    var id = parseInt(document.getElementById('editEntryId').value);
    var patch = { time: document.getElementById('editEntryTime').value, title: document.getElementById('editEntryTitle').value, content: document.getElementById('editEntryContent').value };
    fetch('/api/journal/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) })
        .then(function (r) { return r.json(); }).then(function (u) {
            var idx = journalEntries.findIndex(function (x) { return x.id === id; });
            if (idx >= 0) Object.assign(journalEntries[idx], u);
            renderJournal();
        });
    closeEditEntry();
}
function delJEntry(id) {
    if (!confirm('确定删除?')) return;
    fetch('/api/journal/' + id, { method: 'DELETE' });
    journalEntries = journalEntries.filter(function (x) { return x.id !== id; });
    renderJournal();
}
function addJournalEntry() {
    var maxDay = journalEntries.length ? Math.max.apply(null, journalEntries.map(function (e) { return e.day || 1; })) : 1;
    var entry = { day: maxDay, time: '12:00', title: '新条目', content: '在这里写下你的感受...', lng: 0, lat: 0 };
    fetch('/api/journal', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(entry) })
        .then(function (r) { return r.json(); }).then(function (e) { journalEntries.push(e); renderJournal(); });
}
function locJEntry(id) {
    var e = journalEntries.find(function (x) { return x.id === id; });
    if (e && e.lng && e.lat) { switchTab('map'); setTimeout(function () { map.setView([e.lat, e.lng], 16); }, 300); }
}
function exportJournal() {
    var text = journalEntries.map(function (e) { return '## Day ' + e.day + ' ' + e.time + ' - ' + e.title + '\n\n' + e.content + '\n'; }).join('\n---\n\n');
    var blob = new Blob(['\uFEFF' + text], { type: 'text/markdown;charset=utf-8' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = '旅行游记.md'; a.click();
}

// ========== Utils ==========
function esc(s) { if (!s) return ''; var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ========== 快选 Chip ==========
var chipState = { days: null, budget: null, prefs: [] };

function toggleChip(btn) {
    var type = btn.dataset.type;
    var val = btn.dataset.val;
    if (type === 'pref') {
        var idx = chipState.prefs.indexOf(val);
        if (idx >= 0) {
            chipState.prefs.splice(idx, 1);
            btn.classList.remove('active');
        } else {
            chipState.prefs.push(val);
            btn.classList.add('active');
        }
    } else {
        // 单选：取消同类其他chip
        document.querySelectorAll('.chip[data-type="' + type + '"]').forEach(function (s) {
            s.classList.remove('active');
        });
        if (chipState[type] === val) {
            chipState[type] = null;  // 再次点击取消
        } else {
            chipState[type] = val;
            btn.classList.add('active');
        }
    }

    // 同步 Chip 选择到后端 travel_info
    syncChipsToBackend();
}

function syncChipsToBackend() {
    fetch('/api/chat/update_chips', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            days: chipState.days ? parseInt(chipState.days) : null,
            budget: chipState.budget ? parseFloat(chipState.budget) : null,
            prefs: chipState.prefs.length > 0 ? chipState.prefs : null
        })
    }).catch(function (e) {
        console.warn('Chip sync failed:', e);
    });
}

function buildQueryWithChips(baseQuery) {
    var parts = [];
    if (baseQuery) parts.push(baseQuery);
    if (chipState.days) parts.push(chipState.days + '天');
    if (chipState.prefs.length) parts.push('偏好' + chipState.prefs.join('、'));
    if (chipState.budget) parts.push('预算' + chipState.budget + '元');
    return parts.join('，');
}

// ========== 旅行信息收集状态展示 ==========
function updateTravelInfoDisplay(info) {
    // 更新对话面板状态栏
    var status = document.getElementById('convStatus');
    if (!status) return;

    var parts = [];
    if (info.destination) parts.push('📍' + info.destination);
    if (info.days) parts.push(info.days + '天');
    if (info.budget) parts.push('¥' + info.budget);
    if (info.preferences && info.preferences.length) parts.push(info.preferences.join('/'));

    if (parts.length > 0) {
        status.textContent = parts.join(' · ');
        status.title = '已收集: ' + JSON.stringify(info);
    } else {
        status.textContent = '在线';
        status.title = '';
    }

    // 同步 chip UI 状态（后端可能通过对话更新了信息）
    if (info.days && !chipState.days) {
        var dayBtn = document.querySelector('.chip[data-type="days"][data-val="' + info.days + '"]');
        if (dayBtn) { dayBtn.classList.add('active'); chipState.days = String(info.days); }
    }
    if (info.budget && !chipState.budget) {
        var budgetBtn = document.querySelector('.chip[data-type="budget"][data-val="' + info.budget + '"]');
        if (budgetBtn) { budgetBtn.classList.add('active'); chipState.budget = String(info.budget); }
    }
    if (info.preferences && info.preferences.length && chipState.prefs.length === 0) {
        info.preferences.forEach(function (p) {
            var prefBtn = document.querySelector('.chip[data-type="pref"][data-val="' + p + '"]');
            if (prefBtn) { prefBtn.classList.add('active'); chipState.prefs.push(p); }
        });
    }
}

// ========== 侧边栏二级 Tab ==========
function switchStab(stab) {
    document.querySelectorAll('.stab').forEach(function (b) {
        b.classList.toggle('active', b.dataset.stab === stab);
    });
    document.getElementById('stabPlan').style.display = stab === 'plan' ? '' : 'none';
    document.getElementById('stabPois').style.display = stab === 'pois' ? '' : 'none';
}

// ========== POI 卡片列表 ==========
var allPoiData = { attraction: [], restaurant: [], hotel: [] };
var currentPoiFilter = 'all';

function renderPoiList(data) {
    allPoiData.attraction = data.attraction_markers || [];
    allPoiData.restaurant = data.restaurant_markers || [];
    allPoiData.hotel = data.hotel_markers || [];
    filterPoiList(currentPoiFilter);
}

function filterPoiList(filter) {
    currentPoiFilter = filter;
    document.querySelectorAll('.poi-filter').forEach(function (b) {
        b.classList.toggle('active', b.dataset.pf === filter);
    });

    var items = [];
    var typeColors = { attraction: '#4F6AF6', restaurant: '#F97316', hotel: '#10B981' };
    var typeLabels = { attraction: '景点', restaurant: '餐厅', hotel: '酒店' };

    if (filter === 'all' || filter === 'attraction')
        allPoiData.attraction.forEach(function (p) { items.push(Object.assign({}, p, { _type: 'attraction' })); });
    if (filter === 'all' || filter === 'restaurant')
        allPoiData.restaurant.forEach(function (p) { items.push(Object.assign({}, p, { _type: 'restaurant' })); });
    if (filter === 'all' || filter === 'hotel')
        allPoiData.hotel.forEach(function (p) { items.push(Object.assign({}, p, { _type: 'hotel' })); });

    var el = document.getElementById('poiListContent');
    if (!items.length) {
        el.innerHTML = '<p class="empty-hint" style="padding:16px;">暂无' + (filter === 'all' ? '' : typeLabels[filter]) + '数据</p>';
        return;
    }

    var html = items.map(function (p) {
        var color = typeColors[p._type];
        var label = typeLabels[p._type];
        var starsHtml = renderStars(p.rating);
        var ratingNum = (p.rating && p.rating !== 'None') ? '<span class="poi-rating-num">' + p.rating + '</span>' : '';
        var priceHtml = (p.price && p.price !== 'None') ? '<span class="poi-price">¥' + p.price + '</span>' : '';
        var fullDayBadge = p.is_full_day ? '<span class="poi-fullday-badge">🎪 整天</span>' : '';
        var addrHtml = p.address ? '<div class="poi-card-addr"><i class="fas fa-map-pin"></i>' + esc(p.address) + '</div>' : '';
        var thumbHtml = p.photo_url ? '<div class="poi-card-thumb" style="background-image:url(' + esc(p.photo_url) + ')"></div>' : '';
        return '<div class="poi-card' + (p.photo_url ? ' poi-card-has-photo' : '') + '" onclick="flyToPoi(' + p.lat + ',' + p.lng + ',' + JSON.stringify(p.name) + ',\'' + p._type + '\')">' +
            (thumbHtml ? thumbHtml : '<div class="poi-card-dot" style="background:' + color + ';"></div>') +
            '<div class="poi-card-body">' +
            '<div class="poi-card-row1">' +
            '<span class="poi-card-name">' + esc(p.name) + '</span>' +
            '<span class="poi-card-type" style="color:' + color + ';">' + label + '</span>' +
            '</div>' +
            '<div class="poi-card-rating">' + starsHtml + ratingNum + priceHtml + '</div>' +
            (fullDayBadge ? '<div>' + fullDayBadge + '</div>' : '') +
            addrHtml +
            '</div></div>';
    }).join('');

    el.innerHTML = html;
}

function renderStars(rating) {
    if (!rating || rating === 'None') return '';
    var r = parseFloat(rating);
    if (isNaN(r)) return '';
    var html = '';
    for (var i = 1; i <= 5; i++) {
        if (r >= i) html += '<i class="fas fa-star"></i>';
        else if (r >= i - 0.5) html += '<i class="fas fa-star-half-alt"></i>';
        else html += '<i class="far fa-star"></i>';
    }
    return '<span class="poi-stars" style="color:#F59E0B;">' + html + '</span>';
}

function flyToPoi(lat, lng, name, type) {
    switchTab('map');
    setTimeout(function () {
        map.setView([lat, lng], 16);
        var group = markerGroups[type] || [];
        for (var i = 0; i < group.length; i++) {
            if (group[i].data.name === name) {
                group[i].marker.fire('click');
                break;
            }
        }
    }, 150);
}


// ================================================================
//  小满聊天系统 (GuideAgent Frontend)
//  对话持久化: localStorage 保存消息, 断线恢复
// ================================================================

var chatInitialized = false;
var conversationExpanded = false;
var planCompleted = false;  // 规划是否已完成
var chatAutoHideTimer = null;      // 自动收起定时器
var chatUnreadCount = 0;           // 未读消息数
var AUTO_HIDE_DELAY = 6000;        // 自动收起延迟 (ms)

// ---- localStorage 对话持久化 ----
var CHAT_STORAGE_KEY = 'xiaoman_chat_messages';
var CHAT_STATE_KEY = 'xiaoman_chat_state';

function saveChatToStorage() {
    var container = document.getElementById('chatMessages');
    var messages = [];
    var nodes = container.querySelectorAll('.chat-msg');
    for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        // 跳过 typing indicator
        if (node.id && node.id.indexOf('typing-') === 0) continue;
        var role = 'system';
        if (node.classList.contains('chat-msg-user')) role = 'user';
        else if (node.classList.contains('chat-msg-assistant')) role = 'assistant';
        // 提取纯文本内容用于后端恢复
        var bubble = node.querySelector('.chat-msg-bubble');
        var sysEl = node.querySelector('.chat-msg-system');
        var text = '';
        if (bubble) text = bubble.textContent || '';
        else if (sysEl) text = sysEl.textContent || '';
        // 保存原始 HTML 用于前端显示恢复
        messages.push({ role: role, text: text, html: node.outerHTML });
    }
    try {
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages));
        localStorage.setItem(CHAT_STATE_KEY, JSON.stringify({
            initialized: chatInitialized,
            planCompleted: planCompleted
        }));
    } catch (e) {
        console.warn('localStorage save failed:', e);
    }
}

function loadChatFromStorage() {
    try {
        var raw = localStorage.getItem(CHAT_STORAGE_KEY);
        if (!raw) return null;
        return JSON.parse(raw);
    } catch (e) {
        return null;
    }
}

function loadChatState() {
    try {
        var raw = localStorage.getItem(CHAT_STATE_KEY);
        if (!raw) return null;
        return JSON.parse(raw);
    } catch (e) {
        return null;
    }
}

function clearChatStorage() {
    try {
        localStorage.removeItem(CHAT_STORAGE_KEY);
        localStorage.removeItem(CHAT_STATE_KEY);
    } catch (e) {}
}

// 将保存的对话历史恢复到后端 GuideAgent
function restoreBackendHistory(messages) {
    // 提取 user 和 assistant 消息用于恢复后端状态
    var history = [];
    for (var i = 0; i < messages.length; i++) {
        var m = messages[i];
        if (m.role === 'user' || m.role === 'assistant') {
            history.push({ role: m.role, content: m.text });
        }
    }
    if (history.length === 0) return;

    fetch('/api/chat/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ history: history })
    }).then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.status === 'ok') {
            console.log('[Chat] 后端对话历史恢复成功, 共 ' + history.length + ' 条');
        }
    }).catch(function (e) {
        console.warn('[Chat] 后端恢复失败:', e);
    });
}

function initChat() {
    var saved = loadChatFromStorage();
    var savedState = loadChatState();

    if (saved && saved.length > 0 && savedState && !savedState.planCompleted) {
        // 有未完成的对话 → 恢复显示 + 同步后端
        var container = document.getElementById('chatMessages');
        container.innerHTML = '';
        for (var i = 0; i < saved.length; i++) {
            var div = document.createElement('div');
            div.innerHTML = saved[i].html;
            if (div.firstChild) {
                container.appendChild(div.firstChild);
            }
        }
        container.scrollTop = container.scrollHeight;
        chatInitialized = true;
        planCompleted = false;
        // 添加一条恢复提示
        appendChatMessage('system', '🔄 已恢复上次的对话，我们继续聊吧~');
        // 同步到后端
        restoreBackendHistory(saved);
    } else {
        // 规划已完成或无历史 → 清除旧数据, 开始新对话
        clearChatStorage();
        planCompleted = false;
        if (!chatInitialized) {
            chatInitialized = true;
            sendSystemMessage('[系统] 用户已连接');
        }
    }
}

function showConversation() {
    var panel = document.getElementById('conversationPanel');
    var backdrop = document.getElementById('convBackdrop');
    if (!conversationExpanded) {
        panel.classList.remove('collapsed');
        backdrop.classList.remove('hidden');
        conversationExpanded = true;
        chatUnreadCount = 0;
        updateUnreadBadge();
        var msgs = document.getElementById('chatMessages');
        if (msgs) msgs.scrollTop = msgs.scrollHeight;
    }
    resetAutoHideTimer();
}

function hideConversation() {
    var panel = document.getElementById('conversationPanel');
    var backdrop = document.getElementById('convBackdrop');
    panel.classList.add('collapsed');
    backdrop.classList.add('hidden');
    conversationExpanded = false;
    clearAutoHideTimer();
}

function toggleConversation() {
    if (conversationExpanded) {
        hideConversation();
    } else {
        showConversation();
    }
}

function resetAutoHideTimer() {
    clearAutoHideTimer();
    chatAutoHideTimer = setTimeout(function () {
        // 如果输入框没有焦点，且没有正在输入的指示器，则自动收起
        var input = document.getElementById('chatInput');
        var hasTyping = document.querySelector('.typing-indicator');
        if (document.activeElement !== input && !hasTyping) {
            hideConversation();
        } else {
            // 用户仍在交互，延迟再试
            resetAutoHideTimer();
        }
    }, AUTO_HIDE_DELAY);
}

function clearAutoHideTimer() {
    if (chatAutoHideTimer) {
        clearTimeout(chatAutoHideTimer);
        chatAutoHideTimer = null;
    }
}

function updateUnreadBadge() {
    var badge = document.getElementById('chatUnreadBadge');
    if (!badge) return;
    if (chatUnreadCount > 0 && !conversationExpanded) {
        badge.textContent = chatUnreadCount > 99 ? '99+' : chatUnreadCount;
        badge.classList.add('show');
    } else {
        badge.classList.remove('show');
        chatUnreadCount = 0;
    }
}

// ---- 对话面板高度拖拽调整 ----
(function initConvResize() {
    document.addEventListener('DOMContentLoaded', function () {
        var handle = document.getElementById('convResizeHandle');
        var panel = document.getElementById('conversationPanel');
        if (!handle || !panel) return;

        var startY, startH;
        handle.addEventListener('mousedown', onStart);
        handle.addEventListener('touchstart', onStart, { passive: false });

        function onStart(e) {
            e.preventDefault();
            panel.classList.add('resizing');
            startY = e.type === 'touchstart' ? e.touches[0].clientY : e.clientY;
            startH = panel.offsetHeight;
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onEnd);
            document.addEventListener('touchmove', onMove, { passive: false });
            document.addEventListener('touchend', onEnd);
        }
        function onMove(e) {
            e.preventDefault();
            var y = e.type === 'touchmove' ? e.touches[0].clientY : e.clientY;
            var newH = startH + (y - startY);
            var minH = 120;
            var maxH = window.innerHeight - 120;
            newH = Math.max(minH, Math.min(maxH, newH));
            panel.style.height = newH + 'px';
        }
        function onEnd() {
            panel.classList.remove('resizing');
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onEnd);
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('touchend', onEnd);
        }
    });
})();

function sendSystemMessage(text) {
    fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
    }).then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.reply) {
            appendChatMessage('assistant', data.reply);
        }
    }).catch(function (e) {
        console.error('Chat init error:', e);
        appendChatMessage('assistant', '嗨～我是小满 🌿 很高兴见到你！不管是想来一场说走就走的旅行，还是已经有了心仪的目的地，都可以跟我聊聊 ✨ 你最近想去哪里看看呀？');
    });
}

function sendChatMessage() {
    var input = document.getElementById('chatInput');
    var text = input.value.trim();
    if (!text) return;

    input.value = '';
    appendChatMessage('user', text);
    clearAutoHideTimer();   // 等待回复期间不自动收起

    var sendBtn = document.getElementById('chatSendBtn');
    sendBtn.disabled = true;

    // 显示"正在输入"指示器
    var typingId = showTypingIndicator();

    fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: text,
            chip_state: {
                days: chipState.days ? parseInt(chipState.days) : null,
                budget: chipState.budget ? parseFloat(chipState.budget) : null,
                prefs: chipState.prefs.length > 0 ? chipState.prefs : null
            }
        })
    }).then(function (r) { return r.json(); })
    .then(function (data) {
        removeTypingIndicator(typingId);
        if (data.error) {
            appendChatMessage('assistant', '抱歉出了点问题: ' + data.error);
            return;
        }
        appendChatMessage('assistant', data.reply);

        // 更新旅行信息状态显示
        if (data.travel_info) {
            updateTravelInfoDisplay(data.travel_info);
        }

        if (data.is_ready && data.intent) {
            // 信息收集完毕，开始规划
            startPlanFromChat(data.intent);
        }
    }).catch(function (e) {
        removeTypingIndicator(typingId);
        appendChatMessage('assistant', '网络有点小波动，不过没关系，再跟我说一次吧～ 🙏');
    }).finally(function () {
        sendBtn.disabled = false;
    });
}

function startPlanFromChat(intent) {
    // 添加一条加载提示
    appendChatMessage('system', '🗺️ 小满正在认真研究你的行程，请稍等一小会儿...');
    hideConversation();
    showLoading('小满正在精心为你安排行程...');

    fetch('/api/chat/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intent: intent })
    }).then(function (r) {
        if (!r.ok) return r.json().then(function (e) { throw new Error(e.error || 'error'); });
        return r.json();
    }).then(function (data) {
        applyPlanResult(data);
        planCompleted = true;
        saveChatToStorage();
        appendChatMessage('assistant', '行程安排好了！🎉 我把每天的安排都放在了左侧「行程」面板，地图上也标注了所有推荐的地方。你看看有没有想调整的，比如哪里想多待一会儿、哪里想换个地方，随时告诉我～');
        // 自动切换到地图视图
        switchTab('map');
    }).catch(function (e) {
        appendChatMessage('assistant', '规划过程中遇到了一点小问题: ' + e.message + '\n不过没关系，你换个说法或者再试一次，我再帮你安排～');
    }).finally(function () {
        hideLoading();
    });
}

function appendChatMessage(role, text) {
    var container = document.getElementById('chatMessages');
    var wrapper = document.createElement('div');
    wrapper.className = 'chat-msg chat-msg-' + role;

    if (role === 'system') {
        wrapper.innerHTML = '<div class="chat-msg-system">' + esc(text) + '</div>';
    } else {
        var avatar = role === 'assistant' ? '🌿' : '🧑';
        var renderedText = md.render(text);
        wrapper.innerHTML =
            '<div class="chat-msg-avatar">' + avatar + '</div>' +
            '<div class="chat-msg-bubble">' + renderedText + '</div>';
    }
    container.appendChild(wrapper);
    container.scrollTop = container.scrollHeight;

    // 每条消息都持久化保存
    saveChatToStorage();

    // 新消息时展开对话面板
    showConversation();

    // assistant 消息到来后重置自动收起计时器
    if (role === 'assistant') {
        resetAutoHideTimer();
    }

    // 如果面板收起状态，增加未读计数
    if (!conversationExpanded && role !== 'system') {
        chatUnreadCount++;
        updateUnreadBadge();
    }
}

function showTypingIndicator() {
    var container = document.getElementById('chatMessages');
    var el = document.createElement('div');
    var id = 'typing-' + Date.now();
    el.id = id;
    el.className = 'chat-msg chat-msg-assistant';
    el.innerHTML =
        '<div class="chat-msg-avatar">🌿</div>' +
        '<div class="chat-msg-bubble typing-indicator"><span></span><span></span><span></span></div>';
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    return id;
}

function removeTypingIndicator(id) {
    var el = document.getElementById(id);
    if (el) el.remove();
}

function resetChat() {
    if (!confirm('确定要开始新对话吗？')) return;
    clearChatStorage();
    planCompleted = false;
    fetch('/api/chat/reset', { method: 'POST' })
    .then(function () {
        document.getElementById('chatMessages').innerHTML = '';
        chatInitialized = false;
        initChat();
    });
}
