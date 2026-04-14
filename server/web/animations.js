/* ═══════════════════════════════════════════════════════
   J.A.R.V.I.S — Canvas Animations
   Arc reactor, particles, waveforms
   ═══════════════════════════════════════════════════════ */

// ── Floating Particles Background ──────────────────
class ParticleField {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.particles = [];
        this.resize();
        window.addEventListener('resize', () => this.resize());

        for (let i = 0; i < 60; i++) {
            this.particles.push({
                x: Math.random() * this.w,
                y: Math.random() * this.h,
                vx: (Math.random() - 0.5) * 0.3,
                vy: (Math.random() - 0.5) * 0.3,
                r: Math.random() * 1.5 + 0.5,
                alpha: Math.random() * 0.3 + 0.1,
            });
        }
    }

    resize() {
        this.w = this.canvas.width = window.innerWidth;
        this.h = this.canvas.height = window.innerHeight;
    }

    draw() {
        this.ctx.clearRect(0, 0, this.w, this.h);

        for (const p of this.particles) {
            p.x += p.vx;
            p.y += p.vy;
            if (p.x < 0) p.x = this.w;
            if (p.x > this.w) p.x = 0;
            if (p.y < 0) p.y = this.h;
            if (p.y > this.h) p.y = 0;

            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(0, 212, 255, ${p.alpha})`;
            this.ctx.fill();
        }

        // Draw connections
        for (let i = 0; i < this.particles.length; i++) {
            for (let j = i + 1; j < this.particles.length; j++) {
                const a = this.particles[i], b = this.particles[j];
                const dx = a.x - b.x, dy = a.y - b.y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 120) {
                    this.ctx.beginPath();
                    this.ctx.moveTo(a.x, a.y);
                    this.ctx.lineTo(b.x, b.y);
                    this.ctx.strokeStyle = `rgba(0, 212, 255, ${0.05 * (1 - dist / 120)})`;
                    this.ctx.lineWidth = 0.5;
                    this.ctx.stroke();
                }
            }
        }
    }
}

// ── Arc Reactor Animation ──────────────────────────
class ArcReactor {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.cx = canvas.width / 2;
        this.cy = canvas.height / 2;
        this.time = 0;
        this.state = 'idle';
        this.intensity = 0.5;
        this.targetIntensity = 0.5;
    }

    setState(state) {
        this.state = state;
        switch (state) {
            case 'idle':       this.targetIntensity = 0.5; break;
            case 'listening':  this.targetIntensity = 0.8; break;
            case 'processing': this.targetIntensity = 1.0; break;
            case 'speaking':   this.targetIntensity = 0.9; break;
            default:           this.targetIntensity = 0.3;
        }
    }

    draw() {
        const ctx = this.ctx;
        const cx = this.cx, cy = this.cy;
        this.time += 0.016;

        this.intensity += (this.targetIntensity - this.intensity) * 0.05;

        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        const breath = (Math.sin(this.time * 1.5) + 1) * 0.5;
        const int = this.intensity;

        // Outer ring segments
        const segCount = this.state === 'processing' ? 12 : 8;
        const rotSpeed = this.state === 'processing' ? 0.5 : 0.15;

        for (let i = 0; i < segCount; i++) {
            const angle = (i / segCount) * Math.PI * 2 + this.time * rotSpeed;
            const gap = 0.15;
            const r = 120 + breath * 5;

            ctx.beginPath();
            ctx.arc(cx, cy, r, angle + gap, angle + (Math.PI * 2 / segCount) - gap);
            ctx.strokeStyle = this._glow(int * (0.4 + breath * 0.3));
            ctx.lineWidth = 3;
            ctx.stroke();
        }

        // Middle ring
        ctx.beginPath();
        ctx.arc(cx, cy, 85 + breath * 3, 0, Math.PI * 2);
        ctx.strokeStyle = this._teal(int * 0.4);
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Data ring (processing state)
        if (this.state === 'processing') {
            for (let i = 0; i < 24; i++) {
                const a = (i / 24) * Math.PI * 2 - this.time * 2;
                const r = 100;
                const px = cx + Math.cos(a) * r;
                const py = cy + Math.sin(a) * r;
                const size = 1.5 + Math.sin(a * 3 + this.time * 4) * 1;
                ctx.beginPath();
                ctx.arc(px, py, Math.max(0.5, size), 0, Math.PI * 2);
                ctx.fillStyle = i % 3 === 0 ? this._accent(0.8) : this._glow(0.5);
                ctx.fill();
            }
        }

        // Listening sound waves
        if (this.state === 'listening') {
            for (let w = 0; w < 4; w++) {
                const phase = (this.time * 3 + w * 0.8) % 3;
                const r = phase * 50;
                if (r > 0 && r < 140) {
                    ctx.beginPath();
                    ctx.arc(cx, cy, r, 0, Math.PI * 2);
                    ctx.strokeStyle = `rgba(0, 230, 118, ${0.4 * (1 - r / 140)})`;
                    ctx.lineWidth = 2;
                    ctx.stroke();
                }
            }
        }

        // Inner glow rings
        for (let r = 60; r > 15; r -= 8) {
            const alpha = ((60 - r) / 60) * int * (0.3 + breath * 0.2);
            ctx.beginPath();
            ctx.arc(cx, cy, r + breath * 2, 0, Math.PI * 2);
            ctx.strokeStyle = this._glow(alpha);
            ctx.lineWidth = 1;
            ctx.stroke();
        }

        // Center glow
        const gr = ctx.createRadialGradient(cx, cy, 0, cx, cy, 30 + breath * 10);
        gr.addColorStop(0, `rgba(0, 212, 255, ${0.8 * int})`);
        gr.addColorStop(0.4, `rgba(0, 212, 255, ${0.3 * int})`);
        gr.addColorStop(1, 'rgba(0, 212, 255, 0)');
        ctx.beginPath();
        ctx.arc(cx, cy, 30 + breath * 10, 0, Math.PI * 2);
        ctx.fillStyle = gr;
        ctx.fill();

        // Center bright core
        const coreR = 8 + breath * 4;
        ctx.beginPath();
        ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(200, 240, 255, ${0.9 * int})`;
        ctx.fill();

        // Orbiting particles
        const orbCount = this.state === 'processing' ? 6 : 4;
        const orbSpeed = this.state === 'processing' ? 0.8 : 0.3;
        for (let i = 0; i < orbCount; i++) {
            const a = this.time * orbSpeed + (i / orbCount) * Math.PI * 2;
            const r = 70 + Math.sin(this.time + i) * 10;
            const px = cx + Math.cos(a) * r;
            const py = cy + Math.sin(a) * r;
            ctx.beginPath();
            ctx.arc(px, py, 2, 0, Math.PI * 2);
            ctx.fillStyle = this._accent(0.8);
            ctx.fill();
        }

        // Speaking waveform around reactor
        if (this.state === 'speaking') {
            ctx.beginPath();
            for (let i = 0; i <= 360; i += 2) {
                const a = (i / 180) * Math.PI;
                const waveR = 110 + Math.sin(a * 8 + this.time * 5) * 8 * int
                             + Math.sin(a * 12 - this.time * 3) * 4 * int;
                const x = cx + Math.cos(a) * waveR;
                const y = cy + Math.sin(a) * waveR;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.closePath();
            ctx.strokeStyle = this._glow(0.3 * int);
            ctx.lineWidth = 1.5;
            ctx.stroke();
        }

        // Hexagon (processing)
        if (this.state === 'processing') {
            const hexR = 35;
            const hexRot = this.time * 0.3;
            ctx.beginPath();
            for (let i = 0; i <= 6; i++) {
                const a = hexRot + (i / 6) * Math.PI * 2;
                const x = cx + Math.cos(a) * hexR;
                const y = cy + Math.sin(a) * hexR;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.strokeStyle = this._glow(0.5);
            ctx.lineWidth = 1;
            ctx.stroke();
        }
    }

    _glow(a) { return `rgba(0, 212, 255, ${Math.max(0, Math.min(1, a))})`; }
    _teal(a) { return `rgba(0, 184, 169, ${Math.max(0, Math.min(1, a))})`; }
    _accent(a) { return `rgba(255, 215, 0, ${Math.max(0, Math.min(1, a))})`; }
}

// ── Waveform Visualizer ────────────────────────────
class WaveformVis {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.w = canvas.width;
        this.h = canvas.height;
        this.data = new Float32Array(64).fill(0);
        this.time = 0;
        this.active = false;
    }

    setActive(active) { this.active = active; }

    draw() {
        const ctx = this.ctx;
        this.time += 0.016;
        ctx.clearRect(0, 0, this.w, this.h);

        const midY = this.h / 2;

        // Generate wave data
        for (let i = 0; i < this.data.length; i++) {
            const target = this.active
                ? (Math.sin(i * 0.3 + this.time * 4) * 0.3 +
                   Math.sin(i * 0.7 - this.time * 2.5) * 0.2 +
                   Math.sin(i * 1.2 + this.time * 6) * 0.1) *
                  (1 - Math.abs(i - this.data.length / 2) / (this.data.length / 2)) * 0.8
                : Math.sin(i * 0.2 + this.time) * 0.05;

            this.data[i] += (target - this.data[i]) * 0.15;
        }

        // Draw waveform
        const barW = this.w / this.data.length;

        for (let i = 0; i < this.data.length; i++) {
            const val = Math.abs(this.data[i]);
            const h = val * this.h * 0.9;
            const x = i * barW;

            const gradient = ctx.createLinearGradient(x, midY - h, x, midY + h);
            gradient.addColorStop(0, 'rgba(0, 212, 255, 0.0)');
            gradient.addColorStop(0.3, `rgba(0, 212, 255, ${0.3 + val * 0.5})`);
            gradient.addColorStop(0.5, `rgba(0, 212, 255, ${0.5 + val * 0.5})`);
            gradient.addColorStop(0.7, `rgba(0, 212, 255, ${0.3 + val * 0.5})`);
            gradient.addColorStop(1, 'rgba(0, 212, 255, 0.0)');

            ctx.fillStyle = gradient;
            ctx.fillRect(x, midY - h, barW - 1, h * 2);
        }

        // Center line
        ctx.beginPath();
        ctx.moveTo(0, midY);
        ctx.lineTo(this.w, midY);
        ctx.strokeStyle = 'rgba(0, 212, 255, 0.15)';
        ctx.lineWidth = 1;
        ctx.stroke();
    }
}

// Export
window.ParticleField = ParticleField;
window.ArcReactor = ArcReactor;
window.WaveformVis = WaveformVis;
