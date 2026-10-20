/* Small offline chart renderer used by the analytics dashboard.
 * It intentionally exposes the subset of the Chart.js API used by analytics.js.
 */
(function (global) {
  class OfflineChart {
    static defaults = {
      color: '#94A3B8',
      borderColor: '#334155',
      font: { family: 'Segoe UI, Arial, sans-serif', size: 12 },
      plugins: { legend: { labels: { boxWidth: 14, padding: 14 } } },
    };

    constructor(context, config) {
      this.ctx = context;
      this.config = config;
      this.onWindowResize = () => this.draw();
      this.resizeObserver = typeof ResizeObserver === 'undefined'
        ? null : new ResizeObserver(() => this.draw());
      this.resizeObserver?.observe(context.canvas.parentElement || context.canvas);
      window.addEventListener('resize', this.onWindowResize);
      this.draw();
    }

    resize() { this.draw(); }

    draw() {
      const canvas = this.ctx.canvas;
      const parent = canvas.parentElement;
      const width = canvas.clientWidth || parent?.clientWidth || 640;
      if (!width) return;
      const ratio = window.devicePixelRatio || 1;
      const height = canvas.clientHeight || parent?.clientHeight || 320;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      this.ctx.clearRect(0, 0, width, height);
      const dataset = this.config.data.datasets?.[0] || { data: [] };
      const labels = this.config.data.labels || [];
      const type = this.config.type;
      const chartOptions = this.config.options || {};
      const hasData = dataset.data.some(value => value != null);
      if (!hasData) {
        this.ctx.fillStyle = OfflineChart.defaults.color;
        this.ctx.textAlign = 'center';
        this.ctx.font = `${OfflineChart.defaults.font.size}px ${OfflineChart.defaults.font.family}`;
        this.ctx.fillText('No data available yet', width / 2, height / 2);
        return;
      }
      if (type === 'pie') return this.drawPie(width, height, labels, dataset);
      this.drawAxes(width, height, chartOptions);
      if (type === 'line') return this.drawLine(width, height, labels, dataset);
      this.drawBars(width, height, labels, dataset);
    }

    drawAxes(width, height, options) {
      const ctx = this.ctx;
      const axis = options.scales?.y || {};
      const min = axis.min ?? 0;
      const max = axis.max ?? 1;
      const ticks = options.scales?.x?.ticks || {};
      const dataset = this.config.data.datasets?.[0] || { data: [] };
      const isPercent = axis.max === 100;
      const format = value => `${Number(value).toFixed(isPercent ? 0 : 0)}${isPercent ? '%' : ''}`;
      const horizontalStart = 52;
      const horizontalEnd = width - 12;
      const verticalStart = 12;
      const verticalEnd = height - 34;
      ctx.strokeStyle = OfflineChart.defaults.borderColor;
      ctx.lineWidth = 1;
      if (options.scales?.y?.border?.display !== false) {
        ctx.beginPath();
        ctx.moveTo(48, verticalStart);
        ctx.lineTo(48, verticalEnd);
        ctx.lineTo(horizontalEnd, verticalEnd);
        ctx.stroke();
      }
      ctx.fillStyle = OfflineChart.defaults.color;
      ctx.font = `${OfflineChart.defaults.font.size - 1}px ${OfflineChart.defaults.font.family}`;
      ctx.textAlign = 'right';
      const dataMax = Math.max(...dataset.data.filter(value => value != null).map(Number), 1);
      const tickStep = axis.max === 100 ? 25 : axis.ticks?.stepSize || Math.ceil((dataMax - min) / 4) || 1;
      const tickMax = axis.max ?? Math.ceil(dataMax / tickStep) * tickStep;
      for (let value = min; value <= tickMax; value += tickStep) {
        const y = verticalEnd - (value - min) / Math.max(tickMax - min, 1) * (verticalEnd - verticalStart);
        ctx.fillText(format(value), 44, y + 4);
      }
      return { horizontalStart, horizontalEnd, verticalStart, verticalEnd, min, max, ticks };
    }

    drawBars(width, height, labels, dataset) {
      const ctx = this.ctx;
      const values = dataset.data.map(value => value == null ? null : Number(value));
      const axis = this.config.options?.scales?.y || {};
      const max = axis.max ?? Math.max(...values.filter(value => value != null), 1);
      const min = axis.min ?? 0;
      const range = Math.max(max - min, 1);
      const plotW = width - 70;
      const plotH = height - 54;
      const validCount = values.filter(value => value != null).length;
      const slot = plotW / Math.max(validCount, 1);
      let barIndex = 0;
      values.forEach((value, index) => {
        if (value == null) return;
        const barH = Math.max(0, (value - min) / range * plotH);
        const baseline = height - 34 - (0 - min) / range * plotH;
        ctx.fillStyle = Array.isArray(dataset.backgroundColor)
          ? dataset.backgroundColor[index] : (dataset.backgroundColor || '#3B82F6');
        ctx.fillRect(52 + barIndex * slot + slot * 0.18, height - 34 - barH,
          slot * 0.64, Math.abs(baseline - (height - 34 - barH)));
        this.label(labels[index], 52 + barIndex * slot + slot / 2, height - 16, true);
        barIndex += 1;
      });
    }

    drawLine(width, height, labels, dataset) {
      const ctx = this.ctx;
      const values = dataset.data.map(value => value == null ? null : Number(value));
      const axis = this.config.options?.scales?.y || {};
      const max = axis.max ?? Math.max(...values.filter(value => value != null), 1);
      const min = axis.min ?? 0;
      const range = Math.max(max - min, 1);
      const plotW = width - 70;
      const plotH = height - 54;
      const ticks = this.config.options?.scales?.x?.ticks || {};
      const indices = values.map((value, index) => value == null ? null : index).filter(index => index != null);
      const firstIndex = indices[0] ?? 0;
      const lastIndex = indices[indices.length - 1] ?? 0;
      const xAt = index => 52 + (lastIndex === firstIndex ? plotW / 2 : (index - firstIndex) * plotW / (lastIndex - firstIndex));
      ctx.strokeStyle = dataset.borderColor || '#10B981';
      ctx.lineWidth = 2;
      let drawing = false;
      values.forEach((value, index) => {
        if (value == null) { drawing = false; return; }
        const x = xAt(index);
        const y = height - 34 - (value - min) / range * plotH;
        if (drawing) ctx.lineTo(x, y);
        else { ctx.beginPath(); ctx.moveTo(x, y); drawing = true; }
        ctx.stroke();
      });
      values.forEach((value, index) => {
        if (value == null) return;
        const x = xAt(index);
        const y = height - 34 - (value - min) / range * plotH;
        ctx.fillStyle = dataset.pointBackgroundColor || ctx.strokeStyle;
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      });
      const tickLimit = ticks.maxTicksLimit || labels.length;
      const labelStride = Math.max(1, Math.ceil(labels.length / tickLimit));
      labels.forEach((label, index) => {
        const x = 52 + (values.length === 1 ? plotW / 2 : index * plotW / (values.length - 1));
        if (label != null && label !== '' && index % labelStride === 0) this.label(label, x, height - 16, true);
      });
    }

    drawPie(width, height, labels, dataset) {
      const ctx = this.ctx;
      const values = dataset.data.map(Number);
      const total = values.reduce((sum, value) => sum + value, 0);
      if (!total) {
        ctx.fillStyle = OfflineChart.defaults.color;
        ctx.textAlign = 'center';
        ctx.font = `${OfflineChart.defaults.font.size}px ${OfflineChart.defaults.font.family}`;
        ctx.fillText('No feedback data yet', width / 2, height / 2);
        return;
      }
      const legendPosition = this.config.options?.plugins?.legend?.position || 'bottom';
      const sideLegend = legendPosition === 'right' && width >= 360;
      const legendRows = sideLegend ? labels.length : Math.ceil(labels.length / Math.max(1, Math.floor(width / 150)));
      const legendHeight = sideLegend ? 0 : legendRows * 18 + 12;
      const radius = Math.min(sideLegend ? width * 0.24 : width * 0.34, (height - legendHeight) * 0.38);
      const cx = sideLegend ? width * 0.34 : width * 0.5;
      const cy = sideLegend ? height * 0.48 : Math.max(radius + 8, (height - legendHeight) * 0.48);
      let angle = -Math.PI / 2;
      values.forEach((value, index) => {
        if (value <= 0) return;
        const next = angle + value / total * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius, angle, next);
        ctx.closePath();
        ctx.fillStyle = dataset.backgroundColor?.[index] || '#3B82F6';
        ctx.fill();
        angle = next;
      });
      labels.forEach((label, index) => {
        const legendPosition = this.config.options?.plugins?.legend?.position || 'bottom';
        const sideLegend = legendPosition === 'right' && width >= 360;
        ctx.fillStyle = dataset.backgroundColor?.[index] || '#3B82F6';
        if (sideLegend) {
          ctx.fillRect(width * 0.68, 24 + index * 22, 10, 10);
          this.label(label, width * 0.71, 33 + index * 22, false);
        } else {
          const columns = Math.max(1, Math.floor(width / 150));
          const col = index % columns;
          const row = Math.floor(index / columns);
          const x = (width / columns) * col + 12;
          ctx.fillRect(x, height - 42 + row * 18, 10, 10);
          this.label(label, x + 15, height - 33 + row * 18, false);
        }
      });
    }

    label(value, x, y, centered) {
      if (value === undefined) return;
      this.ctx.fillStyle = OfflineChart.defaults.color;
      this.ctx.font = `${OfflineChart.defaults.font.size}px ${OfflineChart.defaults.font.family}`;
      this.ctx.textAlign = centered ? 'center' : 'left';
      this.ctx.fillText(String(value), x, y);
    }

    destroy() {
      this.resizeObserver?.disconnect();
      window.removeEventListener('resize', this.onWindowResize);
      this.ctx.clearRect(0, 0, this.ctx.canvas.width, this.ctx.canvas.height);
    }
  }

  global.Chart = OfflineChart;
}(window));
