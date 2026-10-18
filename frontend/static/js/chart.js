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
      this.draw();
    }

    draw() {
      const canvas = this.ctx.canvas;
      const ratio = window.devicePixelRatio || 1;
      const width = canvas.clientWidth || 640;
      const height = canvas.clientHeight || 320;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      this.ctx.clearRect(0, 0, width, height);
      const dataset = this.config.data.datasets?.[0] || { data: [] };
      const labels = this.config.data.labels || [];
      const type = this.config.type;
      if (type === 'pie') return this.drawPie(width, height, labels, dataset);
      this.drawAxes(width, height);
      if (type === 'line') return this.drawLine(width, height, labels, dataset);
      this.drawBars(width, height, labels, dataset);
    }

    drawAxes(width, height) {
      const ctx = this.ctx;
      ctx.strokeStyle = OfflineChart.defaults.borderColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(48, 12);
      ctx.lineTo(48, height - 34);
      ctx.lineTo(width - 12, height - 34);
      ctx.stroke();
    }

    drawBars(width, height, labels, dataset) {
      const ctx = this.ctx;
      const values = dataset.data.map(Number);
      const max = Math.max(...values, 1);
      const plotW = width - 70;
      const plotH = height - 54;
      const slot = plotW / Math.max(values.length, 1);
      values.forEach((value, index) => {
        const barH = Math.max(0, value / max * plotH);
        ctx.fillStyle = Array.isArray(dataset.backgroundColor)
          ? dataset.backgroundColor[index] : (dataset.backgroundColor || '#3B82F6');
        ctx.fillRect(52 + index * slot + slot * 0.18, height - 34 - barH,
          slot * 0.64, barH);
        this.label(labels[index], 52 + index * slot + slot / 2, height - 16, true);
      });
    }

    drawLine(width, height, labels, dataset) {
      const ctx = this.ctx;
      const values = dataset.data.map(Number);
      const max = Math.max(...values, 1);
      const plotW = width - 70;
      const plotH = height - 54;
      ctx.strokeStyle = dataset.borderColor || '#10B981';
      ctx.lineWidth = 2;
      ctx.beginPath();
      values.forEach((value, index) => {
        const x = 52 + (values.length === 1 ? plotW / 2 : index * plotW / (values.length - 1));
        const y = height - 34 - value / max * plotH;
        index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.stroke();
      values.forEach((value, index) => {
        const x = 52 + (values.length === 1 ? plotW / 2 : index * plotW / (values.length - 1));
        const y = height - 34 - value / max * plotH;
        ctx.fillStyle = dataset.pointBackgroundColor || ctx.strokeStyle;
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
      });
      labels.forEach((label, index) => {
        const x = 52 + (values.length === 1 ? plotW / 2 : index * plotW / (values.length - 1));
        this.label(label, x, height - 16, true);
      });
    }

    drawPie(width, height, labels, dataset) {
      const ctx = this.ctx;
      const values = dataset.data.map(Number);
      const total = values.reduce((sum, value) => sum + value, 0) || 1;
      const radius = Math.min(width * 0.28, height * 0.38);
      const cx = width * 0.36;
      const cy = height * 0.48;
      let angle = -Math.PI / 2;
      values.forEach((value, index) => {
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
        ctx.fillStyle = dataset.backgroundColor?.[index] || '#3B82F6';
        ctx.fillRect(width * 0.68, 24 + index * 22, 10, 10);
        this.label(label, width * 0.71, 33 + index * 22, false);
      });
    }

    label(value, x, y, centered) {
      if (value === undefined) return;
      this.ctx.fillStyle = OfflineChart.defaults.color;
      this.ctx.font = `${OfflineChart.defaults.font.size}px ${OfflineChart.defaults.font.family}`;
      this.ctx.textAlign = centered ? 'center' : 'left';
      this.ctx.fillText(String(value), x, y);
    }

    destroy() { this.ctx.clearRect(0, 0, this.ctx.canvas.width, this.ctx.canvas.height); }
  }

  global.Chart = OfflineChart;
}(window));
