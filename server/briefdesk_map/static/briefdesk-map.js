/* Briefdesk map preview.
 *
 * Everything here runs against the static payload rendered into the page by
 * briefdesk_map/views.py. Distances are computed in the browser, there is no
 * geo query behind this page.
 */
(function () {
    'use strict';

    var data = window.briefdeskMapData || {};
    var strings = data.strings || {};
    var sites = data.sites || [];
    var alerts = data.alerts || [];
    var radiusKm = data.default_radius || 50;

    var canvas = document.getElementById('bd-map-canvas');
    var listEl = document.getElementById('bd-map-list');
    var emptyEl = document.getElementById('bd-map-empty');
    var countEl = document.getElementById('bd-map-panel-count');
    var toastEl = document.getElementById('bd-map-toast');
    var notifyEl = document.getElementById('bd-map-notify');
    var notifyKmEl = document.getElementById('bd-map-notify-km');
    var companyEl = document.getElementById('bd-map-company');

    if (!canvas) {
        return;
    }

    if (typeof window.L === 'undefined') {
        canvas.textContent = strings.leaflet_missing || 'The map could not be loaded.';
        canvas.style.padding = '24px';
        return;
    }

    var L = window.L;
    var EARTH_RADIUS_KM = 6371;
    var disabledSeverities = {};
    var disabledThreats = {};
    var selectedReference = null;
    var toastTimer = null;

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function toRadians(degrees) {
        return (degrees * Math.PI) / 180;
    }

    function haversineKm(lat1, lon1, lat2, lon2) {
        var dLat = toRadians(lat2 - lat1);
        var dLon = toRadians(lon2 - lon1);
        var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
    }

    function formatKm(km) {
        if (km < 10) {
            return km.toFixed(1) + ' km';
        }
        return Math.round(km) + ' km';
    }

    function nearestSite(alert) {
        var best = null;

        sites.forEach(function (site) {
            var km = haversineKm(alert.lat, alert.lon, site.lat, site.lon);
            if (best === null || km < best.km) {
                best = {site: site, km: km};
            }
        });

        return best;
    }

    function isVisible(alert) {
        if (disabledSeverities[alert.severity]) {
            return false;
        }
        if (alert.threat_type && disabledThreats[alert.threat_type]) {
            return false;
        }
        return true;
    }

    function isNear(alert) {
        return alert.nearest !== null && alert.nearest.km <= radiusKm;
    }

    alerts.forEach(function (alert) {
        alert.nearest = nearestSite(alert);
    });

    /* Map */

    var map = L.map(canvas, {
        zoomControl: true,
        scrollWheelZoom: true,
        worldCopyJump: true
    });

    // Leaflet queues layers until a view is set, fitToContent() refines it later.
    map.setView([48, 12], 4);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'
    }).addTo(map);

    var radiusLayer = L.layerGroup().addTo(map);
    var siteLayer = L.layerGroup().addTo(map);
    var alertLayer = L.layerGroup().addTo(map);

    var siteIcon = L.divIcon({
        className: '',
        html: '<span class="bd-map__site-marker"></span>',
        iconSize: [12, 12],
        iconAnchor: [6, 6]
    });

    sites.forEach(function (site) {
        site.circle = L.circle([site.lat, site.lon], {
            radius: radiusKm * 1000,
            color: '#10243E',
            weight: 1,
            opacity: 0.45,
            dashArray: '4 4',
            fillColor: '#10243E',
            fillOpacity: 0.05,
            interactive: false
        }).addTo(radiusLayer);

        site.marker = L.marker([site.lat, site.lon], {
            icon: siteIcon,
            keyboard: false,
            title: site.name
        }).addTo(siteLayer);

        site.marker.bindPopup(
            '<span class="bd-popup__severity" style="color:#10243E">' + escapeHtml(strings.your_site || 'Your site') + '</span>' +
            '<span class="bd-popup__title">' + escapeHtml(site.name) + '</span>' +
            '<span class="bd-popup__meta">' + escapeHtml(site.type) +
            (site.city ? ' &middot; ' + escapeHtml(site.city) : '') +
            (site.country_name ? ', ' + escapeHtml(site.country_name) : '') + '</span>'
        );
    });

    function alertPopupHtml(alert) {
        var distance = '';

        if (alert.nearest) {
            distance = '<span class="bd-popup__meta">' + escapeHtml(formatKm(alert.nearest.km)) + ' ' +
                escapeHtml(strings.from_site || 'from') + ' ' + escapeHtml(alert.nearest.site.name) + '</span>';
        }

        var link = '';

        if (alert.reference && data.wire_url) {
            link = '<a class="bd-popup__link" href="' + escapeHtml(data.wire_url) + '?q=' +
                encodeURIComponent(alert.reference) + '">' +
                escapeHtml(strings.open_in_feed || 'Open in Intelligence Feed') + ' &rsaquo;</a>';
        }

        var tags = [alert.country_name, alert.sector_name, alert.threat_type_name]
            .filter(function (value) { return !!value; })
            .map(escapeHtml)
            .join(' &middot; ');

        return '<span class="bd-popup__severity" style="color:' + escapeHtml(alert.severity_color) + '">' +
            '<span class="bd-popup__dot" style="background:' + escapeHtml(alert.severity_color) + '"></span>' +
            escapeHtml(alert.severity_name) + '</span>' +
            '<span class="bd-popup__title">' + escapeHtml(alert.title) + '</span>' +
            distance +
            (tags ? '<span class="bd-popup__meta">' + tags + '</span>' : '') +
            (alert.reference ? '<span class="bd-popup__meta">' + escapeHtml(alert.reference) + '</span>' : '') +
            link;
    }

    alerts.forEach(function (alert) {
        alert.marker = L.circleMarker([alert.lat, alert.lon], {
            radius: alert.severity_radius || 8,
            color: '#FFFFFF',
            weight: 1.5,
            fillColor: alert.severity_color,
            fillOpacity: 0.85
        });

        alert.marker.bindPopup(alertPopupHtml(alert));
        alert.marker.on('click', function () {
            selectAlert(alert.reference, false);
        });
    });

    function fitToContent() {
        var points = sites.map(function (site) { return [site.lat, site.lon]; });

        alerts.forEach(function (alert) {
            if (isVisible(alert) && isNear(alert)) {
                points.push([alert.lat, alert.lon]);
            }
        });

        if (!points.length) {
            points = alerts.map(function (alert) { return [alert.lat, alert.lon]; });
        }

        if (points.length) {
            map.fitBounds(L.latLngBounds(points), {padding: [40, 40], maxZoom: 9});
        }
    }

    /* Rendering */

    function sortAlerts(list) {
        return list.slice().sort(function (a, b) {
            if (b.severity_rank !== a.severity_rank) {
                return b.severity_rank - a.severity_rank;
            }
            var aKm = a.nearest ? a.nearest.km : Infinity;
            var bKm = b.nearest ? b.nearest.km : Infinity;
            return aKm - bKm;
        });
    }

    function buildRow(alert) {
        var item = document.createElement('li');
        var button = document.createElement('button');

        button.type = 'button';
        button.className = 'bd-map__row' + (alert.reference === selectedReference ? ' bd-map__row--active' : '');
        button.setAttribute('data-reference', alert.reference);

        var meta = [alert.country_name, alert.threat_type_name]
            .filter(function (value) { return !!value; })
            .map(escapeHtml)
            .join(' &middot; ');

        var distance = alert.nearest
            ? escapeHtml(formatKm(alert.nearest.km) + ' ' + (strings.from_site || 'from') + ' ' + alert.nearest.site.city)
            : '';

        button.innerHTML =
            '<span class="bd-map__row-top">' +
                '<span class="bd-map__row-dot" style="background:' + escapeHtml(alert.severity_color) + '"></span>' +
                '<span class="bd-map__row-severity" style="color:' + escapeHtml(alert.severity_color) + '">' +
                    escapeHtml(alert.severity_name) + '</span>' +
                (distance ? '<span class="bd-map__row-distance">' + distance + '</span>' : '') +
            '</span>' +
            '<span class="bd-map__row-title">' + escapeHtml(alert.title) + '</span>' +
            '<span class="bd-map__row-meta">' + (alert.reference ? escapeHtml(alert.reference) : '') +
                (meta ? ' &middot; ' + meta : '') + '</span>';

        button.addEventListener('click', function () {
            selectAlert(alert.reference, true);
        });

        item.appendChild(button);
        return item;
    }

    function render() {
        alertLayer.clearLayers();

        var visible = alerts.filter(isVisible);
        var near = [];
        var far = 0;

        visible.forEach(function (alert) {
            var inRadius = isNear(alert);

            alert.marker.setStyle({
                fillOpacity: inRadius ? 0.85 : 0.25,
                opacity: inRadius ? 1 : 0.45
            });
            alert.marker.addTo(alertLayer);

            if (inRadius) {
                near.push(alert);
            } else {
                far += 1;
            }
        });

        listEl.innerHTML = '';
        sortAlerts(near).forEach(function (alert) {
            listEl.appendChild(buildRow(alert));
        });

        if (!sites.length) {
            emptyEl.hidden = false;
            emptyEl.textContent = strings.no_sites || 'No sites configured.';
        } else if (!near.length) {
            emptyEl.hidden = false;
            emptyEl.textContent = strings.no_alerts || 'No alerts match the current filters.';
        } else {
            emptyEl.hidden = true;
        }

        var summary = near.length + ' ' + (strings.within || 'within') + ' ' + radiusKm + ' ' +
            (strings.of_your_sites || 'km of your sites');

        if (far > 0) {
            summary += ' · ' + far + ' ' + (strings.more_outside || 'more outside the radius');
        }

        countEl.textContent = summary;
    }

    function selectAlert(reference, panTo) {
        selectedReference = reference;

        var alert = null;

        alerts.some(function (candidate) {
            if (candidate.reference === reference) {
                alert = candidate;
                return true;
            }
            return false;
        });

        Array.prototype.forEach.call(listEl.querySelectorAll('.bd-map__row'), function (row) {
            row.classList.toggle('bd-map__row--active', row.getAttribute('data-reference') === reference);
        });

        if (!alert) {
            return;
        }

        if (panTo) {
            map.setView([alert.lat, alert.lon], Math.max(map.getZoom(), 8), {animate: true});
        }

        alert.marker.openPopup();
    }

    function showToast(message) {
        toastEl.textContent = message;
        toastEl.hidden = false;

        if (toastTimer) {
            window.clearTimeout(toastTimer);
        }

        toastTimer = window.setTimeout(function () {
            toastEl.hidden = true;
            toastTimer = null;
        }, 5000);
    }

    /* Controls */

    Array.prototype.forEach.call(document.querySelectorAll('input[name="bd-map-radius"]'), function (input) {
        input.addEventListener('change', function () {
            if (!input.checked) {
                return;
            }
            radiusKm = parseInt(input.value, 10);
            sites.forEach(function (site) {
                site.circle.setRadius(radiusKm * 1000);
            });
            if (notifyKmEl) {
                notifyKmEl.textContent = String(radiusKm);
            }
            render();
        });
    });

    Array.prototype.forEach.call(document.querySelectorAll('.bd-chip'), function (chip) {
        chip.addEventListener('click', function () {
            var pressed = chip.getAttribute('aria-pressed') === 'true';
            var value = chip.getAttribute('data-value');
            var bucket = chip.getAttribute('data-filter') === 'severity' ? disabledSeverities : disabledThreats;

            chip.setAttribute('aria-pressed', pressed ? 'false' : 'true');
            if (pressed) {
                bucket[value] = true;
            } else {
                delete bucket[value];
            }
            render();
        });
    });

    if (notifyEl) {
        notifyEl.addEventListener('change', function () {
            showToast(strings.notify_toast || 'Preview feature.');
        });
    }

    if (companyEl) {
        companyEl.addEventListener('change', function () {
            var url = new URL(window.location.href);
            url.searchParams.set('company', companyEl.value);
            window.location.assign(url.toString());
        });
    }

    /* Start */

    render();
    fitToContent();

    if (typeof window.ResizeObserver === 'function') {
        new window.ResizeObserver(function () {
            map.invalidateSize();
        }).observe(canvas);
    }
})();
